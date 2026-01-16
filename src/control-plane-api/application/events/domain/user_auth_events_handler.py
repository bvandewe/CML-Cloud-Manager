"""
Order event handlers for Mario's Pizzeria.

These handlers process order-related domain events to implement side effects like
notifications, kitchen updates, delivery tracking, customer communications,
customer active order management, and customer notification creation.
"""

import logging

from neuroglia.mediation import DomainEventHandler

from domain.events import UserLoggedInDomainEvent

log = logging.getLogger(__name__)


class UserLoggedInDomainEventHandler(DomainEventHandler[UserLoggedInDomainEvent]):
    """Handles user logged in events - creates user session and sends welcome notification"""

    async def handle_async(self, notification: UserLoggedInDomainEvent) -> None:
        """Process user logged in event"""
        log.info("👤 User %s logged in!", notification.username)
        return None
