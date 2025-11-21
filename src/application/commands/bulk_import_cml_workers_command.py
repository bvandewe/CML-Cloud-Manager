"""Bulk import existing CML Workers command with handler."""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.settings import Settings
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.exceptions import EC2AuthenticationException, EC2InvalidParameterException, IntegrationException
from integration.models import CMLWorkerInstanceDto
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class BulkImportResult:
    """Result of bulk import operation."""

    imported: list[CMLWorkerInstanceDto]
    skipped: list[dict[str, str]]  # {"instance_id": str, "reason": str}
    total_found: int
    total_imported: int
    total_skipped: int


@dataclass
class BulkImportCMLWorkersCommand(Command[OperationResult[BulkImportResult]]):
    """Command to bulk import all matching EC2 instances as CML Workers.

    This command discovers all EC2 instances matching the search criteria
    and registers them in the local database, skipping any that are already
    registered.

    Args:
        aws_region: AWS region where instances exist
        ami_id: AMI ID to search for (optional)
        ami_name: AMI name pattern to search for (optional)
        created_by: User who initiated the import
    """

    aws_region: str
    ami_id: str | None = None  # Search by AMI ID
    ami_name: str | None = None  # Search by AMI name
    created_by: str | None = None


class BulkImportCMLWorkersCommandHandler(
    CommandHandlerBase,
    CommandHandler[BulkImportCMLWorkersCommand, OperationResult[BulkImportResult]],
):
    """Handle bulk importing existing EC2 instances as CML Workers."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client
        self.settings = settings

    async def handle_async(self, request: BulkImportCMLWorkersCommand) -> OperationResult[BulkImportResult]:
        """Handle bulk import CML Workers command.

        Args:
            request: Bulk import command with search criteria

        Returns:
            OperationResult with BulkImportResult containing imported/skipped counts

        Raises:
            EC2InvalidParameterException: If search parameters are invalid
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Validate search criteria
        if not any([command.ami_id, command.ami_name]):
            return self.bad_request("Must provide at least one of: ami_id or ami_name")

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.bulk_import.region": command.aws_region,
                "cml_worker.bulk_import.has_ami_id": command.ami_id is not None,
                "cml_worker.bulk_import.has_ami_name": command.ami_name is not None,
                "cml_worker.bulk_import.has_created_by": command.created_by is not None,
            }
        )

        try:

            aws_region = AwsRegion(command.aws_region)
            instances = []

            with tracer.start_as_current_span("discover_ec2_instances") as span:
                # Search by AMI ID or name
                log.info(f"Searching for EC2 instances by AMI in region {command.aws_region}")
                filters = {}

                if command.ami_id:
                    filters["image_ids"] = [command.ami_id]
                    span.set_attribute("ec2.lookup_method", "ami_id")
                    span.set_attribute("ec2.ami_id", command.ami_id)
                elif command.ami_name:
                    # Resolve AMI name to AMI IDs first
                    log.info(f"Resolving AMI name '{command.ami_name}' to AMI IDs...")
                    ami_ids = await self.aws_ec2_client.get_ami_ids_by_name(
                        aws_region=aws_region,
                        ami_name=command.ami_name,
                    )
                    if not ami_ids:
                        error_msg = f"No AMIs found matching name pattern '{command.ami_name}'"
                        log.error(error_msg)
                        return self.bad_request(error_msg)

                    filters["image_ids"] = ami_ids
                    span.set_attribute("ec2.lookup_method", "ami_name")
                    span.set_attribute("ec2.ami_name", command.ami_name)
                    span.set_attribute("ec2.resolved_ami_ids", ",".join(ami_ids))
                    log.info(f"Resolved AMI name to {len(ami_ids)} AMI ID(s): {ami_ids}")

                instances = await self.aws_ec2_client.list_instances(
                    region_name=aws_region,
                    **filters,
                )

                if not instances:
                    error_msg = "No matching EC2 instances found"
                    log.warning(f"{error_msg} for criteria: {command}")
                    return self.ok(
                        BulkImportResult(
                            imported=[],
                            skipped=[],
                            total_found=0,
                            total_imported=0,
                            total_skipped=0,
                        )
                    )

                log.info(f"Found {len(instances)} instance(s) matching criteria in {aws_region.value}")
                span.set_attribute("ec2.instances_found", len(instances))

            with tracer.start_as_current_span("filter_existing_workers") as span:
                # Get all existing workers to filter out duplicates and handle updates
                existing_workers = await self.cml_worker_repository.get_all_async()
                existing_workers_map = {w.state.aws_instance_id: w for w in existing_workers if w.state.aws_instance_id}

                log.info(f"Found {len(existing_workers_map)} existing workers in database")
                span.set_attribute("workers.existing_count", len(existing_workers_map))

            imported_workers = []
            skipped_instances = []

            with tracer.start_as_current_span("import_instances") as import_span:
                for instance in instances:
                    # Check if already registered
                    if instance.id in existing_workers_map:
                        worker = existing_workers_map[instance.id]

                        # Check for state updates for terminating instances
                        # If AWS says shutting-down/terminated but local is not, update it
                        updated = False
                        if instance.state == "shutting-down" and worker.state.status != CMLWorkerStatus.SHUTTING_DOWN:
                            log.info(f"🔄 Updating worker {worker.id()} status to SHUTTING_DOWN based on AWS state")
                            worker.update_status(CMLWorkerStatus.SHUTTING_DOWN)
                            updated = True
                        elif instance.state == "terminated" and worker.state.status != CMLWorkerStatus.TERMINATED:
                            log.info(f"🔄 Marking worker {worker.id()} as TERMINATED based on AWS state")
                            worker.terminate(terminated_by="system-sync")
                            updated = True

                        if updated:
                            try:
                                await self.cml_worker_repository.update_async(worker)
                                log.info(f"✅ Worker {worker.id()} status updated to {worker.state.status}")
                            except Exception as e:
                                log.error(f"❌ Failed to update worker {worker.id()} status: {e}")

                        log.info(f"Skipping instance {instance.id} - already registered")
                        skipped_instances.append(
                            {
                                "instance_id": instance.id,
                                "reason": "Already registered as CML Worker",
                            }
                        )
                        continue

                    try:
                        with tracer.start_as_current_span("import_single_instance") as instance_span:
                            instance_span.set_attribute("ec2.instance_id", instance.id)
                            instance_span.set_attribute("ec2.instance_type", instance.type)
                            instance_span.set_attribute("ec2.instance_state", instance.state)

                            # Determine worker name
                            worker_name = instance.name or f"worker-{instance.id}"

                            if instance.name:
                                log.info(f"Using AWS instance name for {instance.id}: {instance.name}")
                            else:
                                log.info(f"No AWS instance name, generating for {instance.id}: {worker_name}")

                            # Fetch AMI details from AWS
                            ami_details = await self.aws_ec2_client.get_ami_details(
                                aws_region=aws_region, ami_id=instance.image_id
                            )
                            ami_name = ami_details.ami_name if ami_details else None
                            ami_description = ami_details.ami_description if ami_details else None
                            ami_creation_date = ami_details.ami_creation_date if ami_details else None

                            if ami_details:
                                log.debug(f"Retrieved AMI details for {instance.image_id}: " f"name={ami_name}")
                            else:
                                log.warning(f"Failed to retrieve AMI details for {instance.image_id}")

                            # Create CML Worker aggregate
                            worker = CMLWorker.import_from_existing_instance(
                                name=worker_name,
                                aws_region=command.aws_region,
                                aws_instance_id=instance.id,
                                instance_type=instance.type,
                                ami_id=instance.image_id,
                                instance_state=instance.state,
                                created_by=command.created_by,
                                ami_name=ami_name,
                                ami_description=ami_description,
                                ami_creation_date=ami_creation_date,
                                public_ip=None,
                                private_ip=None,
                            )

                            instance_span.set_attribute("cml_worker.id", worker.id())
                            instance_span.set_attribute("cml_worker.name", worker_name)

                            # Save worker (will publish all domain events)
                            saved_worker = await self.cml_worker_repository.add_async(worker)

                            log.info(
                                f"✅ CML Worker imported: id={saved_worker.id()}, "
                                f"name={worker_name}, aws_instance_id={instance.id}"
                            )

                            # Build response DTO
                            instance_dto = CMLWorkerInstanceDto(
                                id=saved_worker.id(),
                                aws_instance_id=instance.id,
                                aws_region=aws_region,
                                instance_name=worker_name,
                                ami_id=instance.image_id,
                                ami_name=ami_name,
                                instance_type=instance.type,
                                instance_state=instance.state,
                                security_group_ids=[],
                                subnet_id="",
                                public_ip=None,
                                private_ip=None,
                                tags={},
                            )

                            imported_workers.append(instance_dto)

                    except Exception as e:
                        log.error(
                            f"❌ Failed to import instance {instance.id}: {e}",
                            exc_info=True,
                        )
                        skipped_instances.append(
                            {
                                "instance_id": instance.id,
                                "reason": f"Import failed: {str(e)}",
                            }
                        )

                import_span.set_attribute("workers.imported_count", len(imported_workers))
                import_span.set_attribute("workers.skipped_count", len(skipped_instances))

            result = BulkImportResult(
                imported=imported_workers,
                skipped=skipped_instances,
                total_found=len(instances),
                total_imported=len(imported_workers),
                total_skipped=len(skipped_instances),
            )

            log.info(
                f"🎉 Bulk import completed: {result.total_imported} imported, "
                f"{result.total_skipped} skipped out of {result.total_found} found"
            )

            return self.ok(result)

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for bulk CML Worker import: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while bulk importing CML Workers: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while bulk importing CML Workers: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error bulk importing CML Workers: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
            log.error(f"Unexpected error bulk importing CML Workers: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
