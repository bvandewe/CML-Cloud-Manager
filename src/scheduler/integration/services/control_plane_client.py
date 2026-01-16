"""Control Plane API Client.

HTTP client for communicating with the Control Plane API service.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ControlPlaneApiClient:
    """
    HTTP client for the Control Plane API.

    Used by the Scheduler to:
    - Query instance and worker state
    - Request scheduling assignments
    - Signal scale-up requirements
    """

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # Instance Operations
    # =========================================================================

    async def get_pending_instances(self) -> list[dict[str, Any]]:
        """Get all instances in PENDING state."""
        client = await self._get_client()
        response = await client.get("/api/v1/instances", params={"state": "PENDING"})
        response.raise_for_status()
        return response.json()

    async def get_scheduled_instances(self) -> list[dict[str, Any]]:
        """Get all instances in SCHEDULED state."""
        client = await self._get_client()
        response = await client.get("/api/v1/instances", params={"state": "SCHEDULED"})
        response.raise_for_status()
        return response.json()

    async def schedule_instance(self, instance_id: str, worker_id: str) -> dict[str, Any]:
        """Assign a worker to an instance."""
        client = await self._get_client()
        response = await client.post(
            f"/api/internal/instances/{instance_id}/schedule",
            json={"worker_id": worker_id},
        )
        response.raise_for_status()
        return response.json()

    async def allocate_ports(self, instance_id: str, port_count: int) -> dict[str, Any]:
        """Allocate ports for an instance."""
        client = await self._get_client()
        response = await client.post(
            f"/api/internal/instances/{instance_id}/allocate-ports",
            json={"port_count": port_count},
        )
        response.raise_for_status()
        return response.json()

    async def transition_instance(self, instance_id: str, new_state: str, reason: str | None = None) -> dict[str, Any]:
        """Transition an instance to a new state."""
        client = await self._get_client()
        response = await client.post(
            f"/api/internal/instances/{instance_id}/transition",
            json={"state": new_state, "reason": reason},
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Worker Operations
    # =========================================================================

    async def get_active_workers(self) -> list[dict[str, Any]]:
        """Get all active (RUNNING) workers."""
        client = await self._get_client()
        response = await client.get("/api/v1/workers", params={"status": "RUNNING"})
        response.raise_for_status()
        return response.json()

    async def get_worker_capacity(self, worker_id: str) -> dict[str, Any]:
        """Get capacity details for a worker."""
        client = await self._get_client()
        response = await client.get(f"/api/v1/workers/{worker_id}/capacity")
        response.raise_for_status()
        return response.json()

    async def request_scale_up(self, template_name: str, reason: str) -> dict[str, Any]:
        """Request a new worker to be provisioned."""
        client = await self._get_client()
        response = await client.post(
            "/api/internal/workers/scale-up",
            json={"template": template_name, "reason": reason},
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Definition Operations
    # =========================================================================

    async def get_definition(self, definition_id: str) -> dict[str, Any]:
        """Get a lablet definition by ID."""
        client = await self._get_client()
        response = await client.get(f"/api/v1/definitions/{definition_id}")
        response.raise_for_status()
        return response.json()
