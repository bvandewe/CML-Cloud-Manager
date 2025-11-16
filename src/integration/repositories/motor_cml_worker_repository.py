"""
MongoDB repository for CMLWorker entities using Neuroglia's MotorRepository.

This extends the framework's MotorRepository to provide CMLWorker-specific queries
while inheriting all standard CRUD operations with automatic domain event publishing.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, cast

from motor.motor_asyncio import AsyncIOMotorClient
from neuroglia.data.infrastructure.mongo import MotorRepository
from neuroglia.data.infrastructure.tracing_mixin import TracedRepositoryMixin
from neuroglia.serialization.json import JsonSerializer

from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository

if TYPE_CHECKING:
    from neuroglia.mediation.mediator import Mediator


class MongoCMLWorkerRepository(TracedRepositoryMixin, MotorRepository[CMLWorker, str], CMLWorkerRepository):  # type: ignore[misc]
    """
    Motor-based async MongoDB repository for CMLWorker entities with automatic tracing
    and domain event publishing.

    Extends Neuroglia's MotorRepository to inherit standard CRUD operations with
    automatic event publishing and adds CMLWorker-specific queries. TracedRepositoryMixin
    provides automatic OpenTelemetry instrumentation for all repository operations
    using Python's MRO to intercept repository calls transparently.
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        database_name: str,
        collection_name: str,
        serializer: JsonSerializer,
        entity_type: Optional[type[CMLWorker]] = None,
        mediator: Optional["Mediator"] = None,
    ):
        """
        Initialize the CMLWorker repository.

        Args:
            client: Motor async MongoDB client
            database_name: Name of the MongoDB database
            collection_name: Name of the collection
            serializer: JSON serializer for entity conversion
            entity_type: Optional entity type (CMLWorker)
            mediator: Optional Mediator for automatic domain event publishing
        """
        super().__init__(
            client=client,
            database_name=database_name,
            collection_name=collection_name,
            serializer=serializer,
            entity_type=entity_type,
            mediator=mediator,
        )

    async def get_all_async(self) -> list[CMLWorker]:
        """Retrieve all CML workers."""
        cursor = self.collection.find({})
        workers = []
        async for document in cursor:
            worker = self._deserialize_entity(document)
            workers.append(worker)
        return workers

    async def get_by_id_async(self, worker_id: str) -> CMLWorker | None:
        """Retrieve a CML worker by ID."""
        return cast(CMLWorker | None, await self.get_async(worker_id))

    async def get_by_aws_instance_id_async(
        self, aws_instance_id: str
    ) -> CMLWorker | None:
        """Retrieve a CML worker by AWS EC2 instance ID."""
        document = await self.collection.find_one({"aws_instance_id": aws_instance_id})
        if document:
            return self._deserialize_entity(document)
        return None

    async def get_by_status_async(self, status: CMLWorkerStatus) -> list[CMLWorker]:
        """Retrieve CML workers by status."""
        cursor = self.collection.find({"status": status.value})
        workers = []
        async for document in cursor:
            worker = self._deserialize_entity(document)
            workers.append(worker)
        return workers

    async def get_active_workers_async(self) -> list[CMLWorker]:
        """Retrieve all active (non-terminated) CML workers."""
        cursor = self.collection.find(
            {"status": {"$ne": CMLWorkerStatus.TERMINATED.value}}
        )
        workers = []
        async for document in cursor:
            worker = self._deserialize_entity(document)
            workers.append(worker)
        return workers

    async def get_idle_workers_async(
        self, idle_threshold_minutes: int
    ) -> list[CMLWorker]:
        """Retrieve workers that have been idle beyond the threshold.

        Args:
            idle_threshold_minutes: Idle threshold in minutes

        Returns:
            List of idle workers (running but inactive)
        """
        threshold_time = datetime.now(timezone.utc) - timedelta(
            minutes=idle_threshold_minutes
        )
        cursor = self.collection.find(
            {
                "status": CMLWorkerStatus.RUNNING.value,
                "last_activity_at": {"$lt": threshold_time.isoformat()},
            }
        )
        workers = []
        async for document in cursor:
            worker = self._deserialize_entity(document)
            workers.append(worker)
        return workers

    async def get_workers_by_region_async(self, aws_region: str) -> list[CMLWorker]:
        """Retrieve workers in a specific AWS region.

        Args:
            aws_region: AWS region identifier (e.g., 'us-east-1')

        Returns:
            List of workers in the specified region
        """
        cursor = self.collection.find({"aws_region": aws_region})
        workers = []
        async for document in cursor:
            worker = self._deserialize_entity(document)
            workers.append(worker)
        return workers

    async def add_async(self, entity: CMLWorker) -> CMLWorker:  # type: ignore[override]
        """Add a new CML worker.

        Args:
            entity: The CML worker entity to add

        Returns:
            The added worker with updated state
        """
        return cast(CMLWorker, await super().add_async(entity))

    async def update_async(self, entity: CMLWorker) -> CMLWorker:  # type: ignore[override]
        """Update an existing CML worker.

        Args:
            entity: The CML worker entity to update

        Returns:
            The updated worker
        """
        return cast(CMLWorker, await super().update_async(entity))

    async def delete_async(
        self, worker_id: str, worker: Optional[CMLWorker] = None
    ) -> bool:
        """Delete a CML worker by ID.

        Args:
            worker_id: The ID of the worker to delete
            worker: Optional worker entity with pending domain events to publish

        Returns:
            True if deletion was successful, False otherwise
        """
        # The base MotorRepository.remove_async will handle event publishing
        # if a mediator is configured and the entity has pending events
        await self.remove_async(worker_id)
        return True
