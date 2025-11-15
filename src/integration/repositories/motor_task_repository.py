"""
MongoDB repository for Task entities using Neuroglia's MotorRepository.

This extends the framework's MotorRepository to provide Task-specific queries
while inheriting all standard CRUD operations with automatic domain event publishing.
"""

from typing import TYPE_CHECKING, Optional, cast

from motor.motor_asyncio import AsyncIOMotorClient
from neuroglia.data.infrastructure.mongo import MotorRepository
from neuroglia.data.infrastructure.tracing_mixin import TracedRepositoryMixin
from neuroglia.serialization.json import JsonSerializer

from domain.entities import Task
from domain.repositories import TaskRepository

if TYPE_CHECKING:
    from neuroglia.mediation.mediator import Mediator


class MongoTaskRepository(TracedRepositoryMixin, MotorRepository[Task, str], TaskRepository):  # type: ignore[misc]
    """
    Motor-based async MongoDB repository for Task entities with automatic tracing
    and domain event publishing.

    Extends Neuroglia's MotorRepository to inherit standard CRUD operations with
    automatic event publishing and adds Task-specific queries. TracedRepositoryMixin
    provides automatic OpenTelemetry instrumentation for all repository operations
    using Python's MRO to intercept repository calls transparently.

    Note: Type checker may show warnings about return type variance for get_async.
    This is a limitation of Python's type system with generic types and does not
    affect runtime behavior. The tracing mixin intercepts calls correctly via MRO.
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        database_name: str,
        collection_name: str,
        serializer: JsonSerializer,
        entity_type: Optional[type[Task]] = None,
        mediator: Optional["Mediator"] = None,
    ):
        """
        Initialize the Task repository.

        Args:
            client: Motor async MongoDB client
            database_name: Name of the MongoDB database
            collection_name: Name of the collection
            serializer: JSON serializer for entity conversion
            entity_type: Optional entity type (Task)
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

    # Custom Task-specific queries
    # Note: Standard CRUD operations (get_async, add_async, update_async, remove_async, contains_async)
    # are inherited from MotorRepository base class

    async def get_all_async(self) -> list[Task]:
        """Retrieve all tasks."""
        # Use the inherited get_all method from base repository
        cursor = self.collection.find({})
        tasks = []
        async for document in cursor:
            task = self._deserialize_entity(document)
            tasks.append(task)
        return tasks

    async def get_by_id_async(self, task_id: str) -> Task | None:
        """Retrieve a task by ID."""
        return cast(Task | None, await self.get_async(task_id))

    async def get_by_assignee_async(self, assignee_id: str) -> list[Task]:
        """Retrieve tasks assigned to a specific user."""
        cursor = self.collection.find({"assignee_id": assignee_id})
        tasks = []
        async for document in cursor:
            task = self._deserialize_entity(document)
            tasks.append(task)
        return tasks

    async def get_by_department_async(self, department: str) -> list[Task]:
        """Retrieve tasks for a specific department."""
        cursor = self.collection.find({"department": department})
        tasks = []
        async for document in cursor:
            task = self._deserialize_entity(document)
            tasks.append(task)
        return tasks

    async def delete_async(self, task_id: str, task: Task | None = None) -> bool:
        """Delete a task by ID - custom method for TaskRepository interface.

        Args:
            task_id: The ID of the task to delete
            task: Optional task entity with pending domain events to publish.
                  If provided, will publish its domain events before deletion.
                  If not provided, will retrieve the task first.

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            # Use provided task or retrieve it
            entity = task if task else await self.get_async(task_id)

            if entity:
                # Publish domain events (including TaskDeletedDomainEvent if registered)
                await self._publish_domain_events(entity)

            # Perform physical deletion
            await self.remove_async(task_id)
            return True
        except Exception:
            return False
