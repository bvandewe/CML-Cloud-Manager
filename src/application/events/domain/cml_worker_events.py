"""Domain event handlers for CML Worker events that broadcast SSE updates.

These handlers translate domain events into lightweight SSE messages consumed by
frontend components for real-time UI updates.
"""

from __future__ import annotations

import logging
from datetime import datetime

from neuroglia.mediation import DomainEventHandler

from application.services.sse_event_relay import get_sse_relay
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
    async def handle_async(self, notification: CMLWorkerCreatedDomainEvent) -> None:  # type: ignore[override]
        relay = get_sse_relay()
        await relay.broadcast_event(
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
    async def handle_async(self, notification: CMLWorkerStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        relay = get_sse_relay()
        await relay.broadcast_event(
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
    async def handle_async(self, notification: CMLWorkerTerminatedDomainEvent) -> None:  # type: ignore[override]
        relay = get_sse_relay()
        await relay.broadcast_event(
            event_type="worker.terminated",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "terminated_at": _utc_iso(notification.terminated_at),
            },
            source="domain.cml_worker",
        )
        log.info("Broadcasted worker.terminated for %s", notification.aggregate_id)
        return None


class CMLWorkerTelemetryUpdatedDomainEventHandler(
    DomainEventHandler[CMLWorkerTelemetryUpdatedDomainEvent]
):
    async def handle_async(self, notification: CMLWorkerTelemetryUpdatedDomainEvent) -> None:  # type: ignore[override]
        relay = get_sse_relay()
        await relay.broadcast_event(
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
