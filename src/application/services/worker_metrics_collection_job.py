"""Worker metrics collection background job.

This module defines a RecurrentBackgroundJob for collecting worker metrics at regular intervals.
It's invoked by APScheduler and emits metrics events to observers (notification handlers).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import trace

from application.services.background_scheduler import (
    RecurrentBackgroundJob,
    backgroundjob,
)
from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@backgroundjob(task_type="recurrent")
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    """Recurrent background job for collecting metrics from a single CML Worker.

    This job is scheduled by the BackgroundTaskScheduler and runs at regular intervals.
    It polls AWS EC2/CloudWatch APIs to:
    - Sync worker status with EC2 instance state
    - Collect CPU/memory utilization metrics
    - Check instance health status
    - Emit metrics events to observers

    Attributes:
        worker_id: UUID of the CML Worker being monitored
        aws_ec2_client: AWS EC2 API client
        worker_repository: Repository for worker persistence
        _observers: List of observer callbacks that receive metrics events
    """

    def __init__(
        self,
        worker_id: str,
        aws_ec2_client: Optional[AwsEc2Client] = None,
        worker_repository: Optional[CMLWorkerRepository] = None,
    ):
        """Initialize the metrics collection job.

        Args:
            worker_id: UUID of the worker to monitor
            aws_ec2_client: AWS EC2 client instance (will be injected from service provider if None)
            worker_repository: Worker repository instance (will be injected from service provider if None)
        """
        self.worker_id = worker_id
        self.aws_ec2_client = aws_ec2_client
        self._service_provider = None  # Will be set during configure()
        self._observers: List[Callable[[Dict[str, Any]], None]] = (
            []
        )  # Always initialize

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        # Remove unpicklable attributes
        state["_observers"] = []  # Don't serialize observers
        state["_notification_handler"] = (
            None  # Don't serialize handler (will be re-resolved)
        )
        state["aws_ec2_client"] = None  # Don't serialize client (will be re-injected)
        state["_service_provider"] = None  # Don't serialize service provider
        return state

    def __setstate__(self, state):
        """Custom pickle deserialization - restore state."""
        self.__dict__.update(state)
        # Ensure lists are initialized
        if "_observers" not in self.__dict__:
            self._observers = []

    def configure(self, service_provider=None, **kwargs):
        """Configure the background job with dependencies.

        This is called by the BackgroundTaskScheduler during job deserialization.
        For horizontal scaling, this method reconstructs dependencies directly
        from module-level imports rather than relying on a service provider.

        Args:
            service_provider: (Optional) Service provider for dependency injection.
                             If not provided, dependencies are instantiated directly.
            **kwargs: Additional configuration parameters
        """
        logger.info(
            f"🔧 Configuring WorkerMetricsCollectionJob for worker {self.worker_id if hasattr(self, 'worker_id') else 'UNKNOWN'}"
        )

        # If service provider is provided, use it (for backwards compatibility)
        # Otherwise, reconstruct dependencies directly (for horizontal scaling)
        if service_provider:
            self._service_provider = service_provider
        else:
            # No service provider - directly instantiate dependencies
            # This ensures the job can run on any worker instance
            self._service_provider = None

        # Inject or instantiate AwsEc2Client
        if not hasattr(self, "aws_ec2_client") or not self.aws_ec2_client:
            from integration.services.aws_ec2_api_client import AwsEc2Client

            if self._service_provider:
                # Use service provider if available
                self.aws_ec2_client = self._service_provider.get_required_service(
                    AwsEc2Client
                )
            else:
                # Directly instantiate for horizontal scaling
                # Get credentials from settings
                from application.settings import app_settings
                from integration.services.aws_ec2_api_client import (
                    AwsAccountCredentials,
                )

                credentials = AwsAccountCredentials(
                    aws_access_key_id=app_settings.aws_access_key_id,
                    aws_secret_access_key=app_settings.aws_secret_access_key,
                )
                self.aws_ec2_client = AwsEc2Client(aws_account_credentials=credentials)

            logger.info(f"✅ Configured AwsEc2Client for worker {self.worker_id}")

        # Get or instantiate notification handler
        try:
            from application.services.worker_notification_handler import (
                WorkerNotificationHandler,
            )

            if self._service_provider:
                self._notification_handler = (
                    self._service_provider.get_required_service(
                        WorkerNotificationHandler
                    )
                )
            else:
                # Directly instantiate for horizontal scaling
                # Use same thresholds as configured in main.py
                self._notification_handler = WorkerNotificationHandler(
                    cpu_threshold=90.0,
                    memory_threshold=90.0,
                )

            logger.info(
                f"✅ Configured WorkerNotificationHandler for worker {self.worker_id}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Could not configure WorkerNotificationHandler: {e}")
            self._notification_handler = None

        # Ensure _observers list exists (for backwards compatibility)
        if not hasattr(self, "_observers"):
            self._observers = []
            logger.debug(f"✅ Initialized _observers list for worker {self.worker_id}")

        logger.info(f"✅ Configuration complete for worker {self.worker_id}")

    def subscribe(self, observer: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe an observer to metrics events.

        Args:
            observer: Callback function that receives metrics data dict
        """
        if observer not in self._observers:
            self._observers.append(observer)
            logger.debug(f"Added observer for worker {self.worker_id}")

    def unsubscribe(self, observer: Callable[[Dict[str, Any]], None]) -> None:
        """Unsubscribe an observer from metrics events.

        Args:
            observer: Callback function to remove
        """
        if observer in self._observers:
            self._observers.remove(observer)
            logger.debug(f"Removed observer for worker {self.worker_id}")

    async def run_every(self, *args, **kwargs) -> None:
        """Execute the metrics collection job (invoked by APScheduler).

        This method is called by the BackgroundTaskScheduler at regular intervals.
        It performs the following steps:
        1. Load worker from repository
        2. Query EC2 instance status
        3. Map EC2 state to CML worker status
        4. Collect CloudWatch metrics (if running)
        5. Update worker telemetry in database
        6. Emit metrics events to observers
        """
        # Ensure dependencies are injected
        assert (
            hasattr(self, "aws_ec2_client") and self.aws_ec2_client is not None
        ), "aws_ec2_client not injected"

        # Service provider should have been configured during job setup
        if not hasattr(self, "_service_provider") or not self._service_provider:
            logger.error(
                f"❌ Worker {self.worker_id}: service_provider not configured - job cannot execute"
            )
            # Try to reconfigure
            try:
                logger.info(f"🔧 Attempting to reconfigure worker {self.worker_id} job")
                self.configure()  # No service provider - will instantiate dependencies directly
                if not hasattr(self, "_service_provider") or not self._service_provider:
                    logger.warning(
                        f"⚠️ Worker {self.worker_id}: Still no service provider after reconfigure, continuing anyway"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Failed to reconfigure worker {self.worker_id} job: {e}"
                )
                return

        with tracer.start_as_current_span("collect_worker_metrics") as span:
            span.set_attribute("worker_id", self.worker_id)
            span.set_attribute("job_id", self.__task_id__ or "unknown")

            # Create a scope to access scoped services if service provider available
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

                # 1. Load worker from repository
                worker = await worker_repository.get_by_id_async(self.worker_id)
                if not worker:
                    logger.warning(
                        f"⚠️ Worker {self.worker_id} not found in repository - stopping job"
                    )
                    # Raise exception to signal APScheduler to stop this job
                    raise Exception(
                        f"Worker {self.worker_id} not found - terminating job"
                    )

                # Check if worker is terminated - stop monitoring if so
                if worker.state.status == CMLWorkerStatus.TERMINATED:
                    logger.info(
                        f"🛑 Worker {self.worker_id} is terminated - stopping monitoring job"
                    )
                    # Raise exception to signal APScheduler to stop this job
                    raise Exception(
                        f"Worker {self.worker_id} is terminated - stopping job"
                    )

                # Skip if worker doesn't have AWS instance
                if not worker.state.aws_instance_id:
                    logger.debug(
                        f"Worker {self.worker_id} has no AWS instance ID, skipping"
                    )
                    return

                span.set_attribute("aws_instance_id", worker.state.aws_instance_id)
                span.set_attribute("aws_region", worker.state.aws_region)

                # 2. Get EC2 instance status
                status_checks = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=AwsRegion(worker.state.aws_region),
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_checks:
                    logger.warning(
                        f"⚠️ Could not get EC2 status for instance {worker.state.aws_instance_id}"
                    )
                    return

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2_instance_state", ec2_state)

                # 3. Map EC2 state to CML status
                new_status = self._map_ec2_state_to_cml_status(ec2_state)

                # Update status if changed
                if new_status != worker.state.status:
                    logger.info(
                        f"🔄 Worker {self.worker_id} status changed: "
                        f"{worker.state.status.value} → {new_status.value}"
                    )
                    worker.update_status(new_status)
                    span.set_attribute("status_changed", True)

                # 4. Collect CloudWatch metrics (if running)
                metrics = None
                if new_status == CMLWorkerStatus.RUNNING:
                    try:
                        metrics = self.aws_ec2_client.get_instance_resources_utilization(
                            aws_region=AwsRegion(worker.state.aws_region),
                            instance_id=worker.state.aws_instance_id,
                            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
                        )

                        if metrics:
                            # Parse metric values
                            cpu_util = None
                            memory_util = None

                            if (
                                metrics.avg_cpu_utilization
                                and metrics.avg_cpu_utilization
                                != "unknown - enable CloudWatch..."
                            ):
                                try:
                                    cpu_util = float(metrics.avg_cpu_utilization)
                                except (ValueError, TypeError):
                                    pass

                            if (
                                metrics.avg_memory_utilization
                                and metrics.avg_memory_utilization
                                != "unknown - enable CloudWatch..."
                            ):
                                try:
                                    memory_util = float(metrics.avg_memory_utilization)
                                except (ValueError, TypeError):
                                    pass

                            # 5. Update worker telemetry
                            worker.update_telemetry(
                                cpu_utilization=cpu_util,
                                memory_utilization=memory_util,
                                active_labs_count=worker.state.cml_labs_count or 0,
                                last_activity_at=datetime.now(timezone.utc),
                            )

                            span.set_attribute("cpu_utilization", cpu_util or 0)
                            span.set_attribute("memory_utilization", memory_util or 0)

                    except Exception as e:
                        logger.error(
                            f"❌ Failed to collect CloudWatch metrics: {e}",
                            exc_info=True,
                        )

                # 6. Persist changes to repository
                await worker_repository.update_async(worker)

                # 7. Build metrics event payload
                metrics_data: Dict[str, Any] = {
                    "worker_id": self.worker_id,
                    "worker_name": worker.state.name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": new_status.value,
                    "status_checks": status_checks,
                    "instance_id": worker.state.aws_instance_id,
                    "region": worker.state.aws_region,
                    "metrics": None,
                }

                if metrics:
                    metrics_data["metrics"] = {
                        "cpu_utilization": metrics.avg_cpu_utilization,
                        "memory_utilization": metrics.avg_memory_utilization,
                        "start_time": metrics.start_time.isoformat(),
                        "end_time": metrics.end_time.isoformat(),
                    }

                # 8. Notify observers and notification handler
                # First notify old-style observers (for backwards compatibility)
                for observer in self._observers:
                    try:
                        observer(metrics_data)
                    except Exception as e:
                        logger.error(
                            f"❌ Observer failed to handle metrics: {e}", exc_info=True
                        )

                # Then notify the notification handler from service provider
                if (
                    hasattr(self, "_notification_handler")
                    and self._notification_handler
                ):
                    try:
                        self._notification_handler(metrics_data)
                    except Exception as e:
                        logger.error(
                            f"❌ WorkerNotificationHandler failed to handle metrics: {e}",
                            exc_info=True,
                        )

                logger.debug(
                    f"📊 Collected metrics for worker {self.worker_id}: "
                    f"status={new_status.value}, ec2_state={ec2_state}"
                )

            except Exception as e:
                logger.error(
                    f"❌ Failed to collect metrics for worker {self.worker_id}: {e}",
                    exc_info=True,
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise  # Let APScheduler handle retry logic
            finally:
                # Dispose the scope to release scoped services
                if scope:
                    scope.dispose()

    def _map_ec2_state_to_cml_status(self, ec2_state: str) -> CMLWorkerStatus:
        """Map EC2 instance state to CML Worker status.

        Args:
            ec2_state: EC2 instance state string (e.g., 'running', 'stopped')

        Returns:
            Corresponding CMLWorkerStatus enum value
        """
        state_mapping = {
            "running": CMLWorkerStatus.RUNNING,
            "stopped": CMLWorkerStatus.STOPPED,
            "stopping": CMLWorkerStatus.STOPPING,
            "pending": CMLWorkerStatus.PENDING,
            "shutting-down": CMLWorkerStatus.STOPPING,
            "terminated": CMLWorkerStatus.TERMINATED,
        }

        return state_mapping.get(ec2_state, CMLWorkerStatus.UNKNOWN)
