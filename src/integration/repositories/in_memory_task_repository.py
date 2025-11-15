"""In-memory implementation of TaskRepository."""

from domain.entities import Task
from domain.repositories import TaskRepository


class InMemoryTaskRepository(TaskRepository):
    """In-memory implementation of TaskRepository for testing."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    async def get_all_async(self) -> list[Task]:
        """Retrieve all tasks."""
        return list(self._tasks.values())

    async def get_by_id_async(self, task_id: str) -> Task | None:
        """Retrieve a task by ID."""
        return self._tasks.get(task_id)

    async def get_by_assignee_async(self, assignee_id: str) -> list[Task]:
        """Retrieve tasks assigned to a specific user."""
        return [
            task
            for task in self._tasks.values()
            if task.state.assignee_id == assignee_id
        ]

    async def get_by_department_async(self, department: str) -> list[Task]:
        """Retrieve tasks for a specific department."""
        return [
            task for task in self._tasks.values() if task.state.department == department
        ]

    async def add_async(self, entity: Task) -> Task:
        """Add a new task."""
        self._tasks[entity.id()] = entity
        return entity

    async def update_async(self, entity: Task) -> Task:
        """Update an existing task."""
        self._tasks[entity.id()] = entity
        return entity

    async def delete_async(self, task_id: str) -> bool:
        """Delete a task by ID."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False
