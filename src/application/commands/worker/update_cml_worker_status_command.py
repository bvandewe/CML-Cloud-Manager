"""Update CML Worker status command with handler."""

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
from integration.enums import AwsRegion
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceNotFoundException,
    EC2InvalidParameterException,
    EC2StatusCheckException,
    IntegrationException,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

from ..command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class UpdateCMLWorkerStatusCommand(Command[OperationResult[dict[str, str]]]):
    """Command to sync CML Worker status from AWS EC2.

    This command:
    1. Retrieves the worker from repository
    2. Queries EC2 instance status checks via AWS API
    3. Updates worker status based on EC2 state
    4. Returns status check information

    This is typically called by a background job to keep worker state in sync with AWS.
    """

    worker_id: str


class UpdateCMLWorkerStatusCommandHandler(
    CommandHandlerBase,
    CommandHandler[UpdateCMLWorkerStatusCommand, OperationResult[dict[str, str]]],
):
    """Handle syncing CML Worker status from AWS EC2."""

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

    async def handle_async(self, request: UpdateCMLWorkerStatusCommand) -> OperationResult[dict[str, str]]:
        """Handle update CML Worker status command.

        Args:
            request: Update status command with worker ID

        Returns:
            OperationResult with status check information, or error

        Raises:
            EC2InstanceNotFoundException: If instance doesn't exist
            EC2StatusCheckException: If status check retrieval fails
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # Retrieve worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(command.worker_id)

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                if not worker.state.aws_instance_id:
                    error_msg = f"CML Worker {command.worker_id} has no AWS instance assigned"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id)
                span.set_attribute("cml_worker.current_status", worker.state.status.value)

            with tracer.start_as_current_span("get_ec2_status_checks") as span:
                # Get instance status checks from AWS

                aws_region = AwsRegion(worker.state.aws_region)

                status_info = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_info:
                    error_msg = f"Failed to retrieve status for EC2 instance {worker.state.aws_instance_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                instance_state = status_info.get("instance_state", "unknown")
                span.set_attribute("ec2.instance_state", instance_state)
                span.set_attribute(
                    "ec2.instance_status_check",
                    status_info.get("instance_status_check", "unknown"),
                )
                span.set_attribute(
                    "ec2.system_status_check",
                    status_info.get("ec2_system_status_check", "unknown"),
                )

            with tracer.start_as_current_span("update_worker_status") as span:
                # Map EC2 state to CML Worker status
                status_updated = False

                if instance_state == "running":
                    status_updated = worker.update_status(CMLWorkerStatus.RUNNING)
                elif instance_state == "stopped":
                    status_updated = worker.update_status(CMLWorkerStatus.STOPPED)
                elif instance_state == "stopping":
                    status_updated = worker.update_status(CMLWorkerStatus.STOPPING)
                elif instance_state == "pending":
                    status_updated = worker.update_status(CMLWorkerStatus.STARTING)
                elif instance_state == "shutting-down":
                    status_updated = worker.update_status(CMLWorkerStatus.STOPPING)
                elif instance_state == "terminated":
                    worker.terminate()
                    status_updated = True

                span.set_attribute("cml_worker.status_updated", status_updated)
                span.set_attribute("cml_worker.new_status", worker.state.status.value)

            # Save worker if status changed (will publish domain events)
            if status_updated:
                await self.cml_worker_repository.update_async(worker)
                log.info(
                    f"CML Worker status updated: id={worker.id()}, "
                    f"aws_instance_id={worker.state.aws_instance_id}, "
                    f"new_status={worker.state.status.value}"
                )
            else:
                log.debug(f"CML Worker status unchanged: id={worker.id()}, " f"status={worker.state.status.value}")

            return self.ok(status_info)

        except EC2InstanceNotFoundException as e:
            log.error(f"EC2 instance not found for CML Worker {command.worker_id}: {e}")
            # Instance might have been terminated outside our system
            # Mark worker as terminated
            try:
                worker = await self.cml_worker_repository.get_by_id_async(command.worker_id)
                if worker and worker.state.status != CMLWorkerStatus.TERMINATED:
                    worker.terminate()
                    await self.cml_worker_repository.update_async(worker)
                    log.warning(f"Marked CML Worker {command.worker_id} as terminated (instance not found in AWS)")
            except Exception as update_error:
                log.error(f"Failed to mark worker as terminated: {update_error}")

            return self.bad_request(f"Instance not found: {str(e)}")

        except EC2StatusCheckException as e:
            log.error(f"Failed to retrieve status for CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Status check failed: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while checking status: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for status check: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while checking status: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error checking status: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
