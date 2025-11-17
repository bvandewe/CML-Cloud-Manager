"""Domain event handlers for CML Worker events that broadcast SSE updates.

These handlers translate domain events into lightweight SSE messages consumed by
frontend components for real-time UI updates.
"""

from __future__ import annotations

import logging
from datetime import datetime

from neuroglia.mediation import DomainEventHandler

from application.services import WorkerMonitoringScheduler
from application.services.sse_event_relay import SSEEventRelay
from domain.events.cml_worker import (
    CMLWorkerCreatedDomainEvent,
    CMLWorkerStatusUpdatedDomainEvent,
    CMLWorkerTelemetryUpdatedDomainEvent,
    CMLWorkerTerminatedDomainEvent,
)

log = logging.getLogger(__name__)


def _utc_iso(dt: datetime) -> str:
    return dt.isoformat() + "Z"


class CMLWorkerCreatedDomainEventHandler(
    DomainEventHandler[CMLWorkerCreatedDomainEvent]
):
    def __init__(self, sse_relay: SSEEventRelay):
        self._sse_relay = sse_relay

    async def handle_async(self, notification: CMLWorkerCreatedDomainEvent) -> None:  # type: ignore[override]
        await self._sse_relay.broadcast_event(
            event_type="worker.created",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "region": notification.aws_region,
                "status": notification.status.value,
                "instance_type": notification.instance_type,
                "created_at": _utc_iso(notification.created_at),
            },
            source="domain.cml_worker",
        )
        log.info("Broadcasted worker.created for %s", notification.aggregate_id)
        return None


class CMLWorkerStatusUpdatedDomainEventHandler(
    DomainEventHandler[CMLWorkerStatusUpdatedDomainEvent]
):
    def __init__(self, sse_relay: SSEEventRelay):
        self._sse_relay = sse_relay

    async def handle_async(self, notification: CMLWorkerStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        await self._sse_relay.broadcast_event(
            event_type="worker.status.updated",
            data={
                "worker_id": notification.aggregate_id,
                "old_status": notification.old_status.value,
                "new_status": notification.new_status.value,
                "updated_at": _utc_iso(notification.updated_at),
            },
            source="domain.cml_worker",
        )
        log.info("Broadcasted worker.status.updated for %s", notification.aggregate_id)
        return None


class CMLWorkerTerminatedDomainEventHandler(
    DomainEventHandler[CMLWorkerTerminatedDomainEvent]
):
    """Handler for worker termination events.

    Broadcasts SSE notification and stops the monitoring job for the terminated worker.
    """

    def __init__(
        self,
        sse_relay: SSEEventRelay,
        monitoring_scheduler: WorkerMonitoringScheduler | None = None,
    ) -> None:
        """Initialize the handler.

        Args:
            sse_relay: SSE event relay for broadcasting events.
            monitoring_scheduler: Optional scheduler for stopping monitoring jobs.
                                 If None, job cleanup will be skipped (monitoring disabled).
        """
        self._sse_relay = sse_relay
        self._monitoring_scheduler = monitoring_scheduler

    async def handle_async(self, notification: CMLWorkerTerminatedDomainEvent) -> None:  # type: ignore[override]
        await self._sse_relay.broadcast_event(
            event_type="worker.terminated",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "terminated_at": _utc_iso(notification.terminated_at),
            },
            source="domain.cml_worker",
        )
        log.info("Broadcasted worker.terminated for %s", notification.aggregate_id)

        # Stop monitoring job for terminated worker
        if self._monitoring_scheduler:
            try:
                await self._monitoring_scheduler.stop_monitoring_worker_async(
                    notification.aggregate_id
                )
                log.info(
                    f"✅ Stopped monitoring job for terminated worker {notification.aggregate_id}"
                )
            except Exception as e:
                log.error(
                    f"❌ Failed to stop monitoring job for terminated worker {notification.aggregate_id}: {e}",
                    exc_info=True,
                )
        else:
            log.debug(
                "Monitoring scheduler not configured - skipping job cleanup for terminated worker"
            )

        return None


class CMLWorkerTelemetryUpdatedDomainEventHandler(
    DomainEventHandler[CMLWorkerTelemetryUpdatedDomainEvent]
):
    def __init__(self, sse_relay: SSEEventRelay):
        self._sse_relay = sse_relay

    async def handle_async(self, notification: CMLWorkerTelemetryUpdatedDomainEvent) -> None:  # type: ignore[override]
        await self._sse_relay.broadcast_event(
            event_type="worker.metrics.updated",
            data={
                "worker_id": notification.aggregate_id,
                "last_activity_at": _utc_iso(notification.last_activity_at),
                "active_labs_count": notification.active_labs_count,
                "cpu_utilization": notification.cpu_utilization,
                "memory_utilization": notification.memory_utilization,
                "updated_at": _utc_iso(notification.updated_at),
            },
            source="domain.cml_worker",
        )
        log.debug(
            "Broadcasted worker.metrics.updated (telemetry) for %s",
            notification.aggregate_id,
        )
        return None
