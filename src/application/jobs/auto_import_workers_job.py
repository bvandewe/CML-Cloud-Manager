"""Auto-import workers background job.

This module defines a RecurrentBackgroundJob for automatically discovering and importing
CML Worker instances from AWS EC2 by AMI name at regular intervals.
"""

import logging

from neuroglia.mediation import Mediator
from opentelemetry import trace

from application.commands.bulk_import_cml_workers_command import (
    BulkImportCMLWorkersCommand,
)
from application.services.background_scheduler import (
    RecurrentBackgroundJob,
    backgroundjob,
)
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
    """

    def __init__(self, mediator: Mediator | None = None):
        """Initialize the auto-import workers job.

        Args:
            mediator: Mediator instance (will be injected from service provider if None)
        """
        self.mediator = mediator
        self._service_provider = None  # Will be set during configure()

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["mediator"] = None  # Don't serialize mediator
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

        logger.info("✅ AutoImportWorkersJob configured successfully")

    async def execute_async(self, context: dict | None = None) -> dict:
        """Execute auto-import workers job.

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
            span.set_attribute(
                "job.aws_region", app_settings.auto_import_workers_region
            )
            span.set_attribute(
                "job.ami_name", app_settings.auto_import_workers_ami_name
            )

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

                if result.succeeded:
                    logger.info(
                        f"✅ Auto-import completed: {result.data.total_imported} imported, "
                        f"{result.data.total_skipped} skipped, {result.data.total_found} total found"
                    )
                    span.set_attribute("job.workers_found", result.data.total_found)
                    span.set_attribute(
                        "job.workers_imported", result.data.total_imported
                    )
                    span.set_attribute("job.workers_skipped", result.data.total_skipped)

                    return {
                        "status": "success",
                        "total_found": result.data.total_found,
                        "total_imported": result.data.total_imported,
                        "total_skipped": result.data.total_skipped,
                        "imported_worker_ids": [
                            w.instance_id for w in result.data.imported
                        ],
                    }
                else:
                    logger.error(
                        f"❌ Auto-import failed: {result.errors}",
                        extra={"errors": result.errors},
                    )
                    span.set_attribute("job.status", "failed")
                    span.set_attribute("job.errors", str(result.errors))

                    return {
                        "status": "failed",
                        "errors": result.errors,
                    }

            except Exception as ex:
                logger.error(
                    f"❌ Auto-import job failed with exception: {ex}", exc_info=True
                )
                span.set_attribute("job.status", "error")
                span.set_attribute("job.error", str(ex))

                return {
                    "status": "error",
                    "error": str(ex),
                }
