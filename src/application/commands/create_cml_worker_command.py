"""Create CML Worker command with handler."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

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
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class CreateCMLWorkerCommand(Command[OperationResult[dict]]):
    """Command to create a new CML Worker and provision AWS EC2 instance.

    This command:
    1. Creates a CML Worker domain aggregate (PENDING state)
    2. Saves it to the repository
    3. Triggers asynchronous provisioning via domain event handler
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
    CommandHandler[CreateCMLWorkerCommand, OperationResult[dict]],
):
    """Handle CML Worker creation."""

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

    async def handle_async(self, request: CreateCMLWorkerCommand) -> OperationResult[dict]:
        """Handle create CML Worker command.

        Args:
            request: Create command with worker specifications

        Returns:
            OperationResult with created worker details or error
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

                # Fetch full AMI details from AWS (optional, non-blocking)
                if ami_id:
                    aws_region = AwsRegion(command.aws_region)
                    try:
                        ami_details = await self.aws_ec2_client.get_ami_details(aws_region=aws_region, ami_id=ami_id)
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
                    except Exception as e:
                        log.warning(f"Error fetching AMI details: {e}")

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

            # Save worker (will publish CMLWorkerCreatedDomainEvent)
            # This event will be handled by ProvisionCMLWorkerEventHandler to trigger EC2 creation
            saved_worker = await self.cml_worker_repository.add_async(worker)

            log.info(
                f"CML Worker created successfully (pending provisioning): id={saved_worker.id()}, "
                f"name={command.name}"
            )

            # Return worker details
            return self.created(
                {
                    "id": saved_worker.id(),
                    "name": saved_worker.state.name,
                    "status": saved_worker.state.status.value,
                    "aws_region": saved_worker.state.aws_region,
                    "instance_type": saved_worker.state.instance_type,
                    "ami_id": saved_worker.state.ami_id,
                    "created_at": saved_worker.state.created_at.isoformat(),
                }
            )

        except Exception as e:
            log.error(f"Unexpected error creating CML Worker: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
            return self.bad_request(f"Unexpected error: {str(e)}")
