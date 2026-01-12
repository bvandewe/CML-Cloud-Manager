"""Import existing CML Worker command with handler."""

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
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceNotFoundException,
    EC2InvalidParameterException,
    IntegrationException,
)
from integration.models import CMLWorkerInstanceDto
from integration.services.aws_ec2_api_client import AwsEc2Client

from ..command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class ImportCMLWorkerCommand(Command[OperationResult[CMLWorkerInstanceDto]]):
    """Command to import an existing EC2 instance as a CML Worker.

    This command discovers an existing EC2 instance and registers it
    in the local database without creating a new instance.

    Args:
        aws_region: AWS region where the instance exists
        aws_instance_id: AWS EC2 instance ID (if known)
        ami_id: AMI ID to search for (if instance_id not provided)
        ami_name: AMI name pattern to search for (if instance_id not provided)
        name: Optional friendly name for the CML Worker. If not provided,
              uses the AWS instance name, or generates one from the instance ID.
        created_by: User who initiated the import
    """

    aws_region: str
    aws_instance_id: str | None = None  # Direct lookup
    ami_id: str | None = None  # Search by AMI ID
    ami_name: str | None = None  # Search by AMI name
    name: str | None = None  # Optional: defaults to AWS instance name
    created_by: str | None = None


class ImportCMLWorkerCommandHandler(
    CommandHandlerBase,
    CommandHandler[ImportCMLWorkerCommand, OperationResult[CMLWorkerInstanceDto]],
):
    """Handle importing existing EC2 instances as CML Workers."""

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

    async def handle_async(self, request: ImportCMLWorkerCommand) -> OperationResult[CMLWorkerInstanceDto]:
        """Handle import CML Worker command.

        Args:
            request: Import command with search criteria

        Returns:
            OperationResult with imported CMLWorkerInstanceDto or error

        Raises:
            EC2InvalidParameterException: If search parameters are invalid
            EC2InstanceNotFoundException: If no matching instance found
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Validate search criteria
        if not any([command.aws_instance_id, command.ami_id, command.ami_name]):
            return self.bad_request("Must provide at least one of: aws_instance_id, ami_id, or ami_name")

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.import.region": command.aws_region,
                "cml_worker.import.has_instance_id": command.aws_instance_id is not None,
                "cml_worker.import.has_ami_id": command.ami_id is not None,
                "cml_worker.import.has_ami_name": command.ami_name is not None,
                "cml_worker.import.has_created_by": command.created_by is not None,
            }
        )

        try:

            aws_region = AwsRegion(command.aws_region)
            instance = None

            with tracer.start_as_current_span("discover_ec2_instance") as span:
                if command.aws_instance_id:
                    # Direct lookup by instance ID
                    log.info(f"Looking up EC2 instance by ID: {command.aws_instance_id}")
                    instance = await self.aws_ec2_client.get_instance_details(
                        aws_region=aws_region,
                        instance_id=command.aws_instance_id,
                    )
                    span.set_attribute("ec2.lookup_method", "instance_id")
                else:
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

                    if instances and len(instances) > 0:
                        instance = instances[0]
                        log.info(
                            f"Found {len(instances)} instance(s) matching criteria, "
                            f"selecting first match: {instance.id}"
                        )

                if not instance:
                    error_msg = "No matching EC2 instance found"
                    log.error(f"{error_msg} for criteria: {command}")
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", instance.id)
                span.set_attribute("ec2.instance_state", instance.state)
                span.set_attribute("ec2.instance_type", instance.type)

            with tracer.start_as_current_span("check_duplicate_worker") as span:
                # Check if instance already imported
                existing_worker = await self.cml_worker_repository.get_by_aws_instance_id_async(instance.id)
                if existing_worker:
                    error_msg = (
                        f"Instance {instance.id} is already registered "
                        f"as worker '{existing_worker.state.name}' (ID: {existing_worker.id()})"
                    )
                    log.warning(error_msg)
                    span.set_attribute("worker.already_exists", True)
                    span.set_attribute("worker.existing_id", existing_worker.id())
                    return self.bad_request(error_msg)

                span.set_attribute("worker.already_exists", False)

            with tracer.start_as_current_span("create_worker_from_import") as span:
                # Determine worker name (priority: custom name > AWS instance name > generated)
                worker_name = command.name or instance.name or f"worker-{instance.id}"

                if not command.name and instance.name:
                    log.info(f"No custom name provided, using AWS instance name: {instance.name}")
                elif not command.name and not instance.name:
                    log.info(f"No custom name or AWS instance name, generating: {worker_name}")

                # Fetch AMI details from AWS
                ami_details = await self.aws_ec2_client.get_ami_details(aws_region=aws_region, ami_id=instance.image_id)
                ami_name = ami_details.ami_name if ami_details else None
                ami_description = ami_details.ami_description if ami_details else None
                ami_creation_date = ami_details.ami_creation_date if ami_details else None

                if ami_details:
                    log.info(
                        f"Retrieved AMI details for import {instance.image_id}: "
                        f"name={ami_name}, description={ami_description[:50] if ami_description else 'N/A'}..., "
                        f"created={ami_creation_date}"
                    )
                else:
                    log.warning(f"Failed to retrieve AMI details for {instance.image_id} during import")

                # Create CML Worker aggregate using import factory method
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
                    public_ip=None,  # Will be populated on next status check
                    private_ip=None,
                )

                span.set_attribute("cml_worker.id", worker.id())
                span.set_attribute("cml_worker.name", worker_name)
                span.set_attribute("cml_worker.status", worker.state.status.value)

            with tracer.start_as_current_span("save_imported_worker") as span:
                # Save worker (will publish all domain events)
                saved_worker = await self.cml_worker_repository.add_async(worker)

                log.info(
                    f"CML Worker imported successfully: id={saved_worker.id()}, "
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
                security_group_ids=[],  # Not available from descriptor
                subnet_id="",  # Not available from descriptor
                public_ip=None,
                private_ip=None,
                tags={},
            )

            return self.ok(instance_dto)

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for CML Worker import: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except EC2InstanceNotFoundException as e:
            log.error(f"EC2 instance not found during import: {e}")
            return self.bad_request(f"Instance not found: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while importing CML Worker: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while importing CML Worker: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error importing CML Worker: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
