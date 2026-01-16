"""Auto-import workers background job.

This module defines a RecurrentBackgroundJob for automatically discovering and importing
CML Worker instances from AWS EC2 by AMI name at regular intervals.
"""

import logging
from datetime import datetime, timezone

from neuroglia.mediation import Mediator
from opentelemetry import trace

from application.commands.worker import (BulkImportCMLWorkersCommand,
                                         RequestWorkerDataRefreshCommand)
from application.services.background_scheduler import (RecurrentBackgroundJob,
                                                       backgroundjob)
from application.services.sse_event_relay import SSEEventRelay
from application.settings import app_settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@backgroundjob(
    task_type="recurrent",
    interval=app_settings.auto_import_workers_interval,
)
class AutoImportWorkersJob(RecurrentBackgroundJob):
    """Recurrent background job for auto-importing CML Worker instances.

    This job runs at regular intervals (configurable via AUTO_IMPORT_WORKERS_INTERVAL
    env var) and automatically discovers EC2 instances matching the configured AMI name
    in the specified region, registering them as CML Workers if not already imported.

    The job uses BulkImportCMLWorkersCommand via Mediator to ensure consistent
    import logic with manual imports.

    Attributes:
        mediator: Mediator for executing commands
        sse_relay: SSE event relay for broadcasting job completion
    """

    def __init__(self, mediator: Mediator | None = None, sse_relay: SSEEventRelay | None = None):
        """Initialize the auto-import workers job.

        Args:
            mediator: Mediator instance (will be injected from service provider if None)
            sse_relay: SSE relay for broadcasting events (will be injected if None)
        """
        self.mediator = mediator
        self.sse_relay = sse_relay
        self._service_provider = None  # Will be set during configure()

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["mediator"] = None  # Don't serialize mediator
        state["sse_relay"] = None  # Don't serialize SSE relay
        state["_service_provider"] = None  # Don't serialize service provider
        return state

    def __setstate__(self, state):
        """Custom pickle deserialization - restore state."""
        self.__dict__.update(state)

    def configure(self, service_provider=None, **kwargs):
        """Configure the background job with dependencies.

        This is called by the BackgroundTaskScheduler during job deserialization.

        Args:
            service_provider: Service provider for dependency injection
            **kwargs: Additional configuration parameters
        """
        logger.info("🔧 Configuring AutoImportWorkersJob")

        self._service_provider = service_provider

        # Inject or instantiate Mediator
        if not hasattr(self, "mediator") or not self.mediator:
            if self._service_provider:
                self.mediator = self._service_provider.get_required_service(Mediator)
            else:
                logger.error("Cannot configure AutoImportWorkersJob without Mediator")
                raise RuntimeError("Mediator is required for AutoImportWorkersJob")

        # Inject SSE relay for broadcasting job completion
        if not hasattr(self, "sse_relay") or not self.sse_relay:
            if self._service_provider:
                try:
                    self.sse_relay = self._service_provider.get_required_service(SSEEventRelay)
                except Exception:
                    logger.warning("SSEEventRelay not available - job completion won't broadcast")
                    self.sse_relay = None

        logger.info("✅ AutoImportWorkersJob configured successfully")

    async def run_every(self, *args, **kwargs):
        """Execute the job on schedule.

        This method discovers EC2 instances matching the configured AMI name/region
        and imports them via BulkImportCMLWorkersCommand.

        Args:
            context: Execution context (optional)

        Returns:
            dict with execution results
        """
        with tracer.start_as_current_span("auto_import_workers_job") as span:
            logger.info(
                f"🔄 Starting auto-import workers job (region: {app_settings.auto_import_workers_region}, "
                f"AMI name: {app_settings.auto_import_workers_ami_name})"
            )

            span.set_attribute("job.type", "auto_import_workers")
            span.set_attribute("job.aws_region", app_settings.auto_import_workers_region)
            span.set_attribute("job.ami_name", app_settings.auto_import_workers_ami_name)

            try:
                # Skip if auto-import is disabled
                if not app_settings.auto_import_workers_enabled:
                    logger.info("⏭️ Auto-import workers disabled - skipping job")
                    return {
                        "status": "skipped",
                        "reason": "auto_import_workers_enabled=false",
                    }

                # Validate settings
                if not app_settings.auto_import_workers_region:
                    logger.warning("⚠️ auto_import_workers_region not configured")
                    return {
                        "status": "skipped",
                        "reason": "auto_import_workers_region not set",
                    }

                if not app_settings.auto_import_workers_ami_name:
                    logger.warning("⚠️ auto_import_workers_ami_name not configured")
                    return {
                        "status": "skipped",
                        "reason": "auto_import_workers_ami_name not set",
                    }

                # Execute bulk import command via Mediator
                command = BulkImportCMLWorkersCommand(
                    aws_region=app_settings.auto_import_workers_region,
                    ami_name=app_settings.auto_import_workers_ami_name,
                    created_by="auto-import-job",
                )

                result = await self.mediator.execute_async(command)

                # Align handling pattern with WorkerMetricsCollectionJob style (status code check)
                status_code = getattr(result, "status", None)
                detail = getattr(result, "detail", None)

                if status_code != 200:
                    # Use generic safe accessors for optional errors field
                    errors_val = getattr(result, "errors", []) or []
                    logger.warning(f"⚠️ Auto-import failed (status={status_code}) detail={detail} errors={errors_val}")
                    span.set_attribute("job.status", "failed")
                    if detail:
                        span.set_attribute("job.detail", str(detail))
                    if errors_val:
                        span.set_attribute("job.errors", str(errors_val))
                    return {
                        "status": "failed",
                        "status_code": status_code,
                        "detail": detail,
                        "errors": errors_val,
                    }

                data = result.data
                total_found = getattr(data, "total_found", 0)
                total_imported = getattr(data, "total_imported", 0)
                total_skipped = getattr(data, "total_skipped", 0)
                imported_list = getattr(data, "imported", []) or []
                imported_ids = [
                    getattr(w, "instance_id", None) for w in imported_list if getattr(w, "instance_id", None)
                ]

                logger.info(
                    f"✅ Auto-import completed: {total_imported} imported, {total_skipped} skipped, {total_found} total found"
                )
                span.set_attribute("job.status", "success")
                span.set_attribute("job.workers_found", total_found)
                span.set_attribute("job.workers_imported", total_imported)
                span.set_attribute("job.workers_skipped", total_skipped)
                span.set_attribute("job.imported_ids.count", len(imported_ids))

                # Trigger data refresh for newly imported workers
                if imported_list:
                    logger.info(f"🔄 Triggering data refresh for {len(imported_list)} newly imported workers")
                    for worker_dto in imported_list:
                        try:
                            # Extract ID and region from DTO
                            # Note: DTO field names might vary, checking both common patterns
                            worker_id = getattr(worker_dto, "aws_instance_id", None) or getattr(
                                worker_dto, "instance_id", None
                            )
                            region = getattr(worker_dto, "aws_region", None) or app_settings.auto_import_workers_region

                            # Convert enum to string if needed
                            if hasattr(region, "value"):
                                region = region.value

                            if worker_id:
                                logger.info(f"Requesting data refresh for new worker {worker_id} in {region}")
                                refresh_cmd = RequestWorkerDataRefreshCommand(worker_id=worker_id, region=str(region))
                                await self.mediator.execute_async(refresh_cmd)
                        except Exception as refresh_ex:
                            logger.error(f"Failed to trigger refresh for imported worker: {refresh_ex}")

                # Broadcast SSE event for job completion so UI can refresh
                await self._broadcast_refresh_completed(
                    total_found=total_found,
                    total_imported=total_imported,
                    total_skipped=total_skipped,
                )

                return {
                    "status": "success",
                    "status_code": status_code,
                    "total_found": total_found,
                    "total_imported": total_imported,
                    "total_skipped": total_skipped,
                    "imported_worker_ids": imported_ids,
                }

            except Exception as ex:
                logger.error(f"❌ Auto-import job failed with exception: {ex}", exc_info=True)
                span.set_attribute("job.status", "error")
                span.set_attribute("job.error", str(ex))

                # Broadcast error event so UI knows refresh is done (even if failed)
                await self._broadcast_refresh_completed(error=str(ex))

                return {
                    "status": "error",
                    "error": str(ex),
                }

    async def _broadcast_refresh_completed(
        self,
        total_found: int = 0,
        total_imported: int = 0,
        total_skipped: int = 0,
        error: str | None = None,
    ) -> None:
        """Broadcast SSE event when workers refresh job completes.

        Args:
            total_found: Number of EC2 instances found
            total_imported: Number of new workers imported
            total_skipped: Number of instances skipped (already registered)
            error: Error message if job failed
        """
        if not self.sse_relay:
            return

        try:
            event_data = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "total_found": total_found,
                "total_imported": total_imported,
                "total_skipped": total_skipped,
                "status": "error" if error else "success",
            }
            if error:
                event_data["error"] = error

            await self.sse_relay.broadcast_event(
                event_type="workers.refresh.completed",
                data=event_data,
                source="job.auto_import_workers",
            )
            logger.debug(f"Broadcasted workers.refresh.completed event: {event_data}")
        except Exception as e:
            logger.warning(f"Failed to broadcast workers.refresh.completed event: {e}")
            logger.debug(f"Broadcasted workers.refresh.completed event: {event_data}")
        except Exception as e:
            logger.warning(f"Failed to broadcast workers.refresh.completed event: {e}")
            logger.warning(f"Failed to broadcast workers.refresh.completed event: {e}")
