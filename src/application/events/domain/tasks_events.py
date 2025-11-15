"""
These handlers process task-related domain events to implement side effects.
"""

import logging

from neuroglia.mediation import DomainEventHandler

from domain.events import TaskCreatedDomainEvent

# Set up logger
logger = logging.getLogger(__name__)


class TaskCreatedDomainEventHandler(DomainEventHandler[TaskCreatedDomainEvent]):
    """Handles task created events - sends notifications and updates task status"""

    async def handle_async(self, notification: TaskCreatedDomainEvent) -> None:
        """Process task created event"""
        logger.info(
            "✅ Task '%s':'%s' created!",
            notification.aggregate_id,
            notification.title,
        )
        return None
