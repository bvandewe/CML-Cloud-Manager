"""Background job for detecting idle workers and triggering auto-pause."""

import asyncio
import logging

from neuroglia.mediation import Mediator

from application.commands.detect_worker_idle_command import DetectWorkerIdleCommand
from application.services.background_scheduler import RecurrentBackgroundJob, backgroundjob
from application.settings import app_settings
from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository

log = logging.getLogger(__name__)


@backgroundjob(
    task_type="recurrent",
    interval=app_settings.worker_activity_detection_interval,
)
class ActivityDetectionJob(RecurrentBackgroundJob):
    """Background job that checks all running workers for idle activity.

    Runs at configured interval (default 30 minutes) and:
    1. Discovers all running workers
    2. Executes idle detection for each worker
    3. Auto-pauses eligible idle workers

    Configuration:
        - worker_activity_detection_interval: Seconds between job executions
        - worker_auto_pause_enabled: Global enable/disable flag
        - worker_idle_timeout_minutes: Idle threshold
    """

    def __init__(self):
        """Initialize the job."""
        self._service_provider = None  # Will be set during configure()

    def configure(self, service_provider=None, **kwargs):
        """Configure the background job with dependencies.

        This is called by the BackgroundTaskScheduler during job setup.

        Args:
            service_provider: Service provider for dependency injection
            **kwargs: Additional configuration parameters
        """
        self._service_provider = service_provider
        log.info("✅ ActivityDetectionJob configured")

    async def run_every(self, *args, **kwargs) -> None:
        """Execute the activity detection job.

        Called by the BackgroundTaskScheduler at regular intervals.
        """
        if not app_settings.worker_auto_pause_enabled:
            log.debug("Activity detection job skipped: worker_auto_pause_enabled=False")
            return

        log.info(
            f"Starting activity detection job "
            f"(interval={app_settings.worker_activity_detection_interval}s, "
            f"idle_timeout={app_settings.worker_idle_timeout_minutes}m)"
        )

        # Create scope for accessing repositories and mediator
        scope = self._service_provider.create_scope() if self._service_provider else None

        try:
            if not scope:
                log.error("❌ service_provider not configured - job cannot execute")
                return

            # Get repository and mediator from scope
            repository = scope.get_required_service(CMLWorkerRepository)
            mediator = scope.get_required_service(Mediator)

            # Find all active workers (optimization: don't fetch terminated ones)
            active_workers = await repository.get_active_workers_async()
            running_workers = [w for w in active_workers if w.state.status == CMLWorkerStatus.RUNNING]

            log.info(f"Found {len(running_workers)} running workers (total active: {len(active_workers)})")

            if not running_workers:
                log.debug("No running workers to check")
                return

            # Process workers concurrently with semaphore (limit to 5 concurrent operations)
            semaphore = asyncio.Semaphore(5)

            async def process_worker(worker):
                """Process single worker for idle detection."""
                # Skip if idle detection disabled for this worker
                if not worker.state.is_idle_detection_enabled:
                    log.debug(f"Skipping worker {worker.id()}: idle detection disabled")
                    return None

                async with semaphore:
                    log.info(f"Checking idle status for worker {worker.id()}")
                    try:
                        # Execute idle detection command
                        result = await mediator.execute_async(DetectWorkerIdleCommand(worker_id=worker.id()))

                        if result.is_success:
                            detection_data = result.data

                            if detection_data.get("auto_pause_triggered"):
                                log.info(
                                    f"Worker {worker.id()} auto-paused "
                                    f"(idle for {detection_data.get('idle_minutes'):.1f} minutes)"
                                )
                            else:
                                log.debug(
                                    f"Worker {worker.id()} idle check complete: "
                                    f"is_idle={detection_data.get('is_idle')}, "
                                    f"eligible={detection_data.get('eligible_for_pause')}"
                                )
                            return detection_data
                        else:
                            log.warning(f"Idle detection failed for worker {worker.id()}: {result.error_message}")
                            return None

                    except Exception as e:
                        log.error(
                            f"Error checking worker {worker.id()} for idle activity: {e}",
                            exc_info=True,
                        )
                        return e

            # Execute all tasks concurrently
            results = await asyncio.gather(*[process_worker(w) for w in running_workers], return_exceptions=True)

            # Summary logging
            valid_results = [r for r in results if r and not isinstance(r, Exception)]
            auto_paused_count = sum(1 for r in valid_results if r.get("auto_pause_triggered"))
            idle_count = sum(1 for r in valid_results if r.get("is_idle"))
            error_count = sum(1 for r in results if isinstance(r, Exception))

            log.info(
                f"Activity detection job complete: "
                f"checked={len(valid_results)}, "
                f"idle={idle_count}, "
                f"auto_paused={auto_paused_count}, "
                f"errors={error_count}"
            )

        except Exception as e:
            log.error(f"Error in activity detection job: {e}", exc_info=True)
        finally:
            # Clean up scope
            if scope:
                scope.dispose()
