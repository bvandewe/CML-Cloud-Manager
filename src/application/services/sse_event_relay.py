"""Event relay service for SSE (Server-Sent Events) broadcasting."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from neuroglia.hosting.abstractions import HostedService

logger = logging.getLogger(__name__)


@dataclass
class SSEClientSubscription:
    """Subscription details for an SSE client with filtering support."""

    client_id: str
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    worker_ids: set[str] | None = None
    event_types: set[str] | None = None

    def matches_event(self, event_type: str, data: dict) -> bool:
        """Check if event matches client's filter criteria.

        Args:
            event_type: Type of the event
            data: Event data dictionary

        Returns:
            True if event matches filters (or no filters set), False otherwise
        """
        # If event_types filter is set, check if event type matches
        if self.event_types is not None and event_type not in self.event_types:
            return False

        # If worker_ids filter is set, check if worker_id in data matches
        if self.worker_ids is not None:
            worker_id = data.get("worker_id")
            if worker_id is None or worker_id not in self.worker_ids:
                return False

        return True


class SSEEventRelay:
    """Relay service for broadcasting events to SSE clients.

    This service maintains a registry of connected SSE clients and
    broadcasts worker-related events to subscribed clients with optional filtering.

    Filters:
    - worker_ids: Only send events for specific workers
    - event_types: Only send specific event types
    """

    def __init__(self):
        self._clients: dict[str, SSEClientSubscription] = {}
        self._lock = asyncio.Lock()

    async def register_client(
        self,
        worker_ids: set[str] | None = None,
        event_types: set[str] | None = None,
    ) -> tuple[str, asyncio.Queue]:
        """Register a new SSE client with optional filters.

        Args:
            worker_ids: Optional set of worker IDs to filter events by
            event_types: Optional set of event types to filter by

        Returns:
            Tuple of (client_id, event_queue)
        """
        client_id = str(uuid4())
        subscription = SSEClientSubscription(
            client_id=client_id, worker_ids=worker_ids, event_types=event_types
        )
        async with self._lock:
            self._clients[client_id] = subscription
        filters_str = []
        if worker_ids:
            filters_str.append(f"worker_ids={worker_ids}")
        if event_types:
            filters_str.append(f"event_types={event_types}")
        filter_desc = f" with filters: {', '.join(filters_str)}" if filters_str else ""
        logger.info(
            f"SSE client registered: {client_id}{filter_desc} (total: {len(self._clients)})"
        )
        return client_id, subscription.event_queue

    async def unregister_client(self, client_id: str) -> None:
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
                logger.info(
                    f"SSE client unregistered: {client_id} (remaining: {len(self._clients)})"
                )

    async def broadcast_event(
        self, event_type: str, data: dict, source: str = "cml-cloud-manager"
    ) -> None:
        """Broadcast event to all matching clients based on their filters.

        Args:
            event_type: Type of event (e.g., "worker.metrics.updated")
            data: Event data dictionary (must include worker_id if filtering by worker)
            source: Event source identifier

        Note:
            Events are only sent to clients whose filters match the event.
            If a client has no filters, it receives all events.
        """
        event_message = {
            "type": event_type,
            "source": source,
            "time": datetime.utcnow().isoformat() + "Z",
            "data": data,
        }
        async with self._lock:
            matching_clients = [
                subscription
                for subscription in self._clients.values()
                if subscription.matches_event(event_type, data)
            ]

        broadcast_count = 0
        for subscription in matching_clients:
            try:
                await asyncio.wait_for(
                    subscription.event_queue.put(event_message), timeout=0.1
                )
                broadcast_count += 1
            except asyncio.TimeoutError:
                logger.warning(
                    f"SSE client {subscription.client_id} queue full, event dropped"
                )
            except Exception as e:
                logger.error(
                    f"Failed to queue event for SSE client {subscription.client_id}: {e}"
                )

        if broadcast_count > 0:
            logger.debug(
                f"Broadcasted event {event_type} to {broadcast_count}/{len(self._clients)} clients"
            )

    def get_connected_clients_count(self) -> int:
        return len(self._clients)


class SSEEventRelayHostedService(HostedService):
    """Hosted service wrapper for the SSEEventRelay.

    Provides start/stop hooks so the application lifecycle can manage
    the relay cleanly. A configure() helper is provided for DI registration.
    """

    def __init__(self, relay: SSEEventRelay):
        self._relay = relay
        self._started = False

    async def start_async(self):
        if self._started:
            return
        logger.info("Starting SSEEventRelayHostedService")
        self._started = True

    async def stop_async(self):
        if not self._started:
            return
        logger.info("Stopping SSEEventRelayHostedService")
        try:
            await self._relay.broadcast_event(
                event_type="system.sse.shutdown",
                data={"message": "SSE relay shutting down"},
                source="sse-event-relay",
            )
        except Exception as e:
            logger.warning(f"Exception when broadcasting shutdown event: {e}")
        self._started = False

    @classmethod
    def configure(cls, builder: Any) -> Any:
        """Register the relay and hosted service with the DI builder."""
        builder.services.add_singleton(SSEEventRelay)
        builder.services.add_singleton(
            SSEEventRelayHostedService,
            implementation_factory=lambda provider: SSEEventRelayHostedService(
                provider.get_required_service(SSEEventRelay)
            ),
        )
        # Attempt to also register as generic HostedService if available
        try:
            builder.services.add_singleton(
                HostedService,
                implementation_factory=lambda provider: provider.get_service(
                    SSEEventRelayHostedService
                ),
            )
        except Exception as e:
            logger.warning(
                f"Exception when registering SSEEventRelayHostedService: {e}"
            )
        logger.info("Registered SSEEventRelayHostedService")
        return builder
