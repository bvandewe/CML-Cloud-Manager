"""Start CML Worker command with handler."""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceNotFoundException,
    EC2InstanceOperationException,
    EC2InvalidParameterException,
    IntegrationException,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class StartCMLWorkerCommand(Command[OperationResult[bool]]):
    """Command to start a stopped CML Worker EC2 instance.

    This command:
    1. Retrieves the worker from repository
    2. Starts the EC2 instance via AWS API
    3. Updates worker status to STARTING
    """

    worker_id: str
    started_by: str | None = None


class StartCMLWorkerCommandHandler(
    CommandHandlerBase,
    CommandHandler[StartCMLWorkerCommand, OperationResult[bool]],
):
    """Handle starting a stopped CML Worker instance."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client

    async def handle_async(
        self, request: StartCMLWorkerCommand
    ) -> OperationResult[bool]:
        """Handle start CML Worker command.

        Args:
            request: Start command with worker ID

        Returns:
            OperationResult with True if started successfully, or error

        Raises:
            EC2InstanceNotFoundException: If instance doesn't exist
            EC2InstanceOperationException: If start operation fails
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "cml_worker.has_started_by": command.started_by is not None,
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # Retrieve worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(
                    command.worker_id
                )

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                if not worker.state.aws_instance_id:
                    error_msg = (
                        f"CML Worker {command.worker_id} has no AWS instance assigned"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id)
                span.set_attribute(
                    "cml_worker.current_status", worker.state.status.value
                )

            # Validate current status
            if worker.state.status == CMLWorkerStatus.RUNNING:
                log.info(f"CML Worker {command.worker_id} is already running")
                return self.ok(True)

            if worker.state.status == CMLWorkerStatus.TERMINATED:
                error_msg = f"Cannot start terminated CML Worker {command.worker_id}"
                log.error(error_msg)
                return self.bad_request(error_msg)

            with tracer.start_as_current_span("start_ec2_instance") as span:
                # Start EC2 instance
                from integration.enums import AwsRegion

                aws_region = AwsRegion(worker.state.aws_region)

                success = self.aws_ec2_client.start_instance(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not success:
                    error_msg = (
                        f"Failed to start EC2 instance {worker.state.aws_instance_id}"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.start_success", True)

            with tracer.start_as_current_span("update_worker_status") as span:
                # Update worker status to PENDING (instance starting)
                worker.update_status(CMLWorkerStatus.PENDING)

                span.set_attribute(
                    "cml_worker.new_status", CMLWorkerStatus.PENDING.value
                )

            # Save worker (will publish domain events)
            await self.cml_worker_repository.update_async(worker)

            log.info(
                f"CML Worker started successfully: id={worker.id()}, "
                f"aws_instance_id={worker.state.aws_instance_id}"
            )

            return self.ok(True)

        except EC2InstanceNotFoundException as e:
            log.error(f"EC2 instance not found for CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Instance not found: {str(e)}")

        except EC2InstanceOperationException as e:
            log.error(f"Failed to start CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Start operation failed: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while starting CML Worker: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for starting CML Worker: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while starting CML Worker: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error starting CML Worker: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
