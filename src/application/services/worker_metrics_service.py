"""Worker metrics collection service.

Centralized service for collecting worker metrics from AWS sources.
Shared by RefreshWorkerMetricsCommand (on-demand) and WorkerMetricsCollectionJob (scheduled).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from opentelemetry import trace

from application.services.background_scheduler import BackgroundTaskScheduler
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

if TYPE_CHECKING:
    from neuroglia.hosting.web import WebApplicationBuilder

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class MetricsResult:
    """Result of metrics collection operation."""

    worker_id: str
    status_updated: bool
    ec2_state: str
    cpu_utilization: float | None = None
    memory_utilization: float | None = None
    metrics_collected: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "worker_id": self.worker_id,
            "status_updated": self.status_updated,
            "ec2_state": self.ec2_state,
            "cpu_utilization": self.cpu_utilization,
            "memory_utilization": self.memory_utilization,
            "metrics_collected": self.metrics_collected,
            "error": self.error,
        }


class WorkerMetricsService:
    """Service for collecting worker metrics from AWS.

    This service encapsulates the logic for:
    - Querying AWS EC2 instance status
    - Collecting CloudWatch metrics
    - Mapping EC2 states to CML worker states
    - Updating worker aggregate state

    Used by both on-demand commands and scheduled background jobs.
    """

    def __init__(
        self,
        aws_ec2_client: AwsEc2Client,
        background_task_scheduler: BackgroundTaskScheduler | None = None,
    ):
        """Initialize the metrics service.

        Args:
            aws_ec2_client: AWS EC2 client for querying instance data
            background_task_scheduler: Optional scheduler to query actual next run times
        """
        self._aws_client = aws_ec2_client
        self._scheduler = background_task_scheduler

    @staticmethod
    def configure(builder: "WebApplicationBuilder") -> None:
        """Configure the metrics service in the application builder.

        Args:
            builder: Application builder instance
        """

        def create_service(service_provider):
            """Factory to create WorkerMetricsService with dependencies."""
            aws_client = service_provider.get_required_service(AwsEc2Client)
            scheduler = service_provider.get_required_service(BackgroundTaskScheduler)
            return WorkerMetricsService(aws_client, scheduler)

        # Register as singleton with factory function (no singleton= parameter)
        builder.services.add_singleton(WorkerMetricsService, create_service)
        logger.info("✅ WorkerMetricsService configured as singleton")

    async def collect_worker_metrics(
        self,
        worker: CMLWorker,
        collect_cloudwatch: bool = True,
    ) -> MetricsResult:
        """Collect metrics for a single worker from AWS.

        Args:
            worker: CMLWorker entity to update
            collect_cloudwatch: Whether to collect CloudWatch metrics (slower)

        Returns:
            MetricsResult with collected data and update status
        """
        with tracer.start_as_current_span(
            "collect_worker_metrics",
            attributes={
                "worker_id": worker.id(),
                "worker_name": worker.state.name,
                "collect_cloudwatch": collect_cloudwatch,
            },
        ) as span:
            try:
                # Validate worker has AWS instance
                if not worker.state.aws_instance_id:
                    return MetricsResult(
                        worker_id=worker.id(),
                        status_updated=False,
                        ec2_state="unknown",
                        error="No AWS instance ID",
                    )

                # Skip terminated workers
                if worker.state.status == CMLWorkerStatus.TERMINATED:
                    return MetricsResult(
                        worker_id=worker.id(),
                        status_updated=False,
                        ec2_state="terminated",
                        error="Worker already terminated",
                    )

                aws_region = AwsRegion(worker.state.aws_region)
                span.set_attribute("aws_instance_id", worker.state.aws_instance_id)
                span.set_attribute("aws_region", worker.state.aws_region)

                # 1. Query EC2 instance status
                status_checks = self._aws_client.get_instance_status_checks(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_checks:
                    return MetricsResult(
                        worker_id=worker.id(),
                        status_updated=False,
                        ec2_state="unknown",
                        error=f"EC2 instance {worker.state.aws_instance_id} not found",
                    )

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2_instance_state", ec2_state)

                # 2. Update EC2 health metrics
                worker.update_ec2_metrics(
                    instance_state_detail=status_checks["instance_status_check"],
                    system_status_check=status_checks["ec2_system_status_check"],
                )

                # 3. Map EC2 state to CML status
                new_status = self._map_ec2_state_to_cml_status(ec2_state)
                old_status = worker.state.status

                # Update status if changed
                status_updated = False
                if new_status != old_status:
                    worker.update_status(new_status)
                    status_updated = True
                    span.set_attribute("status_changed", True)
                    span.set_attribute("old_status", old_status.value)
                    span.set_attribute("new_status", new_status.value)
                    logger.info(
                        f"🔄 Worker {worker.id()} status changed: "
                        f"{old_status.value} → {new_status.value}"
                    )

                # 4. Collect CloudWatch metrics (if enabled and running)
                cpu_util = None
                memory_util = None
                metrics_collected = False

                if collect_cloudwatch and new_status == CMLWorkerStatus.RUNNING:
                    try:
                        metrics = self._aws_client.get_instance_resources_utilization(
                            aws_region=aws_region,
                            instance_id=worker.state.aws_instance_id,
                            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
                        )

                        if metrics:
                            # Parse metric values
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

                            # Calculate next refresh time for countdown timer
                            # Get the actual next run time from APScheduler (if available)
                            from application.settings import app_settings

                            poll_interval = app_settings.worker_metrics_poll_interval

                            # Try to get actual next run time from scheduler
                            next_refresh_at = None
                            if self._scheduler:
                                try:
                                    job = self._scheduler.get_job(
                                        "WorkerMetricsCollectionJob"
                                    )
                                    if job and job.next_run_time:
                                        # Use APScheduler's scheduled next run time (already in UTC)
                                        next_refresh_at = job.next_run_time.replace(
                                            tzinfo=timezone.utc
                                        )
                                        logger.debug(
                                            f"Using APScheduler next_run_time: {next_refresh_at.isoformat()}"
                                        )
                                except Exception as e:
                                    logger.debug(
                                        f"Could not get next run time from scheduler: {e}"
                                    )

                            # Fallback: calculate from current time + interval
                            if next_refresh_at is None:
                                next_refresh_at = datetime.now(
                                    timezone.utc
                                ) + timedelta(seconds=poll_interval)
                                logger.debug(
                                    f"Using fallback next_refresh_at: {next_refresh_at.isoformat()}"
                                )

                            # Update worker telemetry with timing info
                            # Always update timing even if no metrics data, so UI countdown works
                            if cpu_util is not None or memory_util is not None:
                                worker.update_telemetry(
                                    cpu_utilization=cpu_util,
                                    memory_utilization=memory_util,
                                    active_labs_count=worker.state.cml_labs_count or 0,
                                    last_activity_at=datetime.now(timezone.utc),
                                    poll_interval=poll_interval,
                                    next_refresh_at=next_refresh_at,
                                )
                            else:
                                # No metrics data yet, but still update timing for countdown
                                worker.update_telemetry(
                                    cpu_utilization=None,
                                    memory_utilization=None,
                                    active_labs_count=worker.state.cml_labs_count or 0,
                                    last_activity_at=datetime.now(timezone.utc),
                                    poll_interval=poll_interval,
                                    next_refresh_at=next_refresh_at,
                                )
                                metrics_collected = True

                                span.set_attribute("cpu_utilization", cpu_util or 0)
                                span.set_attribute(
                                    "memory_utilization", memory_util or 0
                                )

                    except Exception as e:
                        logger.warning(
                            f"Failed to collect CloudWatch metrics for worker {worker.id()}: {e}"
                        )
                        # Don't fail entire operation on CloudWatch errors

                return MetricsResult(
                    worker_id=worker.id(),
                    status_updated=status_updated,
                    ec2_state=ec2_state,
                    cpu_utilization=cpu_util,
                    memory_utilization=memory_util,
                    metrics_collected=metrics_collected,
                )

            except Exception as e:
                logger.error(
                    f"Failed to collect metrics for worker {worker.id()}: {e}",
                    exc_info=True,
                )
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                return MetricsResult(
                    worker_id=worker.id(),
                    status_updated=False,
                    ec2_state="error",
                    error=str(e),
                )

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
        return state_mapping.get(ec2_state, CMLWorkerStatus.UNKNOWN)
        return state_mapping.get(ec2_state, CMLWorkerStatus.UNKNOWN)
        return state_mapping.get(ec2_state, CMLWorkerStatus.UNKNOWN)
