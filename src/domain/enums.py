from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CMLWorkerStatus(str, Enum):
    """AWS EC2 instance states for CML Worker."""
    PENDING = "pending"  # Instance is being launched
    STARTING = "starting"  # Instance is starting < TBC if needed!
    RUNNING = "running"  # Instance is running
    STOPPING = "stopping"  # Instance is being stopped
    STOPPED = "stopped"  # Instance is stopped
    SHUTTING_DOWN = "shutting-down"  # Instance is being terminated
    TERMINATED = "terminated"  # Instance is terminated
    UNKNOWN = "unknown"  # Status cannot be determined


class CMLServiceStatus(str, Enum):
    """CML HTTPS service availability status."""
    UNAVAILABLE = "unavailable"  # Service not accessible
    STARTING = "starting"  # Service is starting up
    AVAILABLE = "available"  # Service is accessible via HTTPS
    ERROR = "error"  # Service encountered an error


class LicenseStatus(str, Enum):
    """CML license registration status."""
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    EVALUATION = "evaluation"
    EXPIRED = "expired"
    INVALID = "invalid"
