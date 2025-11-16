"""Domain event for CloudWatch monitoring status changes."""

from dataclasses import dataclass
from datetime import datetime

from neuroglia.data.abstractions import DomainEvent
from neuroglia.eventing.cloud_events.decorators import cloudevent


@cloudevent("cml_worker.cloudwatch_monitoring_updated.v1")
@dataclass
class CloudWatchMonitoringUpdatedDomainEvent(DomainEvent):
    """Event raised when CloudWatch detailed monitoring is enabled or disabled."""

    aggregate_id: str
    enabled: bool
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        enabled: bool,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.enabled = enabled
        self.updated_at = updated_at
