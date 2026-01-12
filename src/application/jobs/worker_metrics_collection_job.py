"""Worker data collection background job.

This module defines a RecurrentBackgroundJob for collecting worker data at regular intervals.
It orchestrates both RefreshWorkerMetricsCommand and RefreshWorkerLabsCommand via Mediator
for all active workers concurrently.
"""

import asyncio
import logging

from neuroglia.mediation import Mediator
from opentelemetry import trace

from application.commands.worker import (RefreshWorkerLabsCommand,
                                         RefreshWorkerMetricsCommand)
from application.services.background_scheduler import (RecurrentBackgroundJob,
                                                       backgroundjob)
from application.settings import app_settings
from domain.repositories import CMLWorkerRepository
from integration.services.aws_ec2_api_client import AwsEc2Client

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@backgroundjob(task_type="recurrent", interval=app_settings.worker_metrics_poll_interval)
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    """Recurrent background job for collecting data from all active CML Workers.

    This job is scheduled by the BackgroundTaskScheduler and runs at regular intervals
    (configurable via WORKER_METRICS_POLL_INTERVAL env var, default: 300s/5min).

    It orchestrates two commands via Mediator for each active worker:
    1. RefreshWorkerMetricsCommand - EC2 status, CloudWatch metrics, CML system data
    2. RefreshWorkerLabsCommand - CML labs topology and state (conditional)

    This approach ensures consistent command orchestration logic between on-demand
    (single worker) and background (all workers) refresh operations.
    """

    def __init__(
        self,
        aws_ec2_client: AwsEc2Client | None = None,
    ):
        """Initialize the metrics collection job.

        Args:
            aws_ec2_client: AWS EC2 client instance (will be injected from service provider if None)
        """
        self.aws_ec2_client = aws_ec2_client
        self._service_provider = None  # Will be set during configure()

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["aws_ec2_client"] = None  # Don't serialize client (will be re-injected)
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
        logger.info("🔧 Configuring WorkerMetricsCollectionJob")

        self._service_provider = service_provider

        # Inject AwsEc2Client
        if not hasattr(self, "aws_ec2_client") or not self.aws_ec2_client:
            if self._service_provider:
                self.aws_ec2_client = self._service_provider.get_required_service(AwsEc2Client)
                logger.info("✅ Configured AwsEc2Client")
            else:
                logger.warning("⚠️ No service provider available to inject AwsEc2Client")

        logger.info("✅ Configuration complete")

    async def run_every(self, *args, **kwargs) -> None:
        """Execute the metrics collection job for all active workers with concurrent processing.

        This method is called by the BackgroundTaskScheduler at regular intervals.
        It performs the following steps:
        1. Query all active workers from repository
        2. Process workers concurrently with semaphore (max 10 concurrent)
        3. Batch update all workers to database
        """
        logger.info(
            "🚀 WorkerMetricsCollectionJob cycle start (interval=%s)s job_id=%s",
            app_settings.worker_metrics_poll_interval,
            getattr(self, "__task_id__", "unknown"),
        )

        # Ensure dependencies are injected
        assert hasattr(self, "aws_ec2_client") and self.aws_ec2_client is not None, "aws_ec2_client not injected"

        # Service provider should have been configured during job setup
        if not hasattr(self, "_service_provider") or not self._service_provider:
            logger.error("❌ service_provider not configured - job cannot execute")
            return

        with tracer.start_as_current_span("collect_all_workers_metrics") as span:
            span.set_attribute("job_id", self.__task_id__ or "unknown")

            # Create a scope to access scoped services
            scope = self._service_provider.create_scope()

            try:
                worker_repository = scope.get_required_service(CMLWorkerRepository)
                mediator = scope.get_required_service(Mediator)

                # 1. Get all active workers
                workers = await worker_repository.get_active_workers_async()

                if not workers:
                    logger.debug("No active workers to monitor")
                    return

                logger.info(f"📊 Collecting metrics for {len(workers)} active workers")
                span.set_attribute("worker_count", len(workers))

                # 3. Process workers concurrently with semaphore (limit to 10 concurrent operations)
                semaphore = asyncio.Semaphore(10)

                async def process_worker_with_semaphore(worker):
                    """Process single worker by orchestrating metrics and labs refresh commands."""
                    async with semaphore:
                        try:
                            worker_id = worker.id()

                            # Step 1: Refresh metrics (EC2, CloudWatch, CML system data)
                            # Mark as background_job so it doesn't trigger user throttle
                            metrics_result = await mediator.execute_async(
                                RefreshWorkerMetricsCommand(worker_id=worker_id, initiated_by="background_job")
                            )

                            if metrics_result.status != 200:
                                logger.warning(
                                    f"⚠️ Metrics refresh failed for worker {worker_id}: {metrics_result.detail}"
                                )
                                return worker_id, False, "metrics_failed"

                            # Step 2: Refresh labs (only if worker is running and CML is ready)
                            operations = metrics_result.data.get("operations", {})
                            worker_running = operations.get("ec2_sync", {}).get("worker_status") == "running"
                            cml_ready = operations.get("cml_sync", {}).get("cml_ready") is True

                            if worker_running and cml_ready:
                                labs_result = await mediator.execute_async(
                                    RefreshWorkerLabsCommand(worker_id=worker_id)
                                )

                                if labs_result.status != 200:
                                    logger.warning(
                                        f"⚠️ Labs refresh failed for worker {worker_id}: {labs_result.detail}"
                                    )
                                    return worker_id, True, "labs_failed"

                                logger.debug(f"✅ Full data refresh completed for worker {worker_id}")
                                return worker_id, True, "success"
                            else:
                                logger.debug(
                                    f"⏭️ Skipping labs refresh for worker {worker_id} - " f"not running or CML not ready"
                                )
                                return worker_id, True, "labs_skipped"

                        except asyncio.CancelledError:
                            logger.warning(f"⚠️ Processing cancelled for worker {worker.id()}")
                            return worker.id(), False, "cancelled"
                        except Exception as e:
                            logger.error(
                                f"❌ Failed to process worker {worker.id()}: {e}",
                                exc_info=True,
                            )
                            return worker.id(), False, f"exception: {str(e)}"

                # Process all workers concurrently
                results = await asyncio.gather(
                    *[process_worker_with_semaphore(w) for w in workers],
                    return_exceptions=True,
                )

                # 4. Aggregate results
                success_count = 0
                errors = 0
                labs_skipped = 0

                for result in results:
                    if isinstance(result, Exception):
                        errors += 1
                        logger.error(f"Worker processing exception: {result}")
                    elif result:
                        worker_id, success, status = result  # type: ignore[assignment]
                        if success:
                            success_count += 1
                            if status == "labs_skipped":
                                labs_skipped += 1
                        else:
                            errors += 1

                span.set_attribute("workers_processed", success_count)
                span.set_attribute("labs_skipped", labs_skipped)
                span.set_attribute("errors", errors)

                logger.info(
                    "✅ Completed metrics collection: %s workers processed, %s labs skipped, %s errors",
                    success_count,
                    labs_skipped,
                    errors,
                )

            except asyncio.CancelledError:
                logger.warning("⚠️ WorkerMetricsCollectionJob was cancelled")
                span.set_status(trace.Status(trace.StatusCode.ERROR, "Cancelled"))
                raise
            except Exception as e:
                logger.error(
                    f"❌ Failed to collect metrics: {e}",
                    exc_info=True,
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
            finally:
                # Dispose the scope to release scoped services
                if scope:
                    scope.dispose()
                if scope:
                    scope.dispose()
                if scope:
                    scope.dispose()
                if scope:
                    scope.dispose()
