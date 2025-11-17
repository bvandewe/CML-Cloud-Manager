"""SSE (Server-Sent Events) Controller for real-time UI updates."""

import asyncio
import json
import logging
from typing import AsyncIterator

from classy_fastapi.decorators import get as get_route
from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.mvc import ControllerBase

from api.dependencies import get_current_user
from application.services.sse_event_relay import SSEEventRelay

logger = logging.getLogger(__name__)


class EventsController(ControllerBase):
    """Controller for Server-Sent Events (SSE) endpoint."""

    def __init__(
        self,
        service_provider: ServiceProviderBase,
        mapper: Mapper,
        mediator: Mediator,
    ):
        """Initialize Events Controller."""
        ControllerBase.__init__(self, service_provider, mapper, mediator)
        self._sse_relay = service_provider.get_required_service(SSEEventRelay)

    async def _event_generator(
        self, request: Request, user_info: dict
    ) -> AsyncIterator[str]:
        """Generate SSE events from SSEEventRelay.

        Args:
            request: FastAPI request object (to detect client disconnect)
            user_info: User authentication info

        Yields:
            SSE-formatted event strings
        """
        client_id, event_queue = await self._sse_relay.register_client()

        try:
            logger.info(
                f"SSE client connected - user: {user_info.get('username', 'unknown')}, client_id: {client_id}"
            )

            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'user': user_info.get('username'), 'client_id': client_id})}\n\n"

            # Heartbeat interval (30 seconds)
            heartbeat_interval = 30
            last_heartbeat = asyncio.get_event_loop().time()

            # Stream events
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(
                        f"SSE client disconnected - user: {user_info.get('username', 'unknown')}, client_id: {client_id}"
                    )
                    break

                try:
                    # Wait for event with timeout (for heartbeat)
                    event_message = await asyncio.wait_for(
                        event_queue.get(), timeout=heartbeat_interval
                    )

                    # Format event as SSE
                    event_type = event_message.get("type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event_message)}\n\n"
                    last_heartbeat = asyncio.get_event_loop().time()

                except asyncio.TimeoutError:
                    # Send heartbeat
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': current_time})}\n\n"
                        last_heartbeat = current_time

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for client {client_id}")
            raise
        except Exception as e:
            logger.error(
                f"Error in SSE event generator for client {client_id}: {e}",
                exc_info=True,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Unregister client on disconnect
            await self._sse_relay.unregister_client(client_id)

    @get_route(
        "/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "Server-Sent Events stream",
                "content": {"text/event-stream": {}},
            }
        },
    )
    async def stream_events(
        self, request: Request, user_info: dict = Depends(get_current_user)
    ) -> StreamingResponse:
        """Stream server-sent events for real-time UI updates.

        This endpoint streams worker-related events to connected clients:
        - Worker metrics updated
        - Worker status changed
        - Worker created/terminated
        - Labs data updated

        The stream includes periodic heartbeats and auto-reconnection support.

        (**Requires authenticated user.**)

        Args:
            request: FastAPI request object
            user_info: Current user information from authentication

        Returns:
            StreamingResponse with SSE events
        """
        return StreamingResponse(
            self._event_generator(request, user_info),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
