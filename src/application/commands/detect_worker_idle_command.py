"""Command for detecting worker idle state and triggering auto-pause."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.mediation import Command, CommandHandler, Mediator
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from application.commands.pause_worker_command import PauseWorkerCommand
from application.commands.update_worker_activity_command import (
    UpdateWorkerActivityCommand,
)
from application.queries.get_worker_idle_status_query import GetWorkerIdleStatusQuery
from application.queries.get_worker_telemetry_events_query import (
    GetWorkerTelemetryEventsQuery,
)

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class DetectWorkerIdleCommand(Command):
    """Command to detect worker idle state and auto-pause if eligible.

    Attributes:
        worker_id: Worker identifier
        force_check: Skip next_idle_check_at validation
    """

    worker_id: str
    force_check: bool = False


class DetectWorkerIdleCommandHandler(CommandHandler[DetectWorkerIdleCommand, dict]):
    """Handler for DetectWorkerIdleCommand.

    Orchestrates idle detection workflow:
    1. Fetch telemetry events from CML
    2. Update worker activity state
    3. Check idle status and eligibility
    4. Auto-pause if conditions met
    """

    def __init__(self, mediator: Mediator):
        """Initialize the handler.

        Args:
            mediator: Mediator for executing queries and commands
        """
        self._mediator = mediator

    async def handle_async(
        self, command: DetectWorkerIdleCommand, cancellation_token=None
    ) -> dict:
        """Execute the command.

        Args:
            command: Command parameters
            cancellation_token: Cancellation token

        Returns:
            OperationResult with detection results
        """
        with tracer.start_as_current_span(
            "DetectWorkerIdleCommandHandler.handle_async"
        ) as span:
            span.set_attribute("worker_id", command.worker_id)
            span.set_attribute("force_check", command.force_check)

            detection_result = {
                "worker_id": command.worker_id,
                "checked_at": datetime.utcnow(),
                "telemetry_fetched": False,
                "activity_updated": False,
                "idle_check_performed": False,
                "auto_pause_triggered": False,
                "error": None,
            }

            try:
                # Step 1: Fetch telemetry events from CML
                log.info(f"Fetching telemetry events for worker {command.worker_id}")

                telemetry_result = await self._mediator.execute_async(
                    GetWorkerTelemetryEventsQuery(worker_id=command.worker_id)
                )

                if not telemetry_result.is_success:
                    log.warning(
                        f"Failed to fetch telemetry for worker {command.worker_id}: "
                        f"{telemetry_result.error_message}"
                    )
                    detection_result["error"] = "Failed to fetch telemetry"
                    return self.ok(detection_result)

                detection_result["telemetry_fetched"] = True
                telemetry_data = telemetry_result.data

                # Step 2: Update worker activity state
                log.info(f"Updating activity state for worker {command.worker_id}")

                checked_at = datetime.now(timezone.utc)
                update_result = await self._mediator.execute_async(
                    UpdateWorkerActivityCommand(
                        worker_id=command.worker_id,
                        last_activity_at=telemetry_data.get("latest_activity_at"),
                        recent_events=telemetry_data.get("recent_events", []),
                        last_check_at=checked_at,
                        next_check_at=None,  # Will be calculated by GetWorkerIdleStatusQuery
                        target_pause_at=None,  # Will be calculated by GetWorkerIdleStatusQuery
                    )
                )

                if not update_result.is_success:
                    log.warning(
                        f"Failed to update activity for worker {command.worker_id}: "
                        f"{update_result.error_message}"
                    )
                    detection_result["error"] = "Failed to update activity"
                    return self.ok(detection_result)

                detection_result["activity_updated"] = True

                # Step 3: Check idle status and eligibility
                log.info(f"Checking idle status for worker {command.worker_id}")

                idle_status_result = await self._mediator.execute_async(
                    GetWorkerIdleStatusQuery(worker_id=command.worker_id)
                )

                if not idle_status_result.is_success:
                    log.warning(
                        f"Failed to check idle status for worker {command.worker_id}: "
                        f"{idle_status_result.error_message}"
                    )
                    detection_result["error"] = "Failed to check idle status"
                    return self.ok(detection_result)

                detection_result["idle_check_performed"] = True
                idle_status = idle_status_result.data

                # Add idle status details to result
                detection_result.update(
                    {
                        "is_idle": idle_status.get("is_idle"),
                        "idle_minutes": idle_status.get("idle_minutes"),
                        "eligible_for_pause": idle_status.get("eligible_for_pause"),
                        "in_snooze_period": idle_status.get("in_snooze_period"),
                    }
                )

                # Step 4: Auto-pause if eligible
                if idle_status.get("eligible_for_pause"):
                    log.info(
                        f"Worker {command.worker_id} is eligible for auto-pause "
                        f"(idle for {idle_status.get('idle_minutes'):.1f} minutes)"
                    )

                    pause_result = await self._mediator.execute_async(
                        PauseWorkerCommand(
                            worker_id=command.worker_id,
                            is_auto_pause=True,
                            reason=f"Auto-paused after {idle_status.get('idle_minutes'):.1f} minutes idle",
                        )
                    )

                    if pause_result.is_success:
                        log.info(f"Successfully auto-paused worker {command.worker_id}")
                        detection_result["auto_pause_triggered"] = True
                    else:
                        log.warning(
                            f"Failed to auto-pause worker {command.worker_id}: "
                            f"{pause_result.error_message}"
                        )
                        detection_result["error"] = "Failed to trigger auto-pause"
                else:
                    log.debug(
                        f"Worker {command.worker_id} not eligible for auto-pause: "
                        f"is_idle={idle_status.get('is_idle')}, "
                        f"auto_pause_enabled={idle_status.get('auto_pause_enabled')}, "
                        f"in_snooze={idle_status.get('in_snooze_period')}"
                    )

                span.set_status(Status(StatusCode.OK))
                return self.ok(detection_result)

            except Exception as e:
                log.error(
                    f"Unexpected error during idle detection for worker {command.worker_id}: {e}",
                    exc_info=True,
                )
                detection_result["error"] = str(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return self.ok(detection_result)
