"""Worker metrics collector using APScheduler for periodic polling.

This module implements a metrics collector that is invoked by APScheduler jobs
to poll AWS EC2 and CloudWatch APIs at regular intervals. The collector is designed
to be job-friendly without managing its own async loops.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import trace

from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class WorkerMetricsCollector:
    """Reactive metrics collector for a single CML Worker.

    This service polls AWS EC2 and CloudWatch APIs at regular intervals to:
    - Sync worker status with EC2 instance state
    - Collect CPU/memory utilization metrics
    - Check instance health status
    - Detect configuration drift

    The collector automatically starts when created and stops when the worker
    is terminated or the collector is explicitly stopped.

    Attributes:
        worker_id: UUID of the CML Worker being monitored
        aws_ec2_client: AWS EC2 API client for querying instance details
        worker_repository: Repository for persisting worker state changes
        poll_interval: Seconds between metric collection cycles (default: 300)
    """

    def __init__(
        self,
        worker_id: str,
        aws_ec2_client: AwsEc2Client,
        worker_repository: CMLWorkerRepository,
        poll_interval_seconds: int = 300,
    ):
        """Initialize the metrics collector.

        Args:
            worker_id: UUID of the worker to monitor
            aws_ec2_client: AWS EC2 client instance
            worker_repository: Worker repository instance
            poll_interval_seconds: Polling interval in seconds (default: 300 = 5 minutes)
        """
        self.worker_id = worker_id
        self.aws_ec2_client = aws_ec2_client
        self.worker_repository = worker_repository
        self.poll_interval = poll_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._observers: List[Callable[[Dict[str, Any]], None]] = []

    def subscribe(self, observer: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to metrics updates.

        Args:
            observer: Callback function that receives metrics data
        """
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: Callable[[Dict[str, Any]], None]) -> None:
        """Unsubscribe from metrics updates.

        Args:
            observer: Callback function to remove
        """
        if observer in self._observers:
            self._observers.remove(observer)

    async def start_async(self) -> None:
        """Start the metrics collection loop.

        Creates an async task that runs the collection loop at regular intervals.
        If already running, this method does nothing.
        """
        if self._running:
            logger.debug(
                f"Metrics collector for worker {self.worker_id} already running"
            )
            return

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info(f"✅ Started metrics collection for worker {self.worker_id}")

    async def stop_async(self) -> None:
        """Stop the metrics collection loop.

        Cancels the collection task and waits for it to complete gracefully.
        Safe to call multiple times.
        """
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"⏹️  Stopped metrics collection for worker {self.worker_id}")

    async def _collect_loop(self) -> None:
        """Main collection loop - runs periodically.

        Continuously collects metrics at the configured interval until stopped.
        Handles errors gracefully to avoid stopping the loop on transient failures.
        """
        while self._running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info(f"Metrics collection cancelled for worker {self.worker_id}")
                break
            except Exception as e:
                logger.error(
                    f"Error collecting metrics for worker {self.worker_id}: {e}",
                    exc_info=True,
                )
                # Continue after error with same interval
                await asyncio.sleep(self.poll_interval)

    async def _collect_metrics(self) -> None:
        """Collect metrics for this worker.

        Performs the following operations:
        1. Retrieve worker from repository
        2. Query EC2 instance status
        3. Map EC2 state to worker status
        4. Collect CloudWatch metrics (if running)
        5. Update worker telemetry
        6. Persist changes to repository
        7. Emit metrics to observers

        If the worker is not found or terminated, the collector stops itself.
        """
        with tracer.start_as_current_span("collect_worker_metrics") as span:
            span.set_attribute("worker.id", self.worker_id)

            # 1. Retrieve worker
            worker = await self.worker_repository.get_by_id_async(self.worker_id)
            if not worker:
                logger.warning(f"Worker {self.worker_id} not found, stopping collector")
                await self.stop_async()
                return

            # Validate worker has AWS instance ID
            if not worker.state.aws_instance_id:
                logger.warning(
                    f"Worker {self.worker_id} has no AWS instance ID, stopping collector"
                )
                await self.stop_async()
                return

            span.set_attribute("worker.aws_instance_id", worker.state.aws_instance_id)
            span.set_attribute("worker.aws_region", worker.state.aws_region)

            # Skip if worker is terminated
            if worker.state.status == CMLWorkerStatus.TERMINATED:
                logger.info(
                    f"Worker {self.worker_id} is terminated, stopping collector"
                )
                await self.stop_async()
                return

            try:
                # 2. Query EC2 instance status
                status_checks = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=AwsRegion(worker.state.aws_region),
                    instance_id=worker.state.aws_instance_id,
                )

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2.instance_state", ec2_state)

                # 3. Map EC2 state to worker status
                new_status = self._map_ec2_state_to_worker_status(ec2_state)

                if new_status != worker.state.status:
                    logger.info(
                        f"Worker {self.worker_id} status changed: "
                        f"{worker.state.status.value} → {new_status.value}"
                    )
                    worker.update_status(new_status)
                    span.set_attribute("worker.status_changed", True)

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
                                active_labs_count=worker.state.cml_labs_count,
                                last_activity_at=datetime.now(timezone.utc),
                            )

                            span.set_attribute("metrics.cpu_utilization", cpu_util or 0)
                            span.set_attribute(
                                "metrics.memory_utilization", memory_util or 0
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to collect CloudWatch metrics for worker {self.worker_id}: {e}"
                        )

                # 6. Persist changes to repository (publishes domain events)
                await self.worker_repository.update_async(worker)

                # 7. Emit metrics to observers
                metrics_data: Dict[str, Any] = {
                    "worker_id": self.worker_id,
                    "status": new_status.value,
                    "status_checks": status_checks,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                if metrics:
                    metrics_data["metrics"] = {
                        "cpu_utilization": metrics.avg_cpu_utilization,
                        "memory_utilization": metrics.avg_memory_utilization,
                        "start_time": metrics.start_time.isoformat(),
                        "end_time": metrics.end_time.isoformat(),
                    }

                # Notify all observers (synchronous callbacks)
                for observer in self._observers:
                    observer(metrics_data)

                logger.debug(
                    f"📊 Collected metrics for worker {self.worker_id}: "
                    f"status={new_status.value}, ec2_state={ec2_state}"
                )

            except Exception as e:
                logger.error(
                    f"Error during metrics collection for worker {self.worker_id}: {e}",
                    exc_info=True,
                )
                raise

    def _map_ec2_state_to_worker_status(self, ec2_state: str) -> CMLWorkerStatus:
        """Map EC2 instance state to CML worker status.

        Args:
            ec2_state: EC2 instance state (running, stopped, pending, etc.)

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
