"""Value objects for CML Worker domain."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AWSInstanceDetails:
    """Value object representing AWS EC2 instance details."""

    instance_id: str
    instance_type: str
    region: str
    ami_id: str | None = None
    ami_name: str | None = None
    ami_description: str | None = None
    ami_creation_date: str | None = None
    public_ip: str | None = None
    private_ip: str | None = None
    availability_zone: str | None = None

    def __post_init__(self) -> None:
        """Validate instance details."""
        if not self.instance_id:
            raise ValueError("instance_id cannot be empty")
        if not self.instance_type:
            raise ValueError("instance_type cannot be empty")
        if not self.region:
            raise ValueError("region cannot be empty")


@dataclass(frozen=True)
class CMLEndpoint:
    """Value object representing CML HTTPS endpoint details."""

    https_url: str
    api_url: str | None = None
    public_ip: str | None = None

    def __post_init__(self) -> None:
        """Validate endpoint URL."""
        if not self.https_url:
            raise ValueError("https_url cannot be empty")
        if not self.https_url.startswith(("https://", "http://")):
            raise ValueError("https_url must start with https:// or http://")


@dataclass(frozen=True)
class WorkerTelemetry:
    """Value object representing worker telemetry snapshot."""

    active_labs_count: int
    cpu_utilization: float | None = None
    memory_utilization: float | None = None
    disk_utilization: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None

    def __post_init__(self) -> None:
        """Validate telemetry values."""
        if self.active_labs_count < 0:
            raise ValueError("active_labs_count cannot be negative")
        if self.cpu_utilization is not None and not 0 <= self.cpu_utilization <= 100:
            raise ValueError("cpu_utilization must be between 0 and 100")
        if self.memory_utilization is not None and not 0 <= self.memory_utilization <= 100:
            raise ValueError("memory_utilization must be between 0 and 100")
        if self.disk_utilization is not None and not 0 <= self.disk_utilization <= 100:
            raise ValueError("disk_utilization must be between 0 and 100")

    def is_idle(self) -> bool:
        """Check if the worker appears to be idle based on telemetry."""
        return self.active_labs_count == 0
