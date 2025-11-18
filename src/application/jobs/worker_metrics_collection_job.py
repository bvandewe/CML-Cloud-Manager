"""Worker metrics collection background job.

This module defines a RecurrentBackgroundJob for collecting worker metrics at regular intervals.
It's invoked by APScheduler and processes all active workers concurrently.
"""

import asyncio
import logging

from opentelemetry import trace

from application.services.background_scheduler import (
    RecurrentBackgroundJob,
    backgroundjob,
)
from application.services.worker_metrics_service import WorkerMetricsService
from application.settings import app_settings  # Import settings to read interval
from integration.services.aws_ec2_api_client import AwsEc2Client

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@backgroundjob(
    task_type="recurrent", interval=app_settings.worker_metrics_poll_interval
)
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    """Recurrent background job for collecting metrics from all active CML Workers.

    This job is scheduled by the BackgroundTaskScheduler and runs at regular intervals
    (configurable via WORKER_METRICS_POLL_INTERVAL env var, default: 300s/5min).

    It iterates through all active workers and polls AWS EC2/CloudWatch APIs to:
    - Sync worker status with EC2 instance state
    - Collect CPU/memory utilization metrics
    - Check instance health status
    - Update worker telemetry in database

    This single-job approach is simpler and more efficient than creating
    one job per worker for small-to-medium scale deployments (<100 workers).
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

        # Inject or instantiate AwsEc2Client
        if not hasattr(self, "aws_ec2_client") or not self.aws_ec2_client:
            from integration.services.aws_ec2_api_client import AwsEc2Client

            if self._service_provider:
                self.aws_ec2_client = self._service_provider.get_required_service(
                    AwsEc2Client
                )
            else:
                # Directly instantiate for horizontal scaling
                from application.settings import app_settings
                from integration.services.aws_ec2_api_client import (
                    AwsAccountCredentials,
                )

                credentials = AwsAccountCredentials(
                    aws_access_key_id=app_settings.aws_access_key_id,
                    aws_secret_access_key=app_settings.aws_secret_access_key,
                )
                self.aws_ec2_client = AwsEc2Client(aws_account_credentials=credentials)

            logger.info("✅ Configured AwsEc2Client")

        logger.info("✅ Configuration complete")

    async def run_every(self, *args, **kwargs) -> None:
        """Execute the metrics collection job for all active workers with concurrent processing.

        This method is called by the BackgroundTaskScheduler at regular intervals.
        It performs the following steps:
        1. Query all active workers from repository
        2. Process workers concurrently with semaphore (max 10 concurrent)
        3. Batch update all workers to database
        """
        # Ensure dependencies are injected
        assert (
            hasattr(self, "aws_ec2_client") and self.aws_ec2_client is not None
        ), "aws_ec2_client not injected"

        # Service provider should have been configured during job setup
        if not hasattr(self, "_service_provider") or not self._service_provider:
            logger.error("❌ service_provider not configured - job cannot execute")
            # Try to reconfigure
            try:
                logger.info("🔧 Attempting to reconfigure job")
                self.configure()  # No service provider - will instantiate dependencies directly
                if not hasattr(self, "_service_provider") or not self._service_provider:
                    logger.warning(
                        "⚠️ Still no service provider after reconfigure, continuing anyway"
                    )
            except Exception as e:
                logger.error(f"❌ Failed to reconfigure job: {e}")
                return

        with tracer.start_as_current_span("collect_all_workers_metrics") as span:
            span.set_attribute("job_id", self.__task_id__ or "unknown")

            # Create a scope to access scoped services
            if self._service_provider:
                scope = self._service_provider.create_scope()
            else:
                scope = None

            try:
                from domain.repositories import CMLWorkerRepository

                if scope:
                    worker_repository = scope.get_required_service(CMLWorkerRepository)
                else:
                    # No service provider - create repository directly for horizontal scaling
                    from motor.motor_asyncio import AsyncIOMotorClient
                    from neuroglia.serialization.json import JsonSerializer

                    from application.settings import app_settings
                    from domain.entities.cml_worker import CMLWorker
                    from integration.repositories.motor_cml_worker_repository import (
                        MongoCMLWorkerRepository,
                    )

                    # Get MongoDB connection string
                    mongo_uri = app_settings.connection_strings.get("mongo")
                    if not mongo_uri:
                        raise Exception("MongoDB connection string not configured")

                    # Create Motor client
                    client = AsyncIOMotorClient(mongo_uri)

                    # Create repository
                    worker_repository = MongoCMLWorkerRepository(
                        client=client,
                        database_name="cml_cloud_manager",
                        collection_name="cml_workers",
                        serializer=JsonSerializer(),
                        entity_type=CMLWorker,
                        mediator=None,  # No mediator for background jobs
                    )

                # 1. Get all active workers
                workers = await worker_repository.get_active_workers_async()

                if not workers:
                    logger.debug("No active workers to monitor")
                    return

                logger.info(f"📊 Collecting metrics for {len(workers)} active workers")
                span.set_attribute("worker_count", len(workers))

                # 2. Create metrics service
                metrics_service = WorkerMetricsService(self.aws_ec2_client)

                # 3. Process workers concurrently with semaphore (limit to 10 concurrent AWS API calls)
                semaphore = asyncio.Semaphore(10)

                async def process_worker_with_semaphore(worker):
                    """Process single worker with semaphore limit."""
                    async with semaphore:
                        try:
                            result = await metrics_service.collect_worker_metrics(
                                worker, collect_cloudwatch=True
                            )
                            if result.error:
                                logger.warning(
                                    f"⚠️ Metrics collection error for worker {worker.id()}: {result.error}"
                                )
                            return worker, result
                        except Exception as e:
                            logger.error(
                                f"❌ Failed to process worker {worker.id()}: {e}",
                                exc_info=True,
                            )
                            return worker, None

                # Process all workers concurrently
                results = await asyncio.gather(
                    *[process_worker_with_semaphore(w) for w in workers],
                    return_exceptions=True,
                )

                # 4. Separate successful and failed updates
                updated_workers = []
                errors = 0
                for result in results:
                    if isinstance(result, Exception):
                        errors += 1
                        logger.error(f"Worker processing exception: {result}")
                    elif result:
                        worker, metrics_result = result
                        if metrics_result and not metrics_result.error:
                            updated_workers.append(worker)
                        else:
                            errors += 1

                span.set_attribute("workers_updated", len(updated_workers))
                span.set_attribute("errors", errors)

                # 5. Batch update to database
                if updated_workers:
                    try:
                        await worker_repository.update_many_async(updated_workers)
                        logger.info(
                            f"✅ Completed metrics collection: {len(updated_workers)} workers updated, {errors} errors"
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed batch update: {e}", exc_info=True)
                        # Fall back to individual updates
                        logger.info("⚠️ Falling back to individual updates")
                        for worker in updated_workers:
                            try:
                                await worker_repository.update_async(worker)
                            except Exception as update_error:
                                logger.error(
                                    f"Failed to update worker {worker.id()}: {update_error}"
                                )
                else:
                    logger.warning("No workers successfully updated")

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
