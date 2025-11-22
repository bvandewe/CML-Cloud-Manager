from dataclasses import dataclass
from datetime import date
from typing import Any

from domain.enums import LicenseStatus


@dataclass(frozen=True)
class CMLLicense:
    """A Value Object representing the CML license details."""

    status: LicenseStatus = LicenseStatus.UNREGISTERED
    token: str | None = None
    operation_in_progress: bool = False
    expiry_date: date | None = None
    features: tuple[str, ...] = ()  # Immutable tuple of licensed features
    raw_info: dict[str, Any] | None = None
