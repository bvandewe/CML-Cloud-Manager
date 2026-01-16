"""System Settings API request models."""

from typing import Any

from pydantic import BaseModel


class UpdateSystemSettingsRequest(BaseModel):
    """Request model for updating system settings."""

    worker_provisioning: dict[str, Any] | None = None
    monitoring: dict[str, Any] | None = None
    idle_detection: dict[str, Any] | None = None
