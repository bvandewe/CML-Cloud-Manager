"""Domain events for worker activity tracking and pause/resume lifecycle."""

from dataclasses import dataclass
from datetime import datetime

from neuroglia.data.abstractions import DomainEvent
from neuroglia.eventing.cloud_events.decorators import cloudevent


@cloudevent("cml_worker.activity_updated.v1")
@dataclass
class WorkerActivityUpdatedDomainEvent(DomainEvent):
    """Event raised when worker activity tracking is updated.

    This event is emitted when:
    - New telemetry events are checked
    - Last activity timestamp is updated
    - Recent activity events list is updated
    """

    aggregate_id: str  # Worker ID
    last_activity_at: datetime | None  # Last relevant user activity detected
    last_activity_check_at: datetime  # When telemetry was checked
    recent_activity_events: list[dict]  # Last N relevant events
    next_idle_check_at: datetime | None  # Next scheduled check
    target_pause_at: datetime | None  # Calculated pause time if idle
    updated_at: datetime


@cloudevent("cml_worker.paused.v1")
@dataclass
class WorkerPausedDomainEvent(DomainEvent):
    """Event raised when worker is paused (stopped in AWS).

    This event is emitted when:
    - Worker is automatically paused due to idle timeout
    - Worker is manually stopped via the application
    - External stop is detected and recorded
    """

    aggregate_id: str  # Worker ID
    pause_reason: str  # "idle_timeout" | "manual" | "external"
    paused_by: str | None  # User ID or "system" for auto-pause
    paused_at: datetime
    auto_pause_count: int  # Updated count
    manual_pause_count: int  # Updated count
    idle_duration_minutes: float | None  # For idle_timeout reason


@cloudevent("cml_worker.resumed.v1")
@dataclass
class WorkerResumedDomainEvent(DomainEvent):
    """Event raised when worker is resumed (started in AWS).

    This event is emitted when:
    - Worker is manually started via the application
    - External start is detected and recorded
    """

    aggregate_id: str  # Worker ID
    resume_reason: str  # "manual" | "external" | "auto" (future)
    resumed_by: str | None  # User ID or None for external
    resumed_at: datetime
    auto_resume_count: int  # Updated count
    manual_resume_count: int  # Updated count
    was_auto_paused: bool  # True if last pause was auto


@cloudevent("cml_worker.idle_detection_toggled.v1")
@dataclass
class IdleDetectionToggledDomainEvent(DomainEvent):
    """Event raised when idle detection is enabled or disabled for a worker.

    This event is emitted when:
    - Idle detection is enabled for a worker
    - Idle detection is disabled for a worker
    """

    aggregate_id: str  # Worker ID
    is_enabled: bool  # True if enabled, False if disabled
    toggled_by: str | None  # User ID who toggled the setting
    toggled_at: datetime  # When the toggle occurred
