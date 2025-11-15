"""Task aggregate definition using the AggregateState pattern

    DomainEvents are appended/aggregated in the Task and the
    repository publishes them via Mediator after the Task was persisted!
."""

from datetime import datetime, timezone
from typing import Optional, cast
from uuid import uuid4

from multipledispatch import dispatch
from neuroglia.data.abstractions import AggregateRoot, AggregateState

from domain.enums import TaskPriority, TaskStatus
from domain.events.task import (
    TaskAssigneeUpdatedDomainEvent,
    TaskCreatedDomainEvent,
    TaskDeletedDomainEvent,
    TaskDepartmentUpdatedDomainEvent,
    TaskDescriptionUpdatedDomainEvent,
    TaskPriorityUpdatedDomainEvent,
    TaskStatusUpdatedDomainEvent,
    TaskTitleUpdatedDomainEvent,
)


class TaskState(AggregateState[str]):
    """Encapsulates the persisted state for the Task aggregate."""

    id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    assignee_id: Optional[str]
    department: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    def __init__(self) -> None:
        super().__init__()
        self.id = ""
        self.title = ""
        self.description = ""
        self.status = TaskStatus.PENDING
        self.priority = TaskPriority.MEDIUM
        self.assignee_id = None
        self.department = None

        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now
        self.created_by = None

    @dispatch(TaskCreatedDomainEvent)
    def on(self, event: TaskCreatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the creation event to the state."""
        self.id = event.aggregate_id
        self.title = event.title
        self.description = event.description
        self.status = event.status
        self.priority = event.priority
        self.assignee_id = event.assignee_id
        self.department = event.department
        self.created_at = event.created_at
        self.updated_at = event.updated_at
        self.created_by = event.created_by

    @dispatch(TaskTitleUpdatedDomainEvent)
    def on(self, event: TaskTitleUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the title updated event to the state."""
        self.title = event.new_title
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskDescriptionUpdatedDomainEvent)
    def on(self, event: TaskDescriptionUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the description updated event to the state"""
        self.description = event.new_description
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskStatusUpdatedDomainEvent)
    def on(self, event: TaskStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the status updated event to the state."""
        self.status = event.new_status
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskPriorityUpdatedDomainEvent)
    def on(self, event: TaskPriorityUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the priority updated event to the state."""
        self.priority = event.new_priority
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskAssigneeUpdatedDomainEvent)
    def on(self, event: TaskAssigneeUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the assignee updated event to the state."""
        self.assignee_id = event.new_assignee_id
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskDepartmentUpdatedDomainEvent)
    def on(self, event: TaskDepartmentUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the department updated event to the state."""
        self.department = event.new_department
        self.updated_at = datetime.now(timezone.utc)

    @dispatch(TaskDeletedDomainEvent)
    def on(self, event: TaskDeletedDomainEvent) -> None:  # type: ignore[override]
        """Apply the deleted event to the state (marks as deleted)."""
        # Note: In event sourcing, we don't actually remove the state,
        # we just mark it as deleted. The repository handles physical deletion.
        self.updated_at = datetime.now(timezone.utc)


class Task(AggregateRoot[TaskState, str]):
    """Task aggregate root following the AggregateState pattern."""

    def __init__(
        self,
        title: str,
        description: str,
        status: TaskStatus = TaskStatus.PENDING,
        priority: TaskPriority = TaskPriority.MEDIUM,
        assignee_id: Optional[str] = None,
        department: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        aggregate_id = task_id or str(uuid4())
        created_time = created_at or datetime.now(timezone.utc)
        updated_time = updated_at or created_time

        self.state.on(
            self.register_event(  # type: ignore
                TaskCreatedDomainEvent(
                    aggregate_id=aggregate_id,
                    title=title,
                    description=description,
                    status=status,
                    priority=priority,
                    assignee_id=assignee_id,
                    department=department,
                    created_at=created_time,
                    updated_at=updated_time,
                    created_by=created_by,
                )
            )
        )

    def id(self) -> str:
        """Return the aggregate identifier with a precise type."""

        aggregate_id = super().id()
        if aggregate_id is None:
            raise ValueError("Task aggregate identifier has not been initialized")
        return cast(str, aggregate_id)

    def update_title(self, new_title: str) -> bool:
        if self.state.title == new_title:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskTitleUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_title=new_title,
                )
            )
        )
        return True

    def update_description(self, new_description: str) -> bool:
        if self.state.description == new_description:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskDescriptionUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_description=new_description,
                )
            )
        )
        return True

    def update_status(self, new_status: TaskStatus) -> bool:
        if self.state.status == new_status:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskStatusUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_status=new_status,
                )
            )
        )
        return True

    def update_priority(self, new_priority: TaskPriority) -> bool:
        if self.state.priority == new_priority:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskPriorityUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_priority=new_priority,
                )
            )
        )
        return True

    def update_assignee(self, new_assignee_id: Optional[str]) -> bool:
        if self.state.assignee_id == new_assignee_id:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskAssigneeUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_assignee_id=new_assignee_id,
                )
            )
        )
        return True

    def update_department(self, new_department: Optional[str]) -> bool:
        if self.state.department == new_department:
            return False
        self.state.on(
            self.register_event(  # type: ignore
                TaskDepartmentUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    new_department=new_department,
                )
            )
        )
        return True

    def mark_as_deleted(self, deleted_by: Optional[str] = None) -> None:
        """Mark the task as deleted by registering a deletion event.

        Args:
            deleted_by: User ID or identifier of who deleted the task
        """
        self.state.on(
            self.register_event(  # type: ignore
                TaskDeletedDomainEvent(
                    aggregate_id=self.id(),
                    title=self.state.title,
                    deleted_by=deleted_by,
                )
            )
        )
