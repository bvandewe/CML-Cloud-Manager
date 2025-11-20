"""Create CML Worker command with handler."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.settings import Settings
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceCreationException,
    EC2InvalidParameterException,
    EC2QuotaExceededException,
    IntegrationException,
)
from integration.models import CMLWorkerInstanceDto
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class CreateCMLWorkerCommand(Command[OperationResult[CMLWorkerInstanceDto]]):
    """Command to create a new CML Worker and provision AWS EC2 instance.

    This command:
    1. Creates a CML Worker domain aggregate
    2. Provisions an AWS EC2 instance
    3. Associates the instance with the worker
    """

    name: str
    aws_region: str
    instance_type: str
    ami_id: str | None = None
    ami_name: str | None = None
    cml_version: str | None = None
    created_by: str | None = None


class CreateCMLWorkerCommandHandler(
    CommandHandlerBase,
    CommandHandler[CreateCMLWorkerCommand, OperationResult[CMLWorkerInstanceDto]],
):
    """Handle CML Worker creation and AWS EC2 instance provisioning."""

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

    async def handle_async(self, request: CreateCMLWorkerCommand) -> OperationResult[CMLWorkerInstanceDto]:
        """Handle create CML Worker command with EC2 provisioning.

        Args:
            request: Create command with worker specifications

        Returns:
            OperationResult with created CMLWorkerInstanceDto or error

        Raises:
            EC2InvalidParameterException: If AMI or other parameters are invalid
            EC2InstanceCreationException: If EC2 instance creation fails
            EC2QuotaExceededException: If AWS quota limit reached
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.name": command.name,
                "cml_worker.region": command.aws_region,
                "cml_worker.instance_type": command.instance_type,
                "cml_worker.has_created_by": command.created_by is not None,
            }
        )

        try:
            with tracer.start_as_current_span("create_cml_worker_aggregate") as span:
                # Determine AMI based on region
                ami_id = command.ami_id
                ami_name = command.ami_name
                ami_description = None
                ami_creation_date = None

                if not ami_id:
                    # Get AMI from settings for the specified region
                    region_ami_ids = self.settings.cml_worker_ami_ids
                    if command.aws_region not in region_ami_ids:
                        error_msg = f"No AMI configured for region {command.aws_region}"
                        log.error(error_msg)
                        return self.bad_request(error_msg)

                    ami_id = region_ami_ids[command.aws_region]

                    # Get AMI name from settings
                    region_ami_names = self.settings.cml_worker_ami_names
                    ami_name = region_ami_names.get(command.aws_region, "CML Worker AMI")

                # Fetch full AMI details from AWS
                if ami_id:
                    aws_region = AwsRegion(command.aws_region)
                    ami_details = self.aws_ec2_client.get_ami_details(aws_region=aws_region, ami_id=ami_id)
                    if ami_details:
                        ami_name = ami_details.ami_name or ami_name
                        ami_description = ami_details.ami_description
                        ami_creation_date = ami_details.ami_creation_date
                        log.info(
                            f"Retrieved AMI details for {ami_id}: name={ami_name}, "
                            f"description={ami_description[:50] if ami_description else 'N/A'}..., "
                            f"created={ami_creation_date}"
                        )
                    else:
                        log.warning(f"Failed to retrieve AMI details for {ami_id} in {aws_region.value}")

                # Create CML Worker domain aggregate first (pending state)
                worker = CMLWorker(
                    name=command.name,
                    aws_region=command.aws_region,
                    instance_type=command.instance_type,
                    ami_id=ami_id,
                    ami_name=ami_name,
                    ami_description=ami_description,
                    ami_creation_date=ami_creation_date,
                    status=CMLWorkerStatus.PENDING,
                    cml_version=command.cml_version,
                    created_at=datetime.now(timezone.utc),
                    created_by=command.created_by,
                )

                span.set_attribute("cml_worker.id", worker.id())
                span.set_attribute("cml_worker.ami_id", ami_id)

            with tracer.start_as_current_span("provision_ec2_instance") as span:
                # Provision EC2 instance
                aws_region = AwsRegion(command.aws_region)

                instance_dto = self.aws_ec2_client.create_instance(
                    aws_region=aws_region,
                    instance_name=command.name,
                    ami_id=ami_id,
                    ami_name=ami_name or "CML Worker AMI",
                    instance_type=command.instance_type,
                    security_group_ids=self.settings.cml_worker_security_group_ids,
                    subnet_id=self.settings.cml_worker_subnet_id,
                    key_name=self.settings.cml_worker_key_name,
                )

                if not instance_dto:
                    error_msg = "Failed to create EC2 instance - no instance returned"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", instance_dto.aws_instance_id)
                span.set_attribute("ec2.instance_state", instance_dto.instance_state or "unknown")

            with tracer.start_as_current_span("check_duplicate_worker") as span:
                # Check if instance already registered as a worker
                existing_worker = await self.cml_worker_repository.get_by_aws_instance_id_async(
                    instance_dto.aws_instance_id
                )
                if existing_worker:
                    error_msg = (
                        f"Instance {instance_dto.aws_instance_id} is already registered "
                        f"as worker '{existing_worker.state.name}' (ID: {existing_worker.id()})"
                    )
                    log.warning(error_msg)
                    span.set_attribute("worker.already_exists", True)
                    span.set_attribute("worker.existing_id", existing_worker.id())
                    return self.bad_request(error_msg)

                span.set_attribute("worker.already_exists", False)

            with tracer.start_as_current_span("assign_instance_to_worker") as span:
                # Assign EC2 instance to worker aggregate
                worker.assign_instance(
                    aws_instance_id=instance_dto.aws_instance_id,
                    public_ip=instance_dto.public_ip,
                    private_ip=instance_dto.private_ip,
                )

                # Update worker status based on instance state
                if instance_dto.instance_state == "running":
                    worker.update_status(CMLWorkerStatus.RUNNING)
                elif instance_dto.instance_state == "pending":
                    worker.update_status(CMLWorkerStatus.PENDING)

                span.set_attribute("worker.updated_status", worker.state.status.value)

            # Save worker (will publish all domain events)
            saved_worker = await self.cml_worker_repository.add_async(worker)

            log.info(
                f"CML Worker created successfully: id={saved_worker.id()}, "
                f"name={command.name}, aws_instance_id={instance_dto.aws_instance_id}"
            )

            return self.ok(instance_dto)

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for CML Worker creation: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except EC2QuotaExceededException as e:
            log.error(f"AWS quota exceeded while creating CML Worker: {e}")
            return self.bad_request(f"AWS quota exceeded: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while creating CML Worker: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except EC2InstanceCreationException as e:
            log.error(f"EC2 instance creation failed for CML Worker: {e}")
            return self.bad_request(f"Instance creation failed: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while creating CML Worker: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error creating CML Worker: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
