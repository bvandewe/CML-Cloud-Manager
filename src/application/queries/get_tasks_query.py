"""Get tasks query with handler and role-based filtering."""

from dataclasses import dataclass
from typing import Any

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from domain.repositories import TaskRepository


@dataclass
class GetTasksQuery(Query[OperationResult[list[Any]]]):
    """Query to retrieve tasks with role-based filtering."""

    user_info: dict[str, Any]


class GetTasksQueryHandler(QueryHandler[GetTasksQuery, OperationResult[list[Any]]]):
    """Handle task retrieval with role-based filtering."""

    def __init__(self, task_repository: TaskRepository):
        super().__init__()
        self.task_repository = task_repository

    async def handle_async(self, request: GetTasksQuery) -> OperationResult[list[Any]]:
        """Handle get tasks query with RBAC logic."""
        query = request
        user_roles = query.user_info.get("roles", [])

        # RBAC Logic: Filter tasks based on user role
        if "admin" in user_roles:
            # Admins see ALL tasks
            tasks = await self.task_repository.get_all_async()
        elif "manager" in user_roles:
            # Managers see their department tasks
            department = query.user_info.get("department")
            if department:
                tasks = await self.task_repository.get_by_department_async(department)
            else:
                tasks = []
        else:
            # Regular users see only their assigned tasks
            # Use 'sub' (subject) from Keycloak userinfo as user_id
            user_id_str = query.user_info.get("sub") or query.user_info.get("user_id")
            if user_id_str:
                # Pass the string directly (repository expects string)
                tasks = await self.task_repository.get_by_assignee_async(user_id_str)
            else:
                # No user ID available, return empty list
                tasks = []

        # Convert to DTOs
        task_dtos = [
            {
                "id": task.id(),
                "title": task.state.title,
                "description": task.state.description,
                "status": task.state.status,
                "priority": task.state.priority,
                "assignee_id": (
                    str(task.state.assignee_id) if task.state.assignee_id else None
                ),
                "department": task.state.department,
                "created_at": task.state.created_at.isoformat(),
                "updated_at": task.state.updated_at.isoformat(),
            }
            for task in tasks
        ]

        return self.ok(task_dtos)
