"""API request models."""

from .cml_worker_requests import (
    CreateCMLWorkerRequest,
    DeleteCMLWorkerRequest,
    ImportCMLWorkerRequest,
    RegisterLicenseRequest,
    UpdateCMLWorkerTagsRequest,
)

__all__ = [
    "CreateCMLWorkerRequest",
    "DeleteCMLWorkerRequest",
    "ImportCMLWorkerRequest",
    "RegisterLicenseRequest",
    "UpdateCMLWorkerTagsRequest",
]
