"""Get task by ID query with handler."""

from dataclasses import dataclass
from typing import Any

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from domain.repositories import TaskRepository


@dataclass
class GetTaskByIdQuery(Query[OperationResult[dict[str, Any]]]):
    """Query to retrieve a single task by ID."""

    task_id: str
    user_info: dict[str, Any]


class GetTaskByIdQueryHandler(
    QueryHandler[GetTaskByIdQuery, OperationResult[dict[str, Any]]]
):
    """Handle task retrieval by ID with authorization checks."""

    def __init__(self, task_repository: TaskRepository):
        super().__init__()
        self.task_repository = task_repository

    async def handle_async(
        self, request: GetTaskByIdQuery
    ) -> OperationResult[dict[str, Any]]:
        """Handle get task by ID query with RBAC logic."""
        # Retrieve task
        task = await self.task_repository.get_by_id_async(request.task_id)

        if not task:
            return self.not_found("Task", request.task_id)

        # RBAC: Check if user can view this task
        user_roles = request.user_info.get("roles", [])
        user_id = request.user_info.get("sub") or request.user_info.get("user_id")
        department = request.user_info.get("department")

        can_view = False

        if "admin" in user_roles:
            # Admins can view all tasks
            can_view = True
        elif "manager" in user_roles:
            # Managers can view tasks in their department
            if department and task.state.department == department:
                can_view = True
        else:
            # Regular users can only view their assigned tasks
            if user_id and task.state.assignee_id == user_id:
                can_view = True

        if not can_view:
            return self.bad_request("You do not have permission to view this task")

        # Convert to DTO
        task_dto = {
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

        return self.ok(task_dto)
