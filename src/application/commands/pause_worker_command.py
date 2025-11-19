"""Command for pausing (stopping) a CML worker."""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.mediation import Command, CommandHandler
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from domain.repositories import CMLWorkerRepository
from integration.services.aws_ec2_api_client import AwsEc2Client

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class PauseWorkerCommand(Command[OperationResult[None]]):
    """Command to pause (stop) a CML worker.

    Attributes:
        worker_id: Worker identifier
        is_auto_pause: Whether this is an automatic pause (True) or manual (False)
        reason: Optional reason for pausing
    """

    worker_id: str
    is_auto_pause: bool = True
    reason: str | None = None


class PauseWorkerCommandHandler(
    CommandHandler[PauseWorkerCommand, OperationResult[None]]
):
    """Handler for PauseWorkerCommand.

    Stops EC2 instance and updates worker aggregate state.
    """

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        aws_client: AwsEc2Client,
    ):
        """Initialize the handler.

        Args:
            worker_repository: Repository for CML worker aggregates
            aws_client: AWS EC2 client for instance operations
        """
        self._repository = worker_repository
        self._aws_client = aws_client

    async def handle_async(
        self, command: PauseWorkerCommand, cancellation_token=None
    ) -> OperationResult[None]:
        """Execute the command.

        Args:
            command: Command parameters
            cancellation_token: Cancellation token

        Returns:
            OperationResult indicating success or failure
        """
        with tracer.start_as_current_span(
            "PauseWorkerCommandHandler.handle_async"
        ) as span:
            span.set_attribute("worker_id", command.worker_id)
            span.set_attribute("is_auto_pause", command.is_auto_pause)

            try:
                # Retrieve worker
                worker = await self._repository.get_async(
                    command.worker_id, cancellation_token
                )

                if not worker:
                    log.warning(f"Worker {command.worker_id} not found")
                    span.set_status(Status(StatusCode.ERROR, "Worker not found"))
                    return self.not_found(
                        f"Worker {command.worker_id}",
                        f"Worker {command.worker_id} not found",
                    )

                # Validate worker has EC2 instance ID
                if not worker.state.ec2_instance_id:
                    log.warning(f"Worker {command.worker_id} has no EC2 instance ID")
                    return self.bad_request("Worker has no EC2 instance ID")

                # Check if already stopping or stopped
                if worker.state.status.value in ["stopping", "stopped", "terminated"]:
                    log.info(
                        f"Worker {command.worker_id} already in state {worker.state.status.value}"
                    )
                    return self.no_content()

                # Stop EC2 instance
                log.info(
                    f"Stopping EC2 instance {worker.state.ec2_instance_id} "
                    f"for worker {command.worker_id} "
                    f"(auto_pause={command.is_auto_pause}, reason={command.reason})"
                )

                await self._aws_client.stop_instance(worker.state.ec2_instance_id)

                # Update worker aggregate
                worker.pause(is_auto_pause=command.is_auto_pause)

                # Persist changes
                await self._repository.update_async(worker, cancellation_token)

                log.info(
                    f"Successfully paused worker {command.worker_id} "
                    f"(auto_pause_count={worker.state.auto_pause_count}, "
                    f"manual_pause_count={worker.state.manual_pause_count})"
                )

                span.set_status(Status(StatusCode.OK))
                return self.no_content()

            except Exception as e:
                log.error(
                    f"Error pausing worker {command.worker_id}: {e}",
                    exc_info=True,
                )
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return self.bad_request(f"Error pausing worker: {e}")
