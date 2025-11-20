"""Refresh Worker Metrics command with handler.

This command orchestrates collecting fresh metrics from AWS and CML for a worker
by coordinating three focused sub-commands via the Mediator. This follows the
Single Responsibility Principle while maintaining backward compatibility.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.services.background_scheduler import BackgroundTaskScheduler
from application.settings import app_settings
from infrastructure.services.worker_refresh_throttle import WorkerRefreshThrottle
from observability.metrics import meter

from .collect_worker_cloudwatch_metrics_command import (
    CollectWorkerCloudWatchMetricsCommand,
)
from .command_handler_base import CommandHandlerBase
from .sync_worker_cml_data_command import SyncWorkerCMLDataCommand
from .sync_worker_ec2_status_command import SyncWorkerEC2StatusCommand

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# OTEL Gauges for worker metrics (kept for backward compatibility)
_worker_cpu_gauge = meter.create_gauge(
    name="cml.worker.cpu_utilization",
    description="Worker CPU utilization percentage",
    unit="%",
)

_worker_memory_gauge = meter.create_gauge(
    name="cml.worker.memory_utilization",
    description="Worker memory utilization percentage",
    unit="%",
)

_worker_labs_gauge = meter.create_gauge(
    name="cml.worker.labs_count",
    description="Number of active labs on worker",
    unit="1",
)

_worker_status_gauge = meter.create_gauge(
    name="cml.worker.status",
    description="Worker status (0=pending, 1=running, 2=stopped, 3=terminated)",
    unit="1",
)


@dataclass
class RefreshWorkerMetricsCommand(Command[OperationResult[dict]]):
    """Command to refresh worker metrics from AWS and CML.

    This command orchestrates focused sub-commands to refresh worker metrics:
    1. SyncWorkerEC2StatusCommand - EC2 instance state and details
    2. CollectWorkerCloudWatchMetricsCommand - CloudWatch CPU/memory metrics
    3. SyncWorkerCMLDataCommand - CML service health, version, stats, licensing

    Note: Labs refresh should be orchestrated separately via RefreshWorkerLabsCommand.

    Returns dict with aggregated refresh summary.
    """

    worker_id: str
    force: bool = False  # Bypass throttle (for user-initiated on-demand refreshes)
    initiated_by: str = "user"  # "user" or "background_job" - for throttle logic


class RefreshWorkerMetricsCommandHandler(
    CommandHandlerBase,
    CommandHandler[RefreshWorkerMetricsCommand, OperationResult[dict]],
):
    """Handle worker refresh by orchestrating focused sub-commands for metadata and metrics."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        refresh_throttle: WorkerRefreshThrottle,
        background_task_scheduler: BackgroundTaskScheduler,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self._refresh_throttle = refresh_throttle
        self._background_task_scheduler = background_task_scheduler

    async def handle_async(self, request: RefreshWorkerMetricsCommand) -> OperationResult[dict]:
        """Handle refresh worker command by orchestrating sub-commands.

        Refreshes EC2 status, CloudWatch metrics, and CML data.
        Labs refresh should be handled separately.

        Args:
            request: Refresh command with worker ID

        Returns:
            OperationResult with aggregated refresh summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "refresh_worker_orchestration",
            }
        )

        try:
            # Rate-limiting: Check if refresh is allowed (only for user-initiated requests)
            # Background jobs bypass throttle to ensure regular data collection
            is_user_request = command.initiated_by == "user"

            if is_user_request and not command.force and not self._refresh_throttle.can_refresh(command.worker_id):
                retry_after = self._refresh_throttle.get_time_until_next_refresh(command.worker_id)
                log.info(f"Refresh throttled for worker {command.worker_id} - " f"retry after {retry_after:.1f}s")
                return self.ok(
                    {
                        "worker_id": command.worker_id,
                        "refresh_skipped": True,
                        "reason": "rate_limited",
                        "retry_after_seconds": retry_after,
                        "last_refresh_at": (
                            self._refresh_throttle.get_last_refresh(command.worker_id).isoformat()
                            if self._refresh_throttle.get_last_refresh(command.worker_id)
                            else None
                        ),
                    }
                )

            # Check if global background job is imminent
            global_job = self._background_task_scheduler.get_job("WorkerMetricsCollectionJob")
            if global_job and global_job.next_run_time:
                now_utc = datetime.now(timezone.utc)
                next_run_utc = global_job.next_run_time.replace(tzinfo=timezone.utc)
                time_until_job = (next_run_utc - now_utc).total_seconds()

                if 0 < time_until_job <= app_settings.worker_refresh_check_upcoming_job_threshold:
                    log.info(
                        f"Skipping manual refresh for worker {command.worker_id} - "
                        f"background job scheduled in {time_until_job:.1f}s"
                    )
                    return self.ok(
                        {
                            "worker_id": command.worker_id,
                            "refresh_skipped": True,
                            "reason": "background_job_imminent",
                            "next_background_job_at": global_job.next_run_time.isoformat(),
                            "seconds_until_background_job": time_until_job,
                        }
                    )

            # Record refresh attempt (only for user requests to prevent background jobs from blocking user refreshes)
            if is_user_request:
                self._refresh_throttle.record_refresh(command.worker_id)

            results = {}

            # 1. Sync EC2 status (always run first)
            with tracer.start_as_current_span("sync_ec2_status") as span:
                log.debug(f"Orchestrating EC2 status sync for worker {command.worker_id}")
                ec2_result = await self.mediator.execute_async(SyncWorkerEC2StatusCommand(worker_id=command.worker_id))

                if ec2_result.status == 200:
                    results["ec2_sync"] = ec2_result.data
                    span.set_attribute("ec2_sync.success", True)
                else:
                    log.warning(f"EC2 status sync failed for worker {command.worker_id}: {ec2_result.detail}")
                    span.set_attribute("ec2_sync.success", False)
                    results["ec2_sync"] = {
                        "success": False,
                        "error": ec2_result.detail,
                    }

            # 2. Collect CloudWatch metrics (only if EC2 sync successful)
            if results.get("ec2_sync", {}).get("worker_status") == "running":
                with tracer.start_as_current_span("collect_cloudwatch_metrics") as span:
                    log.debug(f"Orchestrating CloudWatch metrics collection for worker {command.worker_id}")
                    cloudwatch_result = await self.mediator.execute_async(
                        CollectWorkerCloudWatchMetricsCommand(worker_id=command.worker_id)
                    )

                    if cloudwatch_result.status == 200:
                        results["cloudwatch_metrics"] = cloudwatch_result.data
                        span.set_attribute("cloudwatch_metrics.success", True)

                        # Update OTEL metrics gauges with CloudWatch data
                        metrics = cloudwatch_result.data.get("metrics", {})
                        if metrics.get("cpu_utilization") is not None:
                            _worker_cpu_gauge.set(
                                metrics["cpu_utilization"],
                                {"worker_id": command.worker_id},
                            )
                        if metrics.get("memory_utilization") is not None:
                            _worker_memory_gauge.set(
                                metrics["memory_utilization"],
                                {"worker_id": command.worker_id},
                            )
                    else:
                        log.warning(
                            f"CloudWatch metrics collection failed for worker {command.worker_id}: {cloudwatch_result.detail}"
                        )
                        span.set_attribute("cloudwatch_metrics.success", False)
                        results["cloudwatch_metrics"] = {
                            "success": False,
                            "error": cloudwatch_result.detail,
                        }
            else:
                log.debug(f"Skipping CloudWatch metrics for worker {command.worker_id} - not running")
                results["cloudwatch_metrics"] = {
                    "skipped": True,
                    "reason": "Worker not running",
                }

            # 3. Sync CML data (only if worker is running and has endpoint)
            if results.get("ec2_sync", {}).get("worker_status") == "running":
                with tracer.start_as_current_span("sync_cml_data") as span:
                    log.debug(f"Orchestrating CML data sync for worker {command.worker_id}")
                    cml_result = await self.mediator.execute_async(
                        SyncWorkerCMLDataCommand(worker_id=command.worker_id)
                    )

                    if cml_result.status == 200:
                        results["cml_sync"] = cml_result.data
                        span.set_attribute("cml_sync.success", True)

                        # Update OTEL metrics gauges with CML data
                        cml_data = cml_result.data
                        if cml_data.get("labs_count") is not None:
                            _worker_labs_gauge.set(
                                cml_data["labs_count"],
                                {"worker_id": command.worker_id},
                            )
                    else:
                        log.warning(f"CML data sync failed for worker {command.worker_id}: {cml_result.detail}")
                        span.set_attribute("cml_sync.success", False)
                        results["cml_sync"] = {
                            "success": False,
                            "error": cml_result.detail,
                        }
            else:
                log.debug(f"Skipping CML data sync for worker {command.worker_id} - not running")
                results["cml_sync"] = {
                    "skipped": True,
                    "reason": "Worker not running",
                }

            # 4. Update worker status gauge
            ec2_sync = results.get("ec2_sync", {})
            if ec2_sync.get("worker_status"):
                status_map = {
                    "pending": 0,
                    "running": 1,
                    "stopped": 2,
                    "terminated": 3,
                }
                status_value = status_map.get(ec2_sync["worker_status"], -1)
                if status_value >= 0:
                    _worker_status_gauge.set(
                        status_value,
                        {"worker_id": command.worker_id},
                    )

            # 5. Build aggregated result
            aggregated_result = {
                "worker_id": command.worker_id,
                "refresh_timestamp": (trace.get_current_span().start_time if trace.get_current_span() else None),
                "operations": results,
                "overall_success": all(
                    r.get("success", True) is not False
                    for r in results.values()
                    if isinstance(r, dict) and not r.get("skipped")
                ),
            }

            log.info(
                f"Completed worker refresh orchestration for worker {command.worker_id}: "
                f"overall_success={aggregated_result['overall_success']}"
            )

            return self.ok(aggregated_result)

        except Exception as ex:
            log.error(
                f"Failed to orchestrate worker refresh for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"Failed to orchestrate worker refresh: {str(ex)}")
