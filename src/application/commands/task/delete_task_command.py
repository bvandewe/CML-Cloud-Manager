"""Delete task command with handler."""

import time
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.mediation import Command, CommandHandler
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.repositories import TaskRepository
from observability import task_processing_time, tasks_failed

tracer = trace.get_tracer(__name__)


@dataclass
class DeleteTaskCommand(Command[OperationResult]):
    """Command to delete an existing task."""

    task_id: str
    user_info: dict | None = None


class DeleteTaskCommandHandler(CommandHandler[DeleteTaskCommand, OperationResult]):
    """Handle task deletion with authorization checks."""

    def __init__(self, task_repository: TaskRepository):
        super().__init__()
        self.task_repository = task_repository

    async def handle_async(self, request: DeleteTaskCommand) -> OperationResult:
        """Handle delete task command with custom instrumentation."""
        command = request
        start_time = time.time()

        # Add business context to automatic span
        add_span_attributes(
            {
                "task.id": command.task_id,
                "task.has_user_info": command.user_info is not None,
            }
        )

        # Retrieve existing task (auto-traced)
        task = await self.task_repository.get_by_id_async(command.task_id)

        if not task:
            tasks_failed.add(1, {"reason": "not_found", "operation": "delete"})
            return self.not_found(f"Task {command.task_id}", "Task not found")

        # Create custom span for task deletion logic
        with tracer.start_as_current_span("delete_task_entity") as span:
            span.set_attribute("task.found", True)
            span.set_attribute("task.title", task.state.title)
            span.set_attribute("task.status", task.state.status)

            # Add user context for tracing (authorization already checked at API layer)
            deleted_by = None
            if command.user_info:
                user_id = command.user_info.get("sub")
                user_roles = command.user_info.get("roles", [])

                span.set_attribute("task.user_roles", str(user_roles))
                if user_id:
                    span.set_attribute("task.deleted_by", user_id)
                    deleted_by = user_id

            # Mark task as deleted (registers domain event)
            task.mark_as_deleted(deleted_by=deleted_by)

        # Delete task and publish domain events (repository operations are auto-traced)
        deletion_successful = await self.task_repository.delete_async(
            command.task_id, task=task  # Pass task with registered domain events
        )

        # Record metrics
        processing_time_ms = (time.time() - start_time) * 1000

        if deletion_successful:
            task_processing_time.record(
                processing_time_ms,
                {
                    "operation": "delete",
                    "priority": task.state.priority,
                    "status": "success",
                },
            )

            return self.ok(
                {
                    "id": command.task_id,
                    "title": task.state.title,
                    "message": "Task deleted successfully",
                }
            )
        else:
            tasks_failed.add(1, {"operation": "delete", "reason": "deletion_failed"})
            task_processing_time.record(
                processing_time_ms,
                {
                    "operation": "delete",
                    "priority": task.state.priority,
                    "status": "failed",
                },
            )

            return self.bad_request("Failed to delete task")
