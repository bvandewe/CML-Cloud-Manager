"""Create task command with handler."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.entities import Task
from domain.enums import TaskPriority, TaskStatus
from domain.repositories import TaskRepository
from integration.models.task_dto import TaskCreatedDto
from observability import task_processing_time, tasks_created

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class CreateTaskCommand(Command[OperationResult[TaskCreatedDto]]):
    """Command to create a new task."""

    title: str
    description: str
    status: str = "pending"
    priority: str = "medium"
    assignee_id: str | None = None
    department: str | None = None
    user_info: dict | None = None


class CreateTaskCommandHandler(
    CommandHandlerBase,
    CommandHandler[CreateTaskCommand, OperationResult[TaskCreatedDto]],
):
    """Handle task creation."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        task_repository: TaskRepository,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.task_repository = task_repository

    async def handle_async(
        self, request: CreateTaskCommand
    ) -> OperationResult[TaskCreatedDto]:
        """Handle create task command with custom instrumentation."""
        command = request
        start_time = time.time()

        # Add business context to automatic span created by CQRS middleware
        add_span_attributes(
            {
                "task.title": command.title,
                "task.priority": command.priority,
                "task.has_user_info": command.user_info is not None,
            }
        )

        command.user_info = {} if command.user_info is None else command.user_info

        # Create custom span for task creation logic
        with tracer.start_as_current_span("create_task_entity") as span:
            # Convert string values to enums
            try:
                status = TaskStatus(command.status)
            except ValueError:
                status = TaskStatus.PENDING

            try:
                priority = TaskPriority(command.priority)
            except ValueError:
                priority = TaskPriority.MEDIUM

            # Determine department: use explicit department if provided, otherwise from user_info
            department = (
                command.department
                if command.department
                else command.user_info.get("department")
            )

            # Get user ID from various possible fields in user_info
            # Keycloak uses 'sub' (subject) as the primary user identifier
            created_by = (
                command.user_info.get("sub")
                or command.user_info.get("user_id")
                or command.user_info.get("preferred_username")
                or "unknown"
            )

            # Create new task
            now = datetime.now(timezone.utc)
            task = Task(
                title=command.title,
                description=command.description,
                priority=priority,
                status=status,
                assignee_id=command.assignee_id,
                department=department,
                created_at=now,
                updated_at=now,
                created_by=created_by,
            )
            span.set_attribute("task.status", status.value)
            span.set_attribute("task.priority", priority.value)
            span.set_attribute("task.assignee_id", command.assignee_id or "unassigned")
            span.set_attribute("task.created_by", created_by)
            span.set_attribute("task.department", task.state.department or "unknown")

        # Save task (repository operations are auto-traced)
        # This will publish all DomainEvents!
        saved_task = await self.task_repository.add_async(task)

        # Record metrics
        processing_time_ms = (time.time() - start_time) * 1000
        tasks_created.add(
            1,
            {
                "priority": priority.value,
                "status": status.value,
                "has_assignee": bool(command.assignee_id),
                "has_department": bool(task.state.department),
            },
        )
        task_processing_time.record(
            processing_time_ms, {"operation": "create", "priority": priority.value}
        )

        # This is deprecated (was for Entity, not AggregateRoot)
        # ev = TaskCreatedIntegrationEventV1(
        #     aggregate_id=saved_task.aggregate_id,
        #     created_at=saved_task.created_at,
        #     title=saved_task.title,
        #     description=saved_task.description,
        #     status=saved_task.status,
        #     priority=saved_task.priority,
        #     assignee_id=saved_task.assignee_id,
        #     department=saved_task.department,
        # )
        # await self.publish_cloud_event_async(ev)
        # log.debug(f"Published cloud event for task creation: {ev.aggregate_id}")

        dto = TaskCreatedDto(
            id=saved_task.id(),
            title=saved_task.state.title,
            description=saved_task.state.description,
            status=saved_task.state.status,
            priority=saved_task.state.priority,
            assignee_id=saved_task.state.assignee_id,
            department=saved_task.state.department,
            created_at=saved_task.state.created_at,
            created_by=saved_task.state.created_by,
        )

        return self.ok(dto)
