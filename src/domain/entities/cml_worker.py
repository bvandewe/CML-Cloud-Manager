"""CML Worker aggregate definition using the AggregateState pattern.

The CML Worker represents an AWS EC2 instance running Cisco Modeling Lab.
It manages the lifecycle of the instance, monitors telemetry, and provides
access to CML labs hosted on the instance.
"""

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from multipledispatch import dispatch
from neuroglia.data.abstractions import AggregateRoot, AggregateState

from domain.enums import CMLServiceStatus, CMLWorkerStatus, LicenseStatus
from domain.events.cml_worker import (
    CMLServiceStatusUpdatedDomainEvent,
    CMLWorkerCreatedDomainEvent,
    CMLWorkerEndpointUpdatedDomainEvent,
    CMLWorkerImportedDomainEvent,
    CMLWorkerInstanceAssignedDomainEvent,
    CMLWorkerLicenseUpdatedDomainEvent,
    CMLWorkerStatusUpdatedDomainEvent,
    CMLWorkerTelemetryUpdatedDomainEvent,
    CMLWorkerTerminatedDomainEvent,
)


class CMLWorkerState(AggregateState[str]):
    """Encapsulates the persisted state for the CML Worker aggregate."""

    id: str
    name: str
    aws_region: str
    aws_instance_id: str | None
    instance_type: str
    ami_id: str | None
    ami_name: str | None
    status: CMLWorkerStatus
    service_status: CMLServiceStatus

    # CML-specific attributes
    cml_version: str | None
    license_status: LicenseStatus
    license_token: str | None
    https_endpoint: str | None

    # Network details
    public_ip: str | None
    private_ip: str | None

    # Telemetry and monitoring
    last_activity_at: datetime | None
    active_labs_count: int
    cpu_utilization: float | None
    memory_utilization: float | None

    # Lifecycle timestamps
    created_at: datetime
    updated_at: datetime
    terminated_at: datetime | None

    # Audit
    created_by: str | None
    terminated_by: str | None

    def __init__(self) -> None:
        super().__init__()
        self.id = ""
        self.name = ""
        self.aws_region = ""
        self.aws_instance_id = None
        self.instance_type = ""
        self.ami_id = None
        self.ami_name = None
        self.status = CMLWorkerStatus.PENDING
        self.service_status = CMLServiceStatus.UNAVAILABLE

        self.cml_version = None
        self.license_status = LicenseStatus.UNREGISTERED
        self.license_token = None
        self.https_endpoint = None

        self.public_ip = None
        self.private_ip = None

        self.last_activity_at = None
        self.active_labs_count = 0
        self.cpu_utilization = None
        self.memory_utilization = None

        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now
        self.terminated_at = None

        self.created_by = None
        self.terminated_by = None

    @dispatch(CMLWorkerCreatedDomainEvent)
    def on(self, event: CMLWorkerCreatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the creation event to the state."""
        self.id = event.aggregate_id
        self.name = event.name
        self.aws_region = event.aws_region
        self.aws_instance_id = event.aws_instance_id
        self.instance_type = event.instance_type
        self.ami_id = event.ami_id
        self.ami_name = event.ami_name
        self.status = event.status
        self.cml_version = event.cml_version
        self.created_at = event.created_at
        self.updated_at = event.created_at
        self.created_by = event.created_by

    @dispatch(CMLWorkerImportedDomainEvent)
    def on(self, event: CMLWorkerImportedDomainEvent) -> None:  # type: ignore[override]
        """Apply the import event to the state."""
        self.id = event.aggregate_id
        self.name = event.name
        self.aws_region = event.aws_region
        self.aws_instance_id = event.aws_instance_id
        self.instance_type = event.instance_type
        self.ami_id = event.ami_id
        self.ami_name = event.ami_name
        self.public_ip = event.public_ip
        self.private_ip = event.private_ip
        self.created_at = event.created_at
        self.updated_at = event.created_at
        self.created_by = event.created_by

        # Map EC2 instance state to CMLWorkerStatus
        if event.instance_state == "running":
            self.status = CMLWorkerStatus.RUNNING
        elif event.instance_state == "stopped":
            self.status = CMLWorkerStatus.STOPPED
        elif event.instance_state == "stopping":
            self.status = CMLWorkerStatus.STOPPING
        elif event.instance_state == "pending":
            self.status = CMLWorkerStatus.PENDING
        else:
            self.status = CMLWorkerStatus.UNKNOWN

    @dispatch(CMLWorkerStatusUpdatedDomainEvent)
    def on(self, event: CMLWorkerStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the status updated event to the state."""
        self.status = event.new_status
        self.updated_at = event.updated_at

    @dispatch(CMLServiceStatusUpdatedDomainEvent)
    def on(self, event: CMLServiceStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the service status updated event to the state."""
        self.service_status = event.new_service_status
        if event.https_endpoint:
            self.https_endpoint = event.https_endpoint
        self.updated_at = event.updated_at

    @dispatch(CMLWorkerInstanceAssignedDomainEvent)
    def on(self, event: CMLWorkerInstanceAssignedDomainEvent) -> None:  # type: ignore[override]
        """Apply the instance assigned event to the state."""
        self.aws_instance_id = event.aws_instance_id
        self.public_ip = event.public_ip
        self.private_ip = event.private_ip
        self.updated_at = event.assigned_at

    @dispatch(CMLWorkerLicenseUpdatedDomainEvent)
    def on(self, event: CMLWorkerLicenseUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the license updated event to the state."""
        self.license_status = event.license_status
        self.license_token = event.license_token
        self.updated_at = event.updated_at

    @dispatch(CMLWorkerTelemetryUpdatedDomainEvent)
    def on(self, event: CMLWorkerTelemetryUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the telemetry updated event to the state."""
        self.last_activity_at = event.last_activity_at
        self.active_labs_count = event.active_labs_count
        self.cpu_utilization = event.cpu_utilization
        self.memory_utilization = event.memory_utilization
        self.updated_at = event.updated_at

    @dispatch(CMLWorkerEndpointUpdatedDomainEvent)
    def on(self, event: CMLWorkerEndpointUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the endpoint updated event to the state."""
        self.https_endpoint = event.https_endpoint
        if event.public_ip:
            self.public_ip = event.public_ip
        self.updated_at = event.updated_at

    @dispatch(CMLWorkerTerminatedDomainEvent)
    def on(self, event: CMLWorkerTerminatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the terminated event to the state."""
        self.status = CMLWorkerStatus.TERMINATED
        self.service_status = CMLServiceStatus.UNAVAILABLE
        self.terminated_at = event.terminated_at
        self.terminated_by = event.terminated_by
        self.updated_at = event.terminated_at


class CMLWorker(AggregateRoot[CMLWorkerState, str]):
    """CML Worker aggregate root following the AggregateState pattern.

    Represents an AWS EC2 instance running Cisco Modeling Lab (CML).
    """

    def __init__(
        self,
        name: str,
        aws_region: str,
        instance_type: str,
        ami_id: str | None = None,
        ami_name: str | None = None,
        aws_instance_id: str | None = None,
        status: CMLWorkerStatus = CMLWorkerStatus.PENDING,
        cml_version: str | None = None,
        created_at: datetime | None = None,
        created_by: str | None = None,
        worker_id: str | None = None,
    ) -> None:
        """Initialize a new CML Worker.

        Args:
            name: Human-readable name for the worker
            aws_region: AWS region where the instance is/will be hosted
            instance_type: EC2 instance type (e.g., 't3.xlarge', 'c5.2xlarge')
            ami_id: AWS AMI ID to create the instance from (e.g., 'ami-0123456789abcdef0')
            ami_name: Human-readable AMI name
            aws_instance_id: AWS EC2 instance ID (if already provisioned)
            status: Initial worker status
            cml_version: CML version to be installed
            created_at: Creation timestamp
            created_by: User ID who created the worker
            worker_id: Optional worker ID (generates UUID if not provided)
        """
        super().__init__()
        aggregate_id = worker_id or str(uuid4())
        created_time = created_at or datetime.now(timezone.utc)

        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerCreatedDomainEvent(
                    aggregate_id=aggregate_id,
                    name=name,
                    aws_region=aws_region,
                    aws_instance_id=aws_instance_id,
                    instance_type=instance_type,
                    ami_id=ami_id,
                    ami_name=ami_name,
                    status=status,
                    cml_version=cml_version,
                    created_at=created_time,
                    created_by=created_by,
                )
            )
        )

    @staticmethod
    def import_from_existing_instance(
        name: str,
        aws_region: str,
        aws_instance_id: str,
        instance_type: str,
        ami_id: str,
        instance_state: str,
        created_by: str | None = None,
        ami_name: str | None = None,
        public_ip: str | None = None,
        private_ip: str | None = None,
    ) -> "CMLWorker":
        """Factory method to import an existing EC2 instance as a CML Worker.

        This creates a worker from an already-provisioned EC2 instance without
        creating a new instance. Used for registering instances that were
        created outside of the CML Cloud Manager system.

        Args:
            name: Friendly name for the worker
            aws_region: AWS region where instance exists
            aws_instance_id: AWS EC2 instance ID
            instance_type: EC2 instance type (e.g., 'c5.2xlarge')
            ami_id: AMI ID used by the instance
            instance_state: Current EC2 state (running, stopped, etc.)
            created_by: User who initiated the import
            ami_name: Optional AMI name
            public_ip: Optional public IP address
            private_ip: Optional private IP address

        Returns:
            New CMLWorker aggregate with imported instance details
        """
        worker_id = str(uuid4())
        created_at = datetime.now(timezone.utc)

        # Create a new worker instance without going through __init__
        worker = object.__new__(CMLWorker)
        AggregateRoot.__init__(worker)

        # Register and apply the import event
        event = CMLWorkerImportedDomainEvent(
            aggregate_id=worker_id,
            name=name,
            aws_region=aws_region,
            aws_instance_id=aws_instance_id,
            instance_type=instance_type,
            ami_id=ami_id,
            ami_name=ami_name,
            instance_state=instance_state,
            public_ip=public_ip,
            private_ip=private_ip,
            created_by=created_by,
            created_at=created_at,
        )

        worker.state.on(worker.register_event(event))  # type: ignore
        return worker

    def id(self) -> str:
        """Return the aggregate identifier with a precise type."""
        aggregate_id = super().id()
        if aggregate_id is None:
            raise ValueError("CMLWorker aggregate identifier has not been initialized")
        return cast(str, aggregate_id)

    def update_status(self, new_status: CMLWorkerStatus) -> bool:
        """Update the EC2 instance status.

        Args:
            new_status: New worker status

        Returns:
            True if status was changed, False if already at that status
        """
        if self.state.status == new_status:
            return False

        old_status = self.state.status
        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerStatusUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    old_status=old_status,
                    new_status=new_status,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )
        return True

    def update_service_status(
        self,
        new_service_status: CMLServiceStatus,
        https_endpoint: str | None = None,
    ) -> bool:
        """Update the CML HTTPS service status.

        Args:
            new_service_status: New service availability status
            https_endpoint: HTTPS endpoint URL (if available)

        Returns:
            True if status was changed, False if already at that status
        """
        if (
            self.state.service_status == new_service_status
            and self.state.https_endpoint == https_endpoint
        ):
            return False

        old_service_status = self.state.service_status
        self.state.on(
            self.register_event(  # type: ignore
                CMLServiceStatusUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    old_service_status=old_service_status,
                    new_service_status=new_service_status,
                    https_endpoint=https_endpoint,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )
        return True

    def assign_instance(
        self,
        aws_instance_id: str,
        public_ip: str | None = None,
        private_ip: str | None = None,
    ) -> None:
        """Assign AWS EC2 instance details to the worker.

        Args:
            aws_instance_id: AWS EC2 instance ID
            public_ip: Public IP address
            private_ip: Private IP address
        """
        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerInstanceAssignedDomainEvent(
                    aggregate_id=self.id(),
                    aws_instance_id=aws_instance_id,
                    public_ip=public_ip,
                    private_ip=private_ip,
                    assigned_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_license(
        self,
        license_status: LicenseStatus,
        license_token: str | None = None,
    ) -> bool:
        """Update the CML license status.

        Args:
            license_status: New license status
            license_token: License token/registration key

        Returns:
            True if license was updated, False if unchanged
        """
        if (
            self.state.license_status == license_status
            and self.state.license_token == license_token
        ):
            return False

        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerLicenseUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    license_status=license_status,
                    license_token=license_token,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )
        return True

    def update_telemetry(
        self,
        last_activity_at: datetime,
        active_labs_count: int,
        cpu_utilization: float | None = None,
        memory_utilization: float | None = None,
    ) -> None:
        """Update worker telemetry data.

        Args:
            last_activity_at: Timestamp of last detected activity
            active_labs_count: Number of active labs running
            cpu_utilization: CPU utilization percentage (0-100)
            memory_utilization: Memory utilization percentage (0-100)
        """
        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerTelemetryUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    last_activity_at=last_activity_at,
                    active_labs_count=active_labs_count,
                    cpu_utilization=cpu_utilization,
                    memory_utilization=memory_utilization,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_endpoint(
        self,
        https_endpoint: str | None,
        public_ip: str | None = None,
    ) -> bool:
        """Update the worker's HTTPS endpoint.

        Args:
            https_endpoint: HTTPS endpoint URL
            public_ip: Updated public IP address

        Returns:
            True if endpoint was updated, False if unchanged
        """
        if self.state.https_endpoint == https_endpoint and (
            public_ip is None or self.state.public_ip == public_ip
        ):
            return False

        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerEndpointUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    https_endpoint=https_endpoint,
                    public_ip=public_ip,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )
        return True

    def terminate(self, terminated_by: str | None = None) -> None:
        """Mark the worker as terminated.

        Args:
            terminated_by: User ID who terminated the worker
        """
        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerTerminatedDomainEvent(
                    aggregate_id=self.id(),
                    name=self.state.name,
                    terminated_at=datetime.now(timezone.utc),
                    terminated_by=terminated_by,
                )
            )
        )

    def is_idle(self, idle_threshold_minutes: int) -> bool:
        """Check if the worker has been idle beyond the threshold.

        Args:
            idle_threshold_minutes: Idle threshold in minutes

        Returns:
            True if worker is idle beyond threshold, False otherwise
        """
        if not self.state.last_activity_at:
            return False

        if self.state.active_labs_count > 0:
            return False

        now = datetime.now(timezone.utc)
        idle_duration = now - self.state.last_activity_at
        return idle_duration.total_seconds() / 60 >= idle_threshold_minutes

    def can_connect(self) -> bool:
        """Check if the worker is ready for user connections.

        Returns:
            True if worker is running and service is available
        """
        return (
            self.state.status == CMLWorkerStatus.RUNNING
            and self.state.service_status == CMLServiceStatus.AVAILABLE
            and self.state.https_endpoint is not None
        )
