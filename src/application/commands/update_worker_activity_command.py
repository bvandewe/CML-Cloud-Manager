"""Command for updating worker activity from telemetry events."""

import logging
from dataclasses import dataclass
from datetime import datetime

from neuroglia.core import OperationResult
from neuroglia.mediation import Command, CommandHandler
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from domain.repositories import CMLWorkerRepository

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class UpdateWorkerActivityCommand(Command[OperationResult[None]]):
    """Command to update worker activity from telemetry events.

    Attributes:
        worker_id: Worker identifier
        last_activity_at: Timestamp of latest activity
        recent_events: List of recent telemetry events (max 10)
    """

    worker_id: str
    last_activity_at: datetime | None
    recent_events: list[dict] = None


class UpdateWorkerActivityCommandHandler(
    CommandHandler[UpdateWorkerActivityCommand, OperationResult[None]]
):
    """Handler for UpdateWorkerActivityCommand.

    Updates worker aggregate with latest activity data from telemetry.
    """

    def __init__(self, worker_repository: CMLWorkerRepository):
        """Initialize the handler.

        Args:
            worker_repository: Repository for CML worker aggregates
        """
        self._repository = worker_repository

    async def handle_async(
        self, command: UpdateWorkerActivityCommand, cancellation_token=None
    ) -> OperationResult[None]:
        """Execute the command.

        Args:
            command: Command parameters
            cancellation_token: Cancellation token

        Returns:
            OperationResult indicating success or failure
        """
        with tracer.start_as_current_span(
            "UpdateWorkerActivityCommandHandler.handle_async"
        ) as span:
            span.set_attribute("worker_id", command.worker_id)

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

                # Update activity tracking
                worker.update_activity(
                    last_activity_at=command.last_activity_at,
                    recent_events=command.recent_events or [],
                )

                # Persist changes
                await self._repository.update_async(worker, cancellation_token)

                log.info(
                    f"Updated activity for worker {command.worker_id}: "
                    f"last_activity_at={command.last_activity_at}, "
                    f"events={len(command.recent_events or [])}"
                )

                span.set_status(Status(StatusCode.OK))
                return self.no_content()

            except Exception as e:
                log.error(
                    f"Error updating activity for worker {command.worker_id}: {e}",
                    exc_info=True,
                )
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return self.bad_request(f"Error updating activity: {e}")
