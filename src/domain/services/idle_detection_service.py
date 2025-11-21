"""Domain service for worker idle detection."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from domain.entities.cml_worker import CMLWorker

if TYPE_CHECKING:
    from neuroglia.hosting.web import WebApplicationBuilder


class IdleDetectionService:
    """Service to determine if a CML worker is idle."""

    def is_worker_idle(self, worker: CMLWorker, idle_threshold_minutes: int) -> bool:
        """Check if a worker is idle based on metrics and activity history.

        A worker is considered idle if:
        1. It has no active labs running.
        2. It has been inactive (no user activity) for longer than the threshold.

        Args:
            worker: The CMLWorker entity to check.
            idle_threshold_minutes: The threshold in minutes to consider as idle.

        Returns:
            True if the worker is idle, False otherwise.
        """
        # 1. Check active labs (primary indicator)
        if worker.state.metrics.labs_count > 0:
            return False

        # 2. Determine last activity timestamp
        # Use explicit last_activity_at if available
        last_activity = worker.state.last_activity_at

        # Fallback to last_resumed_at (when it started running)
        if not last_activity:
            last_activity = worker.state.last_resumed_at

        # Fallback to created_at (if never resumed/paused)
        if not last_activity:
            last_activity = worker.state.created_at

        # If we still don't have a timestamp, we can't determine idleness safely
        if not last_activity:
            return False

        # 3. Calculate idle duration
        now = datetime.now(timezone.utc)

        # Ensure timezone awareness
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)

        idle_duration = now - last_activity
        idle_minutes = idle_duration.total_seconds() / 60.0

        return idle_minutes >= idle_threshold_minutes

    @classmethod
    def configure(cls, builder: "WebApplicationBuilder") -> None:
        """Configure the CMLHealthService in the dependency injection container."""
        builder.services.add_singleton(cls)
