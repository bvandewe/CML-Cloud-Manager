"""Collect Worker CloudWatch Metrics command with handler.

This command collects CPU and memory utilization metrics from AWS CloudWatch
for a running worker and updates the worker aggregate.
"""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.services.worker_metrics_service import (
    MetricsResult,
    WorkerMetricsService,
)
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class CollectWorkerCloudWatchMetricsCommand(Command[OperationResult[dict]]):
    """Command to collect CloudWatch metrics for a worker.

    This command:
    1. Queries AWS CloudWatch for CPU and memory utilization
    2. Updates worker with CloudWatch metrics
    3. Only collects metrics if worker is RUNNING

    Returns dict with metrics summary.
    """

    worker_id: str


class CollectWorkerCloudWatchMetricsCommandHandler(
    CommandHandlerBase,
    CommandHandler[CollectWorkerCloudWatchMetricsCommand, OperationResult[dict]],
):
    """Handle CloudWatch metrics collection for worker."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        worker_metrics_service: WorkerMetricsService,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.worker_metrics_service = worker_metrics_service

    async def handle_async(
        self, request: CollectWorkerCloudWatchMetricsCommand
    ) -> OperationResult[dict]:
        """Handle collect CloudWatch metrics command.

        Args:
            request: Collect command with worker ID

        Returns:
            OperationResult with metrics summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "collect_cloudwatch_metrics",
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

            # 2. Only collect CloudWatch metrics if worker is RUNNING
            if worker.state.status != CMLWorkerStatus.RUNNING:
                log.info(
                    f"Skipping CloudWatch metrics collection for worker {command.worker_id} - "
                    f"status is {worker.state.status.value}, not RUNNING"
                )
                return self.ok(
                    {
                        "worker_id": command.worker_id,
                        "status": worker.state.status.value,
                        "metrics_collected": False,
                        "reason": "Worker not running",
                    }
                )

            # 3. Collect metrics using WorkerMetricsService
            with tracer.start_as_current_span("collect_metrics") as span:
                metrics_result: MetricsResult = (
                    await self.worker_metrics_service.collect_worker_metrics(
                        worker=worker,
                        collect_cloudwatch=True,
                    )
                )

                span.set_attribute("metrics.collected", metrics_result.status_updated)
                if metrics_result.cpu_utilization is not None:
                    span.set_attribute("metrics.cpu", metrics_result.cpu_utilization)
                if metrics_result.memory_utilization is not None:
                    span.set_attribute(
                        "metrics.memory", metrics_result.memory_utilization
                    )

            # 4. Save updated worker
            with tracer.start_as_current_span("save_worker"):
                await self.cml_worker_repository.update_async(worker)

            # 5. Build result summary
            result = {
                "worker_id": command.worker_id,
                "metrics_collected": True,
                "cpu_utilization": metrics_result.cpu_utilization,
                "memory_utilization": metrics_result.memory_utilization,
                "cloudwatch_detailed_monitoring": worker.state.cloudwatch_detailed_monitoring_enabled,
            }

            log.info(
                f"Collected CloudWatch metrics for worker {command.worker_id}: "
                f"CPU={metrics_result.cpu_utilization}%, Memory={metrics_result.memory_utilization}%"
            )

            return self.ok(result)

        except Exception as ex:
            log.error(
                f"Failed to collect CloudWatch metrics for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(
                f"Failed to collect worker CloudWatch metrics: {str(ex)}"
            )
