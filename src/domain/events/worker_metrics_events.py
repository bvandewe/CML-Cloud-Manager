"""Domain events for source-specific worker metrics."""

from dataclasses import dataclass
from datetime import datetime

from neuroglia.data.abstractions import DomainEvent
from neuroglia.eventing.cloud_events.decorators import cloudevent


@cloudevent("cml_worker.ec2_metrics.updated.v1")
@dataclass
class EC2MetricsUpdatedDomainEvent(DomainEvent):
    """Event raised when EC2 instance metrics are collected from AWS EC2 API."""

    aggregate_id: str
    instance_state_detail: str  # e.g., "ok", "impaired", "insufficient-data"
    system_status_check: str  # e.g., "ok", "impaired"
    checked_at: datetime
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        instance_state_detail: str,
        system_status_check: str,
        checked_at: datetime,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.instance_state_detail = instance_state_detail
        self.system_status_check = system_status_check
        self.checked_at = checked_at
        self.updated_at = updated_at


@cloudevent("cml_worker.cloudwatch_metrics.updated.v1")
@dataclass
class CloudWatchMetricsUpdatedDomainEvent(DomainEvent):
    """Event raised when CloudWatch metrics are collected from AWS CloudWatch API."""

    aggregate_id: str
    cpu_utilization: float
    memory_utilization: float
    collected_at: datetime
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        cpu_utilization: float,
        memory_utilization: float,
        collected_at: datetime,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.cpu_utilization = cpu_utilization
        self.memory_utilization = memory_utilization
        self.collected_at = collected_at
        self.updated_at = updated_at


@cloudevent("cml_worker.cml_metrics.updated.v1")
@dataclass
class CMLMetricsUpdatedDomainEvent(DomainEvent):
    """Event raised when CML application metrics are collected from CML API."""

    aggregate_id: str
    cml_version: str | None
    system_info: dict
    system_health: dict | None
    license_info: dict | None
    ready: bool
    uptime_seconds: int | None
    labs_count: int
    synced_at: datetime
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        cml_version: str | None,
        system_info: dict,
        system_health: dict | None,
        license_info: dict | None,
        ready: bool,
        uptime_seconds: int | None,
        labs_count: int,
        synced_at: datetime,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.cml_version = cml_version
        self.system_info = system_info
        self.system_health = system_health
        self.license_info = license_info
        self.ready = ready
        self.uptime_seconds = uptime_seconds
        self.labs_count = labs_count
        self.synced_at = synced_at
        self.updated_at = updated_at


@cloudevent("cml_worker.ec2_instance_details.updated.v1")
@dataclass
class EC2InstanceDetailsUpdatedDomainEvent(DomainEvent):
    """Event raised when EC2 instance details are collected from AWS EC2 API."""

    aggregate_id: str
    public_ip: str | None
    private_ip: str | None
    instance_type: str | None
    ami_id: str | None
    ami_name: str | None
    ami_description: str | None
    ami_creation_date: str | None
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        public_ip: str | None,
        private_ip: str | None,
        instance_type: str | None,
        ami_id: str | None,
        ami_name: str | None,
        ami_description: str | None,
        ami_creation_date: str | None,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.public_ip = public_ip
        self.private_ip = private_ip
        self.instance_type = instance_type
        self.ami_id = ami_id
        self.ami_name = ami_name
        self.ami_description = ami_description
        self.ami_creation_date = ami_creation_date
        self.updated_at = updated_at
