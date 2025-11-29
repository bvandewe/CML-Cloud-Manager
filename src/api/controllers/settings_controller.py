"""System Settings Controller."""

import logging
from typing import Any

from classy_fastapi.decorators import get, put
from fastapi import Depends
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles
from api.models import UpdateSystemSettingsRequest
from application.commands.update_system_settings_command import UpdateSystemSettingsCommand
from application.queries.get_system_settings_query import GetSystemSettingsQuery

logger = logging.getLogger(__name__)


class SettingsController(ControllerBase):
    """Controller for managing system settings."""

    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
        ControllerBase.__init__(self, service_provider, mapper, mediator)

    @get(
        "/",
        response_model=dict[str, Any],
        response_description="System Settings",
        status_code=200,
        responses=ControllerBase.error_responses,
        dependencies=[Depends(require_roles("admin"))],
    )
    async def get_settings(
        self,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Get system settings.

        (**Requires admin role.**)
        """
        query = GetSystemSettingsQuery()
        return self.process(await self.mediator.execute_async(query))

    @put(
        "/",
        response_model=dict[str, Any],
        response_description="Updated System Settings",
        status_code=200,
        responses=ControllerBase.error_responses,
        dependencies=[Depends(require_roles("admin"))],
    )
    async def update_settings(
        self,
        request: UpdateSystemSettingsRequest,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Update system settings.

        (**Requires admin role.**)
        """
        command = UpdateSystemSettingsCommand(
            worker_provisioning=request.worker_provisioning,
            monitoring=request.monitoring,
            idle_detection=request.idle_detection,
            updated_by="admin",  # In a real app, extract user from token
        )
        return self.process(await self.mediator.execute_async(command))
