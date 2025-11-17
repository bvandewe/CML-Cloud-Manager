"""Worker monitoring scheduler using APScheduler for job management.

This service coordinates the worker monitoring system by:
- Managing WorkerMetricsCollectionJob instances via BackgroundTaskScheduler
- Auto-discovering active workers on startup
- Starting/stopping monitoring jobs based on worker lifecycle
- Coordinating metrics collection with notification handling

Uses the Neuroglia BackgroundTaskScheduler for distributed job management.
"""

import logging
from typing import Dict, Optional

from opentelemetry import trace

from application.services.background_scheduler import (BackgroundTasksBus,
                                                       RecurrentTaskDescriptor)
# Import WorkerMetricsCollectionJob for type resolution in BackgroundTaskScheduler
from application.services.worker_metrics_collection_job import \
    WorkerMetricsCollectionJob  # noqa: F401
from application.services.worker_notification_handler import WorkerNotificationHandler
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.aws_ec2_api_client import AwsEc2Client

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class WorkerMonitoringScheduler:
    """Manages worker monitoring jobs using BackgroundTaskScheduler.

    Central coordinator that:
    - Schedules WorkerMetricsCollectionJob instances for active workers
    - Auto-discovers active workers on startup
    - Starts/stops monitoring jobs via BackgroundTaskScheduler
    - Coordinates job instances with notification handler

    Attributes:
        _worker_repository: Repository for querying workers
        _aws_client: AWS EC2 API client for metrics
        _notification_handler: Handler for processing metrics events
        _background_task_bus: Bus for scheduling background jobs
        _poll_interval: Interval in seconds between metric collections
        _active_jobs: Registry of active job IDs by worker_id
        _is_running: Whether the scheduler is currently running
    """

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        aws_client: AwsEc2Client,
        notification_handler: WorkerNotificationHandler,
        background_task_bus: BackgroundTasksBus,
        background_task_scheduler,  # BackgroundTaskScheduler type hint causes circular import
        poll_interval: int = 300,
    ) -> None:
        """Initialize the monitoring scheduler.

        Args:
            worker_repository: Repository for worker queries
            aws_client: AWS EC2 API client
            notification_handler: Notification handler for metrics processing
            background_task_bus: BackgroundTasksBus for scheduling jobs
            background_task_scheduler: BackgroundTaskScheduler for stopping jobs
            poll_interval: Seconds between metric collections (default: 300 = 5 min)
        """
        self._worker_repository = worker_repository
        self._aws_client = aws_client
        self._notification_handler = notification_handler
        self._background_task_bus = background_task_bus
        self._background_task_scheduler = background_task_scheduler
        self._poll_interval = poll_interval
        self._active_jobs: Dict[str, str] = {}  # worker_id -> job_id mapping
        self._is_running = False

        logger.info(
            f"📅 WorkerMonitoringScheduler initialized (poll_interval={poll_interval}s)"
        )

    async def start_async(self) -> None:
        """Start the monitoring scheduler.

        Auto-discovers active workers and starts monitoring jobs for them.
        """
        if self._is_running:
            logger.warning("⚠️ Scheduler already running")
            return

        with tracer.start_as_current_span("start_monitoring_scheduler"):
            self._is_running = True
            logger.info("🚀 Starting worker monitoring scheduler...")

            # Auto-discover active workers
            await self._discover_active_workers_async()

            logger.info(
                f"✅ Scheduler started - monitoring {len(self._active_jobs)} workers"
            )

    async def stop_async(self) -> None:
        """Stop the monitoring scheduler.

        Stops all active monitoring jobs via the BackgroundTaskScheduler.
        """
        if not self._is_running:
            return

        with tracer.start_as_current_span("stop_monitoring_scheduler"):
            self._is_running = False
            logger.info("🛑 Stopping worker monitoring scheduler...")

            # Stop all monitoring jobs
            job_ids = list(self._active_jobs.keys())
            for worker_id in job_ids:
                await self.stop_monitoring_worker_async(worker_id)

            logger.info("✅ Scheduler stopped")

    async def start_monitoring_worker_async(self, worker_id: str) -> None:
        """Start monitoring a specific worker using BackgroundTaskScheduler.

        Creates a WorkerMetricsCollectionJob and schedules it via the BackgroundTasksBus.

        Args:
            worker_id: Worker aggregate ID to monitor
        """
        with tracer.start_as_current_span(
            "start_monitoring_worker",
            attributes={"worker_id": worker_id},
        ):
            # Generate unique job ID
            job_id = f"worker-metrics-{worker_id}"

            # Check if already monitoring (in-memory registry)
            if worker_id in self._active_jobs:
                logger.debug(f"Already monitoring worker {worker_id} (in-memory registry)")
                return

            # Check if job already exists in scheduler (after restart)
            try:
                existing_job = self._background_task_scheduler.get_job(job_id)
                if existing_job:
                    logger.info(f"📋 Job {job_id} already exists in scheduler, registering in memory")
                    self._active_jobs[worker_id] = job_id
                    return
            except Exception as e:
                logger.debug(f"Could not check for existing job {job_id}: {e}")

            # Load worker to verify it's active
            worker = await self._load_worker_async(worker_id)
            if not worker:
                logger.warning(f"⚠️ Worker {worker_id} not found, cannot monitor")
                return

            # Only monitor active workers
            if worker.state.status not in [
                CMLWorkerStatus.RUNNING,
                CMLWorkerStatus.PENDING,
            ]:
                logger.debug(
                    f"Worker {worker_id} not in active state ({worker.state.status.value}), skipping monitoring"
                )
                return

            # Create task descriptor for scheduling
            # Only serialize minimal data (worker_id) - dependencies will be re-injected via configure()
            # The actual job instance will be created by BackgroundTaskScheduler during deserialization
            task_descriptor = RecurrentTaskDescriptor(
                id=job_id,
                name="WorkerMetricsCollectionJob",
                data={"worker_id": worker_id},  # Only serialize worker_id
                interval=self._poll_interval,
            )

            # Schedule the job via BackgroundTasksBus
            self._background_task_bus.schedule_task(task_descriptor)

            # Track active job
            self._active_jobs[worker_id] = job_id

            logger.info(f"✅ Started monitoring worker: {worker_id} (job_id: {job_id})")

    async def stop_monitoring_worker_async(self, worker_id: str) -> None:
        """Stop monitoring a specific worker.

        Stops the scheduled job via the BackgroundTaskScheduler.

        Args:
            worker_id: Worker aggregate ID to stop monitoring
        """
        with tracer.start_as_current_span(
            "stop_monitoring_worker",
            attributes={"worker_id": worker_id},
        ):
            job_id = self._active_jobs.get(worker_id)
            if not job_id:
                logger.debug(f"No active job for worker {worker_id}")
                return

            # Stop the job via BackgroundTaskScheduler
            try:
                success = self._background_task_scheduler.stop_task(job_id)
                if success:
                    logger.info(
                        f"🛑 Stopped monitoring worker: {worker_id} (job_id: {job_id})"
                    )
                else:
                    logger.warning(
                        f"⚠️ Failed to stop job {job_id} for worker {worker_id}"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Error stopping job {job_id} for worker {worker_id}: {e}"
                )
            finally:
                # Remove from registry even if stop failed (to allow retry)
                del self._active_jobs[worker_id]

    async def _discover_active_workers_async(self) -> None:
        """Discover and start monitoring all active workers.

        Queries the repository for active workers (RUNNING or PENDING state)
        and starts monitoring for each.
        """
        with tracer.start_as_current_span("discover_active_workers"):
            logger.info("🔍 Discovering active workers...")

            try:
                # Get all active workers (using existing repository method)
                workers = await self._worker_repository.get_active_workers_async()

                logger.info(f"Found {len(workers)} active workers")

                # Start monitoring for each
                for worker in workers:
                    try:
                        # Only monitor RUNNING or PENDING workers
                        if worker.state.status in [
                            CMLWorkerStatus.RUNNING,
                            CMLWorkerStatus.PENDING,
                        ]:
                            await self.start_monitoring_worker_async(worker.id())
                    except Exception as e:
                        logger.error(
                            f"❌ Failed to start monitoring worker {worker.id()}: {e}",
                            exc_info=True,
                        )

            except Exception as e:
                logger.error(
                    f"❌ Failed to discover active workers: {e}",
                    exc_info=True,
                )

    async def _load_worker_async(self, worker_id: str) -> Optional[CMLWorker]:
        """Load a worker by ID.

        Args:
            worker_id: Worker aggregate ID

        Returns:
            Worker aggregate or None if not found
        """
        try:
            return await self._worker_repository.get_by_id_async(worker_id)
        except Exception as e:
            logger.error(f"❌ Failed to load worker {worker_id}: {e}")
            return None

    def get_active_jobs(self) -> list[str]:
        """Get list of worker IDs currently being monitored.

        Returns:
            List of worker IDs with active monitoring jobs
        """
        return list(self._active_jobs.keys())

    def is_monitoring_worker(self, worker_id: str) -> bool:
        """Check if a worker is currently being monitored.

        Args:
            worker_id: Worker aggregate ID

        Returns:
            True if worker has an active monitoring job
        """
        return worker_id in self._active_jobs
