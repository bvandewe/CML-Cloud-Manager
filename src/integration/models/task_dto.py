import datetime
import logging

from neuroglia.utils import CamelModel

from domain.enums import TaskPriority, TaskStatus

log = logging.getLogger(__name__)


class TaskCreatedDto(CamelModel):
    id: str
    """The unique identifier of the Task."""

    title: str
    """The title of the Task."""

    description: str
    """The description of the Task."""

    status: TaskStatus
    """The status of the Task."""

    priority: TaskPriority
    """The priority of the Task."""

    assignee_id: str | None = None
    """The id of the user assigned to the Task."""

    department: str | None = None
    """The department responsible for the Task."""

    created_at: datetime.datetime
    """The date and time when the Task was created."""

    created_by: str | None = None
    """The id of the user who created the Task."""
