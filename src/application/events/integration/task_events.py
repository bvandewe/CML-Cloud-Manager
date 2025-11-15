from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from neuroglia.eventing.cloud_events.decorators import cloudevent
from neuroglia.integration.models import IntegrationEvent

from domain.enums import TaskPriority, TaskStatus


@cloudevent("com.source.task.creation.requested.v1")
@dataclass
class TaskCreationRequestedIntegrationEventV1(IntegrationEvent[str]):
    """Incoming CloudEvent"""

    aggregate_id: str
    created_at: datetime
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: str | None = None
    department: str | None = None


# @cloudevent("task.created.v1")
# @dataclass
# class TaskCreatedIntegrationEventV1(IntegrationEvent[str]):
#     """Outgoing CloudEvent"""

#     aggregate_id: str
#     created_at: datetime
#     title: str = ""
#     description: str = ""
#     status: TaskStatus = TaskStatus.PENDING
#     priority: TaskPriority = TaskPriority.MEDIUM
#     assignee_id: str | None = None
#     department: str | None = None
