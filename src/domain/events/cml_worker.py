"""Domain events for CML Worker aggregate operations."""

from dataclasses import dataclass
from datetime import datetime

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
    aws_instance_id: str | None
    instance_type: str
    ami_id: str | None
    ami_name: str | None
    ami_description: str | None
    ami_creation_date: str | None
    status: CMLWorkerStatus
    cml_version: str | None
    created_at: datetime
    created_by: str | None

    def __init__(
        self,
        aggregate_id: str,
        name: str,
        aws_region: str,
        aws_instance_id: str | None,
        instance_type: str,
        ami_id: str | None,
        ami_name: str | None,
        ami_description: str | None,
        ami_creation_date: str | None,
        status: CMLWorkerStatus,
        cml_version: str | None,
        created_at: datetime,
        created_by: str | None,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.name = name
        self.aws_region = aws_region
        self.aws_instance_id = aws_instance_id
        self.instance_type = instance_type
        self.ami_id = ami_id
        self.ami_name = ami_name
        self.ami_description = ami_description
        self.ami_creation_date = ami_creation_date
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
    transition_initiated_at: datetime | None

    def __init__(
        self,
        aggregate_id: str,
        old_status: CMLWorkerStatus,
        new_status: CMLWorkerStatus,
        updated_at: datetime,
        transition_initiated_at: datetime | None = None,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.old_status = old_status
        self.new_status = new_status
        self.updated_at = updated_at
        self.transition_initiated_at = transition_initiated_at


@cloudevent("cml_worker.service.status.updated.v1")
@dataclass
class CMLServiceStatusUpdatedDomainEvent(DomainEvent):
    """Event raised when CML HTTPS service status changes."""

    aggregate_id: str
    old_service_status: CMLServiceStatus
    new_service_status: CMLServiceStatus
    https_endpoint: str | None
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        old_service_status: CMLServiceStatus,
        new_service_status: CMLServiceStatus,
        https_endpoint: str | None,
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
    public_ip: str | None
    private_ip: str | None
    assigned_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        aws_instance_id: str,
        public_ip: str | None,
        private_ip: str | None,
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
    license_token: str | None
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        license_status: LicenseStatus,
        license_token: str | None,
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
    cpu_utilization: float | None
    memory_utilization: float | None
    updated_at: datetime
    poll_interval: int | None  # Metrics collection interval in seconds
    next_refresh_at: datetime | None  # Next scheduled metrics collection time

    def __init__(
        self,
        aggregate_id: str,
        last_activity_at: datetime,
        active_labs_count: int,
        cpu_utilization: float | None,
        memory_utilization: float | None,
        updated_at: datetime,
        poll_interval: int | None = None,
        next_refresh_at: datetime | None = None,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.last_activity_at = last_activity_at
        self.active_labs_count = active_labs_count
        self.cpu_utilization = cpu_utilization
        self.memory_utilization = memory_utilization
        self.updated_at = updated_at
        self.poll_interval = poll_interval
        self.next_refresh_at = next_refresh_at


@cloudevent("cml_worker.endpoint.updated.v1")
@dataclass
class CMLWorkerEndpointUpdatedDomainEvent(DomainEvent):
    """Event raised when worker HTTPS endpoint is updated."""

    aggregate_id: str
    https_endpoint: str | None
    public_ip: str | None
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        https_endpoint: str | None,
        public_ip: str | None,
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.https_endpoint = https_endpoint
        self.public_ip = public_ip
        self.updated_at = updated_at


@cloudevent("cml_worker.imported.v1")
@dataclass
class CMLWorkerImportedDomainEvent(DomainEvent):
    """Event raised when an existing EC2 instance is imported as a CML Worker.

    This event is used when registering pre-existing EC2 instances that were
    created outside of the CML Cloud Manager system (e.g., via AWS Console,
    Terraform, CloudFormation, or other tools).
    """

    aggregate_id: str
    name: str
    aws_region: str
    aws_instance_id: str
    instance_type: str
    ami_id: str
    ami_name: str | None
    ami_description: str | None
    ami_creation_date: str | None
    instance_state: str
    public_ip: str | None
    private_ip: str | None
    created_by: str | None
    created_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        name: str,
        aws_region: str,
        aws_instance_id: str,
        instance_type: str,
        ami_id: str,
        ami_name: str | None,
        ami_description: str | None,
        ami_creation_date: str | None,
        instance_state: str,
        public_ip: str | None,
        private_ip: str | None,
        created_by: str | None,
        created_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.name = name
        self.aws_region = aws_region
        self.aws_instance_id = aws_instance_id
        self.instance_type = instance_type
        self.ami_id = ami_id
        self.ami_name = ami_name
        self.ami_description = ami_description
        self.ami_creation_date = ami_creation_date
        self.instance_state = instance_state
        self.public_ip = public_ip
        self.private_ip = private_ip
        self.created_by = created_by
        self.created_at = created_at


@cloudevent("cml_worker.terminated.v1")
@dataclass
class CMLWorkerTerminatedDomainEvent(DomainEvent):
    """Event raised when CML Worker is terminated."""

    aggregate_id: str
    name: str
    terminated_at: datetime
    terminated_by: str | None

    def __init__(
        self,
        aggregate_id: str,
        name: str,
        terminated_at: datetime,
        terminated_by: str | None,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.name = name
        self.terminated_at = terminated_at
        self.terminated_by = terminated_by


@cloudevent("cml_worker.tags.updated.v1")
@dataclass
class CMLWorkerTagsUpdatedDomainEvent(DomainEvent):
    """Event raised when CML Worker AWS tags are updated."""

    aggregate_id: str
    aws_tags: dict[str, str]
    updated_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        aws_tags: dict[str, str],
        updated_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.aws_tags = aws_tags
        self.updated_at = updated_at


@cloudevent("cml_worker.license.registration.started.v1")
@dataclass
class CMLWorkerLicenseRegistrationStartedDomainEvent(DomainEvent):
    """Event raised when license registration starts."""

    aggregate_id: str
    worker_id: str
    started_at: str
    initiated_by: str

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        started_at: str,
        initiated_by: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.started_at = started_at
        self.initiated_by = initiated_by


@cloudevent("cml_worker.license.registration.completed.v1")
@dataclass
class CMLWorkerLicenseRegistrationCompletedDomainEvent(DomainEvent):
    """Event raised when license registration completes successfully."""

    aggregate_id: str
    worker_id: str
    registration_status: str
    smart_account: str | None
    virtual_account: str | None
    completed_at: str

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        registration_status: str,
        smart_account: str | None,
        virtual_account: str | None,
        completed_at: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.registration_status = registration_status
        self.smart_account = smart_account
        self.virtual_account = virtual_account
        self.completed_at = completed_at


@cloudevent("cml_worker.license.registration.failed.v1")
@dataclass
class CMLWorkerLicenseRegistrationFailedDomainEvent(DomainEvent):
    """Event raised when license registration fails."""

    aggregate_id: str
    worker_id: str
    error_message: str
    error_code: str | None
    failed_at: str

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        error_message: str,
        error_code: str | None,
        failed_at: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.error_message = error_message
        self.error_code = error_code
        self.failed_at = failed_at


@cloudevent("cml_worker.license.deregistered.v1")
@dataclass
class CMLWorkerLicenseDeregisteredDomainEvent(DomainEvent):
    """Event raised when license is deregistered."""

    aggregate_id: str
    worker_id: str
    deregistered_at: str
    initiated_by: str

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        deregistered_at: str,
        initiated_by: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.deregistered_at = deregistered_at
        self.initiated_by = initiated_by


@cloudevent("cml_worker.data_refresh.requested.v1")
@dataclass
class WorkerDataRefreshRequestedDomainEvent(DomainEvent):
    """Event raised when on-demand worker data refresh is requested."""

    aggregate_id: str
    worker_id: str
    requested_at: str
    requested_by: str | None

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        requested_at: str,
        requested_by: str | None = None,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.requested_at = requested_at
        self.requested_by = requested_by


@cloudevent("cml_worker.data_refresh.skipped.v1")
@dataclass
class WorkerDataRefreshSkippedDomainEvent(DomainEvent):
    """Event raised when worker data refresh is skipped (e.g., too frequent)."""

    aggregate_id: str
    worker_id: str
    reason: str
    skipped_at: str

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        reason: str,
        skipped_at: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.reason = reason
        self.skipped_at = skipped_at


@cloudevent("cml_worker.data_refresh.completed.v1")
@dataclass
class WorkerDataRefreshCompletedDomainEvent(DomainEvent):
    """Event raised when worker data refresh completes successfully."""

    aggregate_id: str
    worker_id: str
    completed_at: str
    refresh_type: str  # 'scheduled' or 'on_demand'

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        completed_at: str,
        refresh_type: str,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.completed_at = completed_at
        self.refresh_type = refresh_type
