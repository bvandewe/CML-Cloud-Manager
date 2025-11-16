
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CMLLicense:
    """A Value Object representing the CML license details."""
    status: str  # e.g., "REGISTERED", "UNREGISTERED", "EVALUATION"
    expiry_date: date | None = None
    features: tuple[str, ...] = () # Immutable tuple of licensed features
