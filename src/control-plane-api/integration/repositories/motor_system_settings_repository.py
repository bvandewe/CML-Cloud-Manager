"""
MongoDB repository for SystemSettings entities using Neuroglia's MotorRepository.
"""

import logging
from typing import TYPE_CHECKING, Optional, cast

from motor.motor_asyncio import AsyncIOMotorClient
from neuroglia.data.infrastructure.mongo import MotorRepository
from neuroglia.data.infrastructure.tracing_mixin import TracedRepositoryMixin
from neuroglia.serialization.json import JsonSerializer

from domain.entities.system_settings import SystemSettings
from domain.repositories.system_settings_repository import SystemSettingsRepository

if TYPE_CHECKING:
    from neuroglia.mediation.mediator import Mediator

log = logging.getLogger(__name__)


class MongoSystemSettingsRepository(TracedRepositoryMixin, MotorRepository[SystemSettings, str], SystemSettingsRepository):  # type: ignore[misc]
    """
    Motor-based async MongoDB repository for SystemSettings entities.
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        database_name: str,
        collection_name: str,
        serializer: JsonSerializer,
        entity_type: type[SystemSettings] | None = None,
        mediator: Optional["Mediator"] = None,
    ):
        super().__init__(
            client=client,
            database_name=database_name,
            collection_name=collection_name,
            serializer=serializer,
            entity_type=entity_type,
            mediator=mediator,
        )

    async def get_default_async(self) -> SystemSettings:
        """Get the default system settings (singleton)."""
        settings = await self.get_async("default")
        if not settings:
            settings = SystemSettings.create_default()
            await self.add_async(settings)
        return cast(SystemSettings, settings)
