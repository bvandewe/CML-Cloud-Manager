"""Refresh Worker Metrics command with handler.

This command orchestrates collecting fresh metrics from AWS for a worker
and updating the worker aggregate state. It's the single source of truth
for worker metrics refresh logic.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import \
    CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import (AwsRegion,
                               Ec2InstanceResourcesUtilizationRelativeStartTime)
from integration.exceptions import IntegrationException
from integration.services.aws_ec2_api_client import AwsEc2Client
from observability.metrics import meter

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# OTEL Gauges for worker metrics
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
    """Command to refresh worker metrics from AWS.

    This command:
    1. Queries AWS EC2 for current instance state
    2. Queries AWS CloudWatch for CPU/memory metrics
    3. Updates worker aggregate with latest data
    4. Updates OTEL metrics gauges
    5. Publishes domain events for state changes

    Returns dict with refreshed metrics summary.
    """

    worker_id: str


class RefreshWorkerMetricsCommandHandler(
    CommandHandlerBase,
    CommandHandler[RefreshWorkerMetricsCommand, OperationResult[dict]],
):
    """Handle worker metrics refresh from AWS sources."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client

    async def handle_async(
        self, request: RefreshWorkerMetricsCommand
    ) -> OperationResult[dict]:
        """Handle refresh worker metrics command.

        Args:
            request: Refresh command with worker ID

        Returns:
            OperationResult with metrics summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "refresh_metrics",
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # 1. Load worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(
                    command.worker_id
                )

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                if not worker.state.aws_instance_id:
                    error_msg = (
                        f"CML Worker {command.worker_id} has no AWS instance assigned"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id)
                span.set_attribute(
                    "cml_worker.current_status", worker.state.status.value
                )

            # 2. Query AWS EC2 for current instance status
            with tracer.start_as_current_span("query_ec2_instance_status") as span:
                aws_region = AwsRegion(worker.state.aws_region)

                status_checks = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_checks:
                    error_msg = f"EC2 instance {worker.state.aws_instance_id} not found in AWS"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2.current_state", ec2_state)

                # Update EC2 health metrics
                worker.update_ec2_metrics(
                    instance_state_detail=status_checks["instance_status_check"],
                    system_status_check=status_checks["ec2_system_status_check"],
                )

                # Check CloudWatch detailed monitoring status
                monitoring_state = status_checks.get("monitoring_state", "disabled")
                monitoring_enabled = monitoring_state == "enabled"

                # Update worker monitoring status if changed
                if worker.state.cloudwatch_detailed_monitoring_enabled != monitoring_enabled:
                    worker.update_cloudwatch_monitoring(monitoring_enabled)
                    log.info(
                        f"Worker {command.worker_id} CloudWatch monitoring status updated: {monitoring_state}"
                    )

                # Map EC2 state to worker status
                ec2_state_to_worker_status = {
                    "pending": CMLWorkerStatus.PENDING,
                    "running": CMLWorkerStatus.RUNNING,
                    "stopping": CMLWorkerStatus.STOPPING,
                    "stopped": CMLWorkerStatus.STOPPED,
                    "shutting-down": CMLWorkerStatus.TERMINATED,
                    "terminated": CMLWorkerStatus.TERMINATED,
                }
                new_status = ec2_state_to_worker_status.get(
                    ec2_state, CMLWorkerStatus.PENDING
                )

                # Update worker status if changed
                status_changed = worker.update_status(new_status)
                if status_changed:
                    log.info(
                        f"Worker {command.worker_id} status updated: {worker.state.status.value}"
                    )

            # 3. Query AWS CloudWatch for metrics (only if running)
            metrics_summary = {}
            if new_status == CMLWorkerStatus.RUNNING:
                with tracer.start_as_current_span("query_cloudwatch_metrics") as span:
                    try:
                        metrics = self.aws_ec2_client.get_instance_resources_utilization(
                            aws_region=aws_region,
                            instance_id=worker.state.aws_instance_id,
                            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
                        )

                        if metrics:
                            # Parse metrics values - handle error strings from CloudWatch
                            try:
                                cpu_value = float(metrics.avg_cpu_utilization)
                                memory_value = float(metrics.avg_memory_utilization)
                            except (ValueError, TypeError):
                                log.warning(
                                    f"CloudWatch returned non-numeric metrics for worker {command.worker_id}: "
                                    f"CPU={metrics.avg_cpu_utilization}, Memory={metrics.avg_memory_utilization}"
                                )
                                # Skip telemetry update if metrics are invalid
                            else:
                                # Update CloudWatch metrics with source-specific method
                                worker.update_cloudwatch_metrics(
                                    cpu_utilization=cpu_value,
                                    memory_utilization=memory_value,
                                )

                                metrics_summary = {
                                    "cpu_utilization": metrics.avg_cpu_utilization,
                                    "memory_utilization": metrics.avg_memory_utilization,
                                    "start_time": metrics.start_time.isoformat(),
                                    "end_time": metrics.end_time.isoformat(),
                                }

                                span.set_attribute("metrics.cpu", cpu_value)
                                span.set_attribute("metrics.memory", memory_value)

                                log.info(
                                    f"Worker {command.worker_id} metrics: CPU={cpu_value}%, Memory={memory_value}%"
                                )
                    except IntegrationException as e:
                        log.warning(
                            f"Failed to collect CloudWatch metrics for worker {command.worker_id}: {e}"
                        )
                        # Continue anyway - not critical

            # 4. Persist worker aggregate (publishes domain events)
            with tracer.start_as_current_span("persist_worker") as span:
                await self.cml_worker_repository.update_async(worker)
                span.set_attribute("worker.persisted", True)

                log.info(f"✅ Worker {command.worker_id} state persisted to repository")

            # 5. Update OTEL metrics
            with tracer.start_as_current_span("update_otel_metrics"):
                metric_attributes = {
                    "worker_id": command.worker_id,
                    "region": worker.state.aws_region,
                    "worker_name": worker.state.name,
                }

                # Status gauge (numeric mapping)
                status_value_map = {
                    CMLWorkerStatus.PENDING: 0,
                    CMLWorkerStatus.RUNNING: 1,
                    CMLWorkerStatus.STOPPING: 2,
                    CMLWorkerStatus.STOPPED: 3,
                    CMLWorkerStatus.TERMINATED: 4,
                }
                _worker_status_gauge.set(
                    status_value_map.get(worker.state.status, 0), metric_attributes
                )

                # CPU/Memory gauges (from CloudWatch)
                if worker.state.cloudwatch_cpu_utilization is not None:
                    _worker_cpu_gauge.set(
                        worker.state.cloudwatch_cpu_utilization, metric_attributes
                    )

                if worker.state.cloudwatch_memory_utilization is not None:
                    _worker_memory_gauge.set(
                        worker.state.cloudwatch_memory_utilization, metric_attributes
                    )

                # Labs gauge (from CML API)
                _worker_labs_gauge.set(worker.state.cml_labs_count, metric_attributes)

                log.debug(f"OTEL metrics updated for worker {command.worker_id}")

            # 6. Build response summary
            response = {
                "worker_id": command.worker_id,
                "status": worker.state.status.value,
                "public_ip": worker.state.public_ip,
                "private_ip": worker.state.private_ip,
                "cpu_utilization": worker.state.cpu_utilization,
                "memory_utilization": worker.state.memory_utilization,
                "active_labs_count": worker.state.active_labs_count,
                "https_endpoint": worker.state.https_endpoint,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics_summary,
            }

            log.info(f"✅ Metrics refresh completed for worker {command.worker_id}")
            return self.ok(response)

        except IntegrationException as ex:
            log.error(
                f"AWS integration error refreshing worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"AWS integration error: {ex}")

        except Exception as ex:
            log.error(
                f"Unexpected error refreshing worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"Unexpected error: {ex}")
