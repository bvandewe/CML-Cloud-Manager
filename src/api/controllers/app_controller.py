"""Application health check controller."""
import logging

from classy_fastapi.decorators import get
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.mvc import ControllerBase

log = logging.getLogger(__name__)


class AppController(ControllerBase):
    """Controller for application health checks."""

    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
        super().__init__(service_provider, mapper, mediator)

    @get("/health")
    async def ping(self) -> dict:
        """Health check endpoint to verify the application is online."""
        return {
            "online": True,
            "status": "healthy",
            "detail": "The application is online and running."
        }
