"""API request models."""

from .cml_worker_requests import (
    CreateCMLWorkerRequest,
    ImportCMLWorkerRequest,
    RegisterLicenseRequest,
    UpdateCMLWorkerTagsRequest,
)

__all__ = [
    "CreateCMLWorkerRequest",
    "ImportCMLWorkerRequest",
    "RegisterLicenseRequest",
    "UpdateCMLWorkerTagsRequest",
]
