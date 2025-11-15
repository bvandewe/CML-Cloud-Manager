"""!!!! UNUSED - SAMPLE ONLY !!!!

Task entity for the domain layer.

This is a sample implementation with a simple Entity instead of the full
AggregateRoot with AggregateState and DomainEvents.

The MotorRepository supports both transparently but Application code must
be adjusted to:

- use task.state.* instead of task.* (that is: any task attribute is in its state!)
- use task.state.id() instead of task.id (that is: AggregateRoot's id is a callable)

"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from neuroglia.data import Entity
from neuroglia.mapping.mapper import map_to

from domain.enums import TaskPriority, TaskStatus
from integration.models import TaskCreatedDto


@map_to(TaskCreatedDto)
@dataclass
class Task(Entity[str]):
    """Task domain entity."""

    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: str | None = None
    department: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str | None = None
