"""Domain event handlers for worker data refresh events.

These handlers listen to worker data refresh domain events and broadcast them
as Server-Sent Events (SSE) to connected clients.
"""

import logging

from neuroglia.mediation import DomainEventHandler

from application.services.sse_event_relay import SSEEventRelay
from domain.events.cml_worker import (
    WorkerDataRefreshCompletedDomainEvent,
    WorkerDataRefreshRequestedDomainEvent,
    WorkerDataRefreshSkippedDomainEvent,
)
from domain.repositories.cml_worker_repository import CMLWorkerRepository

logger = logging.getLogger(__name__)


class WorkerDataRefreshRequestedEventHandler(DomainEventHandler[WorkerDataRefreshRequestedDomainEvent]):
    """Handler for worker data refresh requested events."""

    def __init__(
        self,
        sse_relay: SSEEventRelay,
        worker_repository: CMLWorkerRepository,
    ):
        """Initialize the handler.

        Args:
            sse_relay: SSE event relay for broadcasting to clients
            worker_repository: Repository to fetch worker details
        """
        self._sse_relay = sse_relay
        self._worker_repository = worker_repository

    async def handle_async(
        self,
        notification: WorkerDataRefreshRequestedDomainEvent,
    ) -> None:
        """Handle worker data refresh requested event.

        Broadcasts SSE notification to connected clients.

        Args:
            notification: The domain event
        """
        try:
            # Fetch worker to get name
            worker = await self._worker_repository.get_by_id_async(notification.worker_id)
            worker_name = worker.state.name if worker else "Unknown"

            # Broadcast SSE to all connected clients
            await self._sse_relay.broadcast_event(
                event_type="worker.refresh.requested",
                data={
                    "worker_id": notification.worker_id,
                    "worker_name": worker_name,
                    "requested_at": notification.requested_at,
                    "requested_by": notification.requested_by,
                    "eta_seconds": 1,
                    "message": f"Data refresh requested for worker '{worker_name}' by {notification.requested_by}",
                },
            )

            logger.info(
                "Broadcasted data refresh requested event",
                extra={
                    "worker_id": notification.worker_id,
                    "worker_name": worker_name,
                    "requested_by": notification.requested_by,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to handle worker data refresh requested event",
                extra={
                    "worker_id": notification.worker_id,
                    "error": str(e),
                },
                exc_info=True,
            )


class WorkerDataRefreshSkippedEventHandler(DomainEventHandler[WorkerDataRefreshSkippedDomainEvent]):
    """Handler for worker data refresh skipped events."""

    def __init__(
        self,
        sse_relay: SSEEventRelay,
        worker_repository: CMLWorkerRepository,
    ):
        """Initialize the handler.

        Args:
            sse_relay: SSE event relay for broadcasting to clients
            worker_repository: Repository to fetch worker details
        """
        self._sse_relay = sse_relay
        self._worker_repository = worker_repository

    async def handle_async(
        self,
        notification: WorkerDataRefreshSkippedDomainEvent,
    ) -> None:
        """Handle worker data refresh skipped event.

        Broadcasts SSE notification to connected clients.

        Args:
            notification: The domain event
        """
        try:
            # Fetch worker to get name
            worker = await self._worker_repository.get_by_id_async(notification.worker_id)
            worker_name = worker.state.name if worker else "Unknown"

            # Broadcast SSE to all connected clients
            await self._sse_relay.broadcast_event(
                event_type="worker.refresh.skipped",
                data={
                    "worker_id": notification.worker_id,
                    "worker_name": worker_name,
                    "reason": notification.reason,
                    "skipped_at": notification.skipped_at,
                    "message": f"Data refresh skipped for worker '{worker_name}': {notification.reason}",
                },
            )

            logger.info(
                "Broadcasted data refresh skipped event",
                extra={
                    "worker_id": notification.worker_id,
                    "worker_name": worker_name,
                    "reason": notification.reason,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to handle worker data refresh skipped event",
                extra={
                    "worker_id": notification.worker_id,
                    "error": str(e),
                },
                exc_info=True,
            )


class WorkerDataRefreshCompletedEventHandler(DomainEventHandler[WorkerDataRefreshCompletedDomainEvent]):
    """Handler for worker data refresh completed events."""

    def __init__(
        self,
        sse_relay: SSEEventRelay,
        worker_repository: CMLWorkerRepository,
    ):
        """Initialize the handler.

        Args:
            sse_relay: SSE event relay for broadcasting to clients
            worker_repository: Repository to fetch worker details
        """
        self._sse_relay = sse_relay
        self._worker_repository = worker_repository

    async def handle_async(
        self,
        notification: WorkerDataRefreshCompletedDomainEvent,
        cancellation_token=None,
    ) -> None:  # type: ignore[override]
        """Handle worker data refresh completed event.

        Broadcasts SSE notification to connected clients.

        Args:
            notification: The domain event
            cancellation_token: Optional cancellation token
        """
        try:
            # Fetch worker to get name
            worker = await self._worker_repository.get_by_id_async(notification.worker_id)
            worker_name = worker.state.name if worker else "Unknown"

            # Broadcast SSE to all connected clients
            await self._sse_relay.broadcast_event(
                event_type="worker.data.refreshed",
                data={
                    "worker_id": notification.worker_id,
                    "worker_name": worker_name,
                    "completed_at": notification.completed_at,
                    "refresh_type": notification.refresh_type,
                    "message": f"Data refresh completed for worker '{worker_name}'",
                },
            )

            # Note: Snapshot broadcast removed - data refresh completion is just a notification
            # UI already received worker.metrics.updated with actual data changes
            # Snapshots are only broadcast for significant state changes (status, license, etc.)

            logger.info(
                "Broadcasted data refresh completed for %s",
                notification.worker_id,
                extra={
                    "worker_name": worker_name,
                    "refresh_type": notification.refresh_type,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to handle worker data refresh completed event",
                extra={
                    "worker_id": notification.worker_id,
                    "error": str(e),
                },
                exc_info=True,
            )
