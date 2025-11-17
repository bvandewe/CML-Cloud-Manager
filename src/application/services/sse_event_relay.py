"""Event relay service for SSE (Server-Sent Events) broadcasting."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

logger = logging.getLogger(__name__)


class SSEEventRelay:
    """Relay service for broadcasting events to SSE clients.

    This service maintains a registry of connected SSE clients and
    broadcasts worker-related events to all subscribed clients.
    """

    def __init__(self):
        self._clients: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def register_client(self) -> tuple[str, asyncio.Queue]:
        client_id = str(uuid4())
        event_queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._clients[client_id] = event_queue
        logger.info(f"SSE client registered: {client_id} (total: {len(self._clients)})")
        return client_id, event_queue

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
        event_message = {
            "type": event_type,
            "source": source,
            "time": datetime.utcnow().isoformat() + "Z",
            "data": data,
        }
        async with self._lock:
            client_queues = list(self._clients.values())
        for queue in client_queues:
            try:
                await asyncio.wait_for(queue.put(event_message), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning("SSE client queue full, event dropped")
            except Exception as e:
                logger.error(f"Failed to queue event for SSE client: {e}")

    def get_connected_clients_count(self) -> int:
        return len(self._clients)


_sse_relay_instance: SSEEventRelay | None = None


def get_sse_relay() -> SSEEventRelay:
    global _sse_relay_instance
    if _sse_relay_instance is None:
        _sse_relay_instance = SSEEventRelay()
    return _sse_relay_instance


class SSEEventRelayHostedService:
    """Hosted service wrapper for the SSEEventRelay.

    Provides start/stop hooks so the application lifecycle can manage
    the relay cleanly. A configure() helper is provided for DI registration.
    """

    def __init__(self, relay: SSEEventRelay | None = None):
        self._relay = relay or get_sse_relay()
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
        builder.services.add_singleton(SSEEventRelay, singleton=get_sse_relay())
        builder.services.add_singleton(
            SSEEventRelayHostedService,
            implementation_factory=lambda provider: SSEEventRelayHostedService(
                provider.get_required_service(SSEEventRelay)
            ),
        )
        # Attempt to also register as generic HostedService if available
        try:
            from neuroglia.hosting.abstractions import HostedService  # type: ignore

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
