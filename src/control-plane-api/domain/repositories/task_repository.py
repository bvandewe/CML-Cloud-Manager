"""Abstract repository for tasks."""

from abc import ABC, abstractmethod

from domain.entities import Task


class TaskRepository(ABC):
    """Abstract repository for Task entities."""

    @abstractmethod
    async def get_all_async(self) -> list[Task]:
        """Retrieve all tasks."""
        pass

    @abstractmethod
    async def get_by_id_async(self, task_id: str) -> Task | None:
        """Retrieve a task by ID."""
        pass

    @abstractmethod
    async def get_by_assignee_async(self, assignee_id: str) -> list[Task]:
        """Retrieve tasks assigned to a specific user."""
        pass

    @abstractmethod
    async def get_by_department_async(self, department: str) -> list[Task]:
        """Retrieve tasks for a specific department."""
        pass

    @abstractmethod
    async def add_async(self, entity: Task) -> Task:
        """Add a new task."""
        pass

    @abstractmethod
    async def update_async(self, entity: Task) -> Task:
        """Update an existing task."""
        pass

    @abstractmethod
    async def delete_async(self, task_id: str, task: Task | None = None) -> bool:
        """Delete a task by ID.

        Args:
            task_id: The ID of the task to delete
            task: Optional task entity with pending domain events to publish

        Returns:
            True if deletion was successful, False otherwise
        """
        pass
