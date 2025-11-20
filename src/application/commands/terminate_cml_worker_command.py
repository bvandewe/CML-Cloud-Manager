"""Terminate CML Worker command with handler."""

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

from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
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
class TerminateCMLWorkerCommand(Command[OperationResult[bool]]):
    """Command to terminate a CML Worker and its EC2 instance.

    This command:
    1. Retrieves the worker from repository
    2. Terminates the EC2 instance via AWS API (permanent deletion)
    3. Marks worker aggregate as terminated

    Warning: This is a destructive operation that cannot be undone.
    """

    worker_id: str
    terminated_by: str | None = None


class TerminateCMLWorkerCommandHandler(
    CommandHandlerBase,
    CommandHandler[TerminateCMLWorkerCommand, OperationResult[bool]],
):
    """Handle terminating a CML Worker and its EC2 instance."""

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

    async def handle_async(self, request: TerminateCMLWorkerCommand) -> OperationResult[bool]:
        """Handle terminate CML Worker command.

        Args:
            request: Terminate command with worker ID

        Returns:
            OperationResult with True if terminated successfully, or error

        Raises:
            EC2InstanceNotFoundException: If instance doesn't exist (logged as warning)
            EC2InstanceOperationException: If terminate operation fails
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "cml_worker.has_terminated_by": command.terminated_by is not None,
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

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id or "none")
                span.set_attribute("cml_worker.current_status", worker.state.status.value)

            # Terminate EC2 instance if assigned
            if worker.state.aws_instance_id:
                with tracer.start_as_current_span("terminate_ec2_instance") as span:
                    try:
                        aws_region = AwsRegion(worker.state.aws_region)

                        success = self.aws_ec2_client.terminate_instance(
                            aws_region=aws_region,
                            instance_id=worker.state.aws_instance_id,
                        )

                        if not success:
                            log.warning(
                                f"Failed to terminate EC2 instance {worker.state.aws_instance_id}, "
                                "but will mark worker as terminated anyway"
                            )

                        span.set_attribute("ec2.terminate_success", success)

                    except EC2InstanceNotFoundException as e:
                        # Instance already gone - log warning and continue
                        log.warning(
                            f"EC2 instance {worker.state.aws_instance_id} not found during termination: {e}. "
                            "Marking worker as terminated anyway."
                        )
                        span.set_attribute("ec2.already_terminated", True)
            else:
                log.info(f"CML Worker {command.worker_id} has no AWS instance to terminate")

            with tracer.start_as_current_span("update_worker_aggregate") as span:
                # Mark worker as terminated in domain
                worker.terminate(terminated_by=command.terminated_by)

                span.set_attribute("cml_worker.terminated", True)

            # Save worker (will publish domain events)
            await self.cml_worker_repository.update_async(worker)

            log.info(
                f"CML Worker terminated successfully: id={worker.id()}, "
                f"aws_instance_id={worker.state.aws_instance_id or 'none'}, "
                f"terminated_by={command.terminated_by or 'system'}"
            )

            return self.ok(True)

        except EC2InstanceOperationException as e:
            log.error(f"Failed to terminate CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Terminate operation failed: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while terminating CML Worker: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for terminating CML Worker: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while terminating CML Worker: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error terminating CML Worker: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
