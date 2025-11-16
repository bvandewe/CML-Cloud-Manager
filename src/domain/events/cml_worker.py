"""Domain events for CML Worker aggregate operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from neuroglia.data.abstractions import DomainEvent
from neuroglia.eventing.cloud_events.decorators import cloudevent

from domain.enums import CMLServiceStatus, CMLWorkerStatus, LicenseStatus


@cloudevent("cml_worker.created.v1")
@dataclass
class CMLWorkerCreatedDomainEvent(DomainEvent):
    """Event raised when a new CML Worker is created."""

    aggregate_id: str
    name: str
    aws_region: str
    aws_instance_id: Optional[str]
    instance_type: str
    ami_id: Optional[str]
    ami_name: Optional[str]
    status: CMLWorkerStatus
    cml_version: Optional[str]
    created_at: datetime
    created_by: Optional[str]

    def __init__(
        self,
        aggregate_id: str,
        name: str,
        aws_region: str,
        aws_instance_id: Optional[str],
        instance_type: str,
        ami_id: Optional[str],
        ami_name: Optional[str],
        status: CMLWorkerStatus,
        cml_version: Optional[str],
        created_at: datetime,
        created_by: Optional[str],
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.name = name
        self.aws_region = aws_region
        self.aws_instance_id = aws_instance_id
        self.instance_type = instance_type
        self.ami_id = ami_id
        self.ami_name = ami_name
        self.status = status
        self.cml_version = cml_version
        self.created_at = created_at
        self.created_by = created_by


@cloudevent("cml_worker.status.updated.v1")
@dataclass
class CMLWorkerStatusUpdatedDomainEvent(DomainEvent):
    """Event raised when CML Worker EC2 instance status changes."""

    aggregate_id: str
    old_status: CMLWorkerStatus
    new_status: CMLWorkerStatus
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        old_status: CMLWorkerStatus,
        new_status: CMLWorkerStatus,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.old_status = old_status
        self.new_status = new_status
        self.updated_at = updated_at


@cloudevent("cml_worker.service.status.updated.v1")
@dataclass
class CMLServiceStatusUpdatedDomainEvent(DomainEvent):
    """Event raised when CML HTTPS service status changes."""

    aggregate_id: str
    old_service_status: CMLServiceStatus
    new_service_status: CMLServiceStatus
    https_endpoint: Optional[str]
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        old_service_status: CMLServiceStatus,
        new_service_status: CMLServiceStatus,
        https_endpoint: Optional[str],
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.old_service_status = old_service_status
        self.new_service_status = new_service_status
        self.https_endpoint = https_endpoint
        self.updated_at = updated_at


@cloudevent("cml_worker.instance.assigned.v1")
@dataclass
class CMLWorkerInstanceAssignedDomainEvent(DomainEvent):
    """Event raised when AWS EC2 instance ID is assigned to worker."""

    aggregate_id: str
    aws_instance_id: str
    public_ip: Optional[str]
    private_ip: Optional[str]
    assigned_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        aws_instance_id: str,
        public_ip: Optional[str],
        private_ip: Optional[str],
        assigned_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.aws_instance_id = aws_instance_id
        self.public_ip = public_ip
        self.private_ip = private_ip
        self.assigned_at = assigned_at


@cloudevent("cml_worker.license.updated.v1")
@dataclass
class CMLWorkerLicenseUpdatedDomainEvent(DomainEvent):
    """Event raised when CML license status is updated."""

    aggregate_id: str
    license_status: LicenseStatus
    license_token: Optional[str]
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        license_status: LicenseStatus,
        license_token: Optional[str],
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.license_status = license_status
        self.license_token = license_token
        self.updated_at = updated_at


@cloudevent("cml_worker.telemetry.updated.v1")
@dataclass
class CMLWorkerTelemetryUpdatedDomainEvent(DomainEvent):
    """Event raised when worker telemetry data is collected."""

    aggregate_id: str
    last_activity_at: datetime
    active_labs_count: int
    cpu_utilization: Optional[float]
    memory_utilization: Optional[float]
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        last_activity_at: datetime,
        active_labs_count: int,
        cpu_utilization: Optional[float],
        memory_utilization: Optional[float],
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.last_activity_at = last_activity_at
        self.active_labs_count = active_labs_count
        self.cpu_utilization = cpu_utilization
        self.memory_utilization = memory_utilization
        self.updated_at = updated_at


@cloudevent("cml_worker.endpoint.updated.v1")
@dataclass
class CMLWorkerEndpointUpdatedDomainEvent(DomainEvent):
    """Event raised when worker HTTPS endpoint is updated."""

    aggregate_id: str
    https_endpoint: Optional[str]
    public_ip: Optional[str]
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        https_endpoint: Optional[str],
        public_ip: Optional[str],
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.https_endpoint = https_endpoint
        self.public_ip = public_ip
        self.updated_at = updated_at


@cloudevent("cml_worker.terminated.v1")
@dataclass
class CMLWorkerTerminatedDomainEvent(DomainEvent):
    """Event raised when CML Worker is terminated."""

    aggregate_id: str
    name: str
    terminated_at: datetime
    terminated_by: Optional[str]

    def __init__(
        self,
        aggregate_id: str,
        name: str,
        terminated_at: datetime,
        terminated_by: Optional[str],
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.name = name
        self.terminated_at = terminated_at
        self.terminated_by = terminated_by
