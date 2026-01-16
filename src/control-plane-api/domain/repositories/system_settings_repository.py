"""Repository interface for SystemSettings."""

from abc import ABC, abstractmethod

from domain.entities.system_settings import SystemSettings


class SystemSettingsRepository(ABC):
    """Interface for SystemSettings repository."""

    @abstractmethod
    async def get_default_async(self) -> SystemSettings:
        """Get the default system settings (singleton)."""
        ...

    @abstractmethod
    async def add_async(self, entity: SystemSettings) -> SystemSettings:
        """Add a new system settings."""
        ...

    @abstractmethod
    async def update_async(self, entity: SystemSettings) -> SystemSettings:
        """Update an existing system settings."""
        ...
