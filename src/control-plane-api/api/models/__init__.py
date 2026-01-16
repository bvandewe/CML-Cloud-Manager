"""API request models."""

from .cml_worker_requests import (
    CreateCMLWorkerRequest,
    DeleteCMLWorkerRequest,
    ImportCMLWorkerRequest,
    RegisterLicenseRequest,
    UpdateCMLWorkerTagsRequest,
)
from .system_settings_requests import UpdateSystemSettingsRequest

__all__ = [
    "CreateCMLWorkerRequest",
    "DeleteCMLWorkerRequest",
    "ImportCMLWorkerRequest",
    "RegisterLicenseRequest",
    "UpdateCMLWorkerTagsRequest",
    "UpdateSystemSettingsRequest",
]
