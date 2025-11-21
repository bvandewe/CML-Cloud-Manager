"""On-demand worker data refresh background job.

This job executes a full data refresh for a single worker when triggered
by an on-demand request (e.g., user clicking "Refresh" button in UI).
It runs once immediately and orchestrates both metrics and labs refresh
commands via Mediator.
"""

import logging

from neuroglia.mediation import Mediator
from opentelemetry import trace

from application.commands.refresh_worker_labs_command import RefreshWorkerLabsCommand
from application.commands.refresh_worker_metrics_command import RefreshWorkerMetricsCommand
from application.services.background_scheduler import ScheduledBackgroundJob, backgroundjob

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@backgroundjob(task_type="scheduled")
class OnDemandWorkerDataRefreshJob(ScheduledBackgroundJob):
    """One-time background job for refreshing a single worker's data on demand.

    This job is scheduled by RequestWorkerDataRefreshCommand when a user
    requests an immediate data refresh via the UI. It orchestrates both:
    1. RefreshWorkerMetricsCommand - EC2 status, CloudWatch metrics, CML data
    2. RefreshWorkerLabsCommand - CML labs topology and state

    This ensures complete worker data refresh for one worker, then completes.
    """

    def __init__(self, worker_id: str, force: bool = False):
        """Initialize the on-demand refresh job.

        Args:
            worker_id: Worker identifier to refresh
            force: Whether to bypass throttling (default: False)
        """
        self.worker_id = worker_id
        self.force = force
        self._service_provider = None  # Will be set during configure()

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["_service_provider"] = None
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
        logger.debug(f"🔧 Configuring OnDemandWorkerDataRefreshJob for {self.worker_id}")
        self._service_provider = service_provider

    async def run_at(self, *args, **kwargs):
        """Execute full data refresh for the specified worker.

        This method orchestrates both metrics and labs refresh commands:
        1. RefreshWorkerMetricsCommand - EC2, CloudWatch, CML system data
        2. RefreshWorkerLabsCommand - CML labs topology and state

        Args:
            context: Job execution context (unused)
        """
        with tracer.start_as_current_span(
            "on_demand_refresh_job",
            attributes={
                "worker_id": self.worker_id,
                "job.type": "on_demand",
            },
        ) as span:
            try:
                if not self._service_provider:
                    logger.error(f"❌ service_provider not configured for on-demand job {self.worker_id}")
                    return

                # Create scope to access scoped services
                scope = self._service_provider.create_scope()

                try:
                    mediator = scope.get_required_service(Mediator)

                    logger.info(f"🔄 Executing on-demand data refresh for worker {self.worker_id}")

                    # Step 1: Refresh metrics (EC2, CloudWatch, CML system data)
                    # initiated_by="user" ensures throttle applies (default), protecting against rapid user clicks
                    # force=True bypasses throttle if requested (e.g. initial import)
                    metrics_result = await mediator.execute_async(
                        RefreshWorkerMetricsCommand(
                            worker_id=self.worker_id,
                            initiated_by="user",
                            force=self.force,
                        )
                    )

                    # Check if refresh was skipped due to throttling
                    if metrics_result.status == 200 and metrics_result.data.get("refresh_skipped"):
                        reason = metrics_result.data.get("reason", "unknown")

                        logger.info(f"⏭️ Metrics refresh skipped for worker {self.worker_id}: {reason}")

                        # SSE events are broadcast automatically by domain event handlers
                        # when worker state changes via repository operations

                        span.set_attribute("metrics.refresh.skipped", True)
                        span.set_attribute("metrics.skip.reason", reason)
                        return

                    if metrics_result.status != 200:
                        logger.warning(
                            f"⚠️ Metrics refresh failed for worker {self.worker_id}: " f"{metrics_result.detail}"
                        )
                        span.set_attribute("metrics.refresh.success", False)
                        span.set_attribute("metrics.error.message", metrics_result.detail)
                    else:
                        logger.info(f"✅ Metrics refresh completed for worker {self.worker_id}")
                        span.set_attribute("metrics.refresh.success", True)

                    # Step 2: Refresh labs (only if worker is running and CML is ready)
                    if metrics_result.status == 200:
                        operations = metrics_result.data.get("operations", {})
                        ec2_status = operations.get("ec2_sync", {}).get("worker_status")
                        worker_running = ec2_status == "running"
                        cml_ready = operations.get("cml_sync", {}).get("cml_ready") is True
                    else:
                        worker_running = False
                        cml_ready = False

                    if worker_running and cml_ready:
                        labs_result = await mediator.execute_async(RefreshWorkerLabsCommand(worker_id=self.worker_id))

                        if labs_result.status != 200:
                            logger.warning(
                                f"⚠️ Labs refresh failed for worker {self.worker_id}: " f"{labs_result.detail}"
                            )
                            span.set_attribute("labs.refresh.success", False)
                            span.set_attribute("labs.error.message", labs_result.detail)
                        else:
                            logger.info(f"✅ Labs refresh completed for worker {self.worker_id}")
                            span.set_attribute("labs.refresh.success", True)
                    else:
                        logger.debug(
                            f"⏭️ Skipping labs refresh for worker {self.worker_id} - "
                            f"worker not running or CML not ready"
                        )
                        span.set_attribute("labs.refresh.skipped", True)

                    # Overall success if metrics succeeded (labs are optional)
                    overall_success = metrics_result.status == 200
                    span.set_attribute("refresh.success", overall_success)

                    if overall_success:
                        logger.info(f"✅ On-demand data refresh completed for worker {self.worker_id}")
                        # SSE events are broadcast automatically by domain event handlers
                    else:
                        logger.warning(f"⚠️ On-demand data refresh had errors for worker {self.worker_id}")

                finally:
                    if scope:
                        scope.dispose()

            except Exception as e:
                logger.exception(f"❌ On-demand data refresh job failed for worker {self.worker_id}")
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
