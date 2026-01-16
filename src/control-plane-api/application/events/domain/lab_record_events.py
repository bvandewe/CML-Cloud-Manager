"""Domain event handlers for Lab Record events that broadcast SSE updates.

These handlers translate lab record domain events into lightweight SSE messages
consumed by frontend components for real-time UI updates.
"""

from __future__ import annotations

import logging

from neuroglia.mediation import DomainEventHandler

from application.services.sse_event_relay import SSEEventRelay
from domain.events.lab_record_events import (
    LabRecordCreatedDomainEvent,
    LabRecordUpdatedDomainEvent,
    LabStateChangedDomainEvent,
)
from domain.repositories.lab_record_repository import LabRecordRepository

log = logging.getLogger(__name__)


def _utc_iso(dt) -> str | None:
    """Convert datetime to ISO format with Z suffix."""
    if dt is None:
        return None
    return dt.isoformat() + "Z"


class LabRecordCreatedDomainEventHandler(DomainEventHandler[LabRecordCreatedDomainEvent]):
    """Handle lab record created event by broadcasting SSE update."""

    def __init__(self, sse_relay: SSEEventRelay, repository: LabRecordRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: LabRecordCreatedDomainEvent) -> None:  # type: ignore[override]
        """Broadcast worker.labs.updated SSE event when lab is created."""
        await self._sse_relay.broadcast_event(
            event_type="worker.labs.updated",
            data={
                "worker_id": notification.worker_id,
                "lab_id": notification.lab_id,
                "action": "created",
                "title": notification.title,
                "state": notification.state,
                "node_count": notification.node_count,
                "link_count": notification.link_count,
                "owner_username": notification.owner_username,
                "first_seen_at": _utc_iso(notification.first_seen_at),
            },
            source="domain.lab_record",
        )

        log.debug(
            f"Broadcasted worker.labs.updated (created) for lab {notification.lab_id} "
            f"on worker {notification.worker_id}"
        )
        return None


class LabRecordUpdatedDomainEventHandler(DomainEventHandler[LabRecordUpdatedDomainEvent]):
    """Handle lab record updated event by broadcasting SSE update."""

    def __init__(self, sse_relay: SSEEventRelay, repository: LabRecordRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: LabRecordUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Broadcast worker.labs.updated SSE event when lab is updated."""
        # Extract worker_id from aggregate_id (format: "worker_id:lab_id")
        # The aggregate uses record ID, so we need to query the repository
        lab_record = await self._repository.get_by_id_async(notification.aggregate_id)
        if not lab_record:
            log.warning(f"Lab record {notification.aggregate_id} not found for SSE broadcast")
            return None

        await self._sse_relay.broadcast_event(
            event_type="worker.labs.updated",
            data={
                "worker_id": lab_record.state.worker_id,
                "lab_id": notification.lab_id,
                "action": "updated",
                "title": notification.title,
                "state": notification.state,
                "node_count": notification.node_count,
                "link_count": notification.link_count,
                "owner_username": notification.owner_username,
                "synced_at": _utc_iso(notification.synced_at),
            },
            source="domain.lab_record",
        )

        log.debug(
            f"Broadcasted worker.labs.updated (updated) for lab {notification.lab_id} "
            f"on worker {lab_record.state.worker_id}"
        )
        return None


class LabStateChangedDomainEventHandler(DomainEventHandler[LabStateChangedDomainEvent]):
    """Handle lab state changed event by broadcasting SSE update."""

    def __init__(self, sse_relay: SSEEventRelay, repository: LabRecordRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: LabStateChangedDomainEvent) -> None:  # type: ignore[override]
        """Broadcast worker.labs.updated SSE event when lab state changes."""
        lab_record = await self._repository.get_by_id_async(notification.aggregate_id)
        if not lab_record:
            log.warning(f"Lab record {notification.aggregate_id} not found for SSE broadcast")
            return None

        await self._sse_relay.broadcast_event(
            event_type="worker.labs.updated",
            data={
                "worker_id": lab_record.state.worker_id,
                "lab_id": notification.lab_id,
                "action": "state_changed",
                "previous_state": notification.previous_state,
                "new_state": notification.new_state,
                "changed_fields": notification.changed_fields,
                "changed_at": _utc_iso(notification.changed_at),
            },
            source="domain.lab_record",
        )

        log.debug(
            f"Broadcasted worker.labs.updated (state_changed) for lab {notification.lab_id} "
            f"on worker {lab_record.state.worker_id}: {notification.previous_state} → {notification.new_state}"
        )
        return None
