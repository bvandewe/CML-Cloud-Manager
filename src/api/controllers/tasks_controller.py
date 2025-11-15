"""Tasks API controller with dual authentication (Session + JWT)."""

from uuid import UUID

from classy_fastapi.decorators import delete, get, post, put
from fastapi import Depends
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.mvc import ControllerBase
from pydantic import BaseModel

from api.dependencies import get_current_user, require_roles
from application.commands import CreateTaskCommand, DeleteTaskCommand, UpdateTaskCommand
from application.queries import GetTaskByIdQuery, GetTasksQuery


class CreateTaskRequest(BaseModel):
    """Create task request model."""

    title: str
    description: str
    status: str = "pending"
    priority: str = "medium"
    assignee_id: str | None = None
    department: str | None = None


class UpdateTaskRequest(BaseModel):
    """Update task request model."""

    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_id: UUID | None = None
    department: str | None = None


class TasksController(ControllerBase):
    """Controller for task management endpoints with dual authentication."""

    def __init__(
        self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator
    ):
        super().__init__(service_provider, mapper, mediator)

    @get("/")
    async def get_tasks(self, user: dict = Depends(get_current_user)):
        """Get tasks with role-based filtering.

        Supports authentication via:
        - Session cookie (from OAuth2 login)
        - JWT Bearer token (for API clients)
        """
        query = GetTasksQuery(user_info=user)
        result = await self.mediator.execute_async(query)
        return self.process(result)

    @get("/{task_id}")
    async def get_task(self, task_id: str, user: dict = Depends(get_current_user)):
        """Get a single task by ID with authorization checks.

        Supports authentication via:
        - Session cookie (from OAuth2 login)
        - JWT Bearer token (for API clients)
        """
        query = GetTaskByIdQuery(task_id=task_id, user_info=user)
        result = await self.mediator.execute_async(query)
        return self.process(result)

    @post("/")
    async def create_task(
        self, request: CreateTaskRequest, user: dict = Depends(get_current_user)
    ):
        """Create a new task.

        Supports authentication via:
        - Session cookie (from OAuth2 login)
        - JWT Bearer token (for API clients)
        """
        command = CreateTaskCommand(
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority,
            assignee_id=request.assignee_id,
            department=request.department,
            user_info=user,
        )

        result = await self.mediator.execute_async(command)
        return self.process(result)

    @put("/{task_id}")
    async def update_task(
        self,
        task_id: str,
        request: UpdateTaskRequest,
        user: dict = Depends(get_current_user),
    ):
        """Update an existing task.

        Supports authentication via:
        - Session cookie (from OAuth2 login)
        - JWT Bearer token (for API clients)
        """
        command = UpdateTaskCommand(
            task_id=task_id,
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority,
            assignee_id=str(request.assignee_id) if request.assignee_id else None,
            department=request.department,
            user_info=user,
        )

        result = await self.mediator.execute_async(command)
        return self.process(result)

    @delete("/{task_id}")
    async def delete_task(
        self, task_id: str, user: dict = Depends(require_roles("admin", "manager"))
    ):
        """Delete an existing task.

        **RBAC Protected**: Only users with 'admin' or 'manager' roles can delete tasks.

        Supports authentication via:
        - Session cookie (from OAuth2 login)
        - JWT Bearer token (for API clients)
        """
        command = DeleteTaskCommand(task_id=task_id, user_info=user)

        result = await self.mediator.execute_async(command)
        return self.process(result)
