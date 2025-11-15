"""Domain events for Task aggregate operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from neuroglia.data.abstractions import DomainEvent
from neuroglia.eventing.cloud_events.decorators import cloudevent

from domain.enums import TaskPriority, TaskStatus


@cloudevent("task.created.v1")
@dataclass
class TaskCreatedDomainEvent(DomainEvent):
    """Event raised when a new task aggregate is created."""

    aggregate_id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    assignee_id: Optional[str]
    department: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    def __init__(
        self,
        aggregate_id: str,
        title: str,
        description: str,
        status: TaskStatus,
        priority: TaskPriority,
        assignee_id: Optional[str],
        department: Optional[str],
        created_at: datetime,
        updated_at: datetime,
        created_by: Optional[str],
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.assignee_id = assignee_id
        self.department = department
        self.created_at = created_at
        self.updated_at = updated_at
        self.created_by = created_by


@cloudevent("task.title.updated.v1")
@dataclass
class TaskTitleUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's title is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_title: str,
    ):
        super().__init__(aggregate_id)
        self.new_title = new_title

    aggregate_id: str
    new_title: str


@cloudevent("task.description.updated.v1")
@dataclass
class TaskDescriptionUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's description is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_description: str,
    ):
        super().__init__(aggregate_id)
        self.new_description = new_description

    aggregate_id: str
    new_description: str


@cloudevent("task.status.updated.v1")
@dataclass
class TaskStatusUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's status is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_status: TaskStatus,
    ):
        super().__init__(aggregate_id)
        self.new_status = new_status

    aggregate_id: str
    new_status: TaskStatus


@cloudevent("task.priority.updated.v1")
@dataclass
class TaskPriorityUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's priority is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_priority: TaskPriority,
    ):
        super().__init__(aggregate_id)
        self.new_priority = new_priority

    aggregate_id: str
    new_priority: TaskPriority


@cloudevent("task.assignee.updated.v1")
@dataclass
class TaskAssigneeUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's assignee is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_assignee_id: str | None,
    ):
        super().__init__(aggregate_id)
        self.new_assignee_id = new_assignee_id

    aggregate_id: str
    new_assignee_id: str | None


@cloudevent("task.department.updated.v1")
@dataclass
class TaskDepartmentUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task's department is updated."""

    def __init__(
        self,
        aggregate_id: str,
        new_department: str | None,
    ):
        super().__init__(aggregate_id)
        self.new_department = new_department

    aggregate_id: str
    new_department: str | None


@cloudevent("task.deleted.v1")
@dataclass
class TaskDeletedDomainEvent(DomainEvent):
    """Event raised when a task is deleted."""

    def __init__(
        self,
        aggregate_id: str,
        title: str,
        deleted_by: Optional[str] = None,
    ):
        super().__init__(aggregate_id)
        self.title = title
        self.deleted_by = deleted_by

    aggregate_id: str
    title: str
    deleted_by: Optional[str]


@cloudevent("task.updated.v1")
@dataclass
class TaskUpdatedDomainEvent(DomainEvent):
    """Event raised when an existing task is updated."""

    def __init__(
        self,
        aggregate_id: str,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: str | None = None,
    ):
        super().__init__(aggregate_id)
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.assignee_id = assignee_id

    aggregate_id: str
    title: str | None
    description: str | None
    status: TaskStatus | None
    priority: TaskPriority | None
    assignee_id: str | None
    department: str | None
    updated_at: datetime
