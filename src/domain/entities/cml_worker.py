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
from domain.events.cloudwatch_monitoring_updated_domain_event import (
    CloudWatchMonitoringUpdatedDomainEvent,
)
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
from domain.events.worker_metrics_events import (
    CloudWatchMetricsUpdatedDomainEvent,
    CMLMetricsUpdatedDomainEvent,
    EC2InstanceDetailsUpdatedDomainEvent,
    EC2MetricsUpdatedDomainEvent,
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
    ami_description: str | None
    ami_creation_date: str | None
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

    # EC2 Metrics (from AWS EC2 API)
    ec2_instance_state_detail: str | None  # e.g., "ok", "impaired", "insufficient-data"
    ec2_system_status_check: str | None  # e.g., "ok", "impaired"
    ec2_last_checked_at: datetime | None

    # CloudWatch Metrics (from AWS CloudWatch API)
    cloudwatch_cpu_utilization: float | None
    cloudwatch_memory_utilization: float | None
    cloudwatch_last_collected_at: datetime | None
    cloudwatch_detailed_monitoring_enabled: bool

    # CML Metrics (from CML API /api/v0/system_information)
    cml_system_info: dict | None  # Full system info from CML
    cml_system_health: dict | None  # System health checks from CML
    cml_license_info: dict | None  # License information from CML
    cml_ready: bool  # CML application ready state
    cml_uptime_seconds: int | None  # CML uptime
    cml_labs_count: int  # Number of labs from CML API
    cml_last_synced_at: datetime | None  # Last successful CML API sync

    # Metrics Timing (for UI countdown timer)
    poll_interval: int | None  # Metrics collection interval in seconds
    next_refresh_at: datetime | None  # Next scheduled metrics collection time

    # Lifecycle timestamps
    created_at: datetime
    updated_at: datetime
    terminated_at: datetime | None
    start_initiated_at: datetime | None
    stop_initiated_at: datetime | None

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
        self.ami_description = None
        self.ami_creation_date = None
        self.status = CMLWorkerStatus.PENDING
        self.service_status = CMLServiceStatus.UNAVAILABLE

        self.cml_version = None
        self.license_status = LicenseStatus.UNREGISTERED
        self.license_token = None
        self.https_endpoint = None

        self.public_ip = None
        self.private_ip = None

        # EC2 Metrics
        self.ec2_instance_state_detail = None
        self.ec2_system_status_check = None
        self.ec2_last_checked_at = None

        # CloudWatch Metrics
        self.cloudwatch_cpu_utilization = None
        self.cloudwatch_memory_utilization = None
        self.cloudwatch_last_collected_at = None
        self.cloudwatch_detailed_monitoring_enabled = False

        # CML Metrics
        self.cml_system_info = None
        self.cml_system_health = None
        self.cml_license_info = None
        self.cml_ready = False
        self.cml_uptime_seconds = None
        self.cml_labs_count = 0
        self.cml_last_synced_at = None

        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now
        self.terminated_at = None
        self.start_initiated_at = None
        self.stop_initiated_at = None

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
        self.ami_description = event.ami_description
        self.ami_creation_date = event.ami_creation_date
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
        self.ami_description = event.ami_description
        self.ami_creation_date = event.ami_creation_date
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
        # Track transition initiation timestamps for long-running operations
        if event.new_status == CMLWorkerStatus.PENDING:
            # Starting
            self.start_initiated_at = event.transition_initiated_at or event.updated_at
        elif event.new_status == CMLWorkerStatus.RUNNING:
            # Clear start transition marker once running
            self.start_initiated_at = None
        elif event.new_status == CMLWorkerStatus.STOPPING:
            self.stop_initiated_at = event.transition_initiated_at or event.updated_at
        elif event.new_status == CMLWorkerStatus.STOPPED:
            self.stop_initiated_at = None

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

    @dispatch(EC2MetricsUpdatedDomainEvent)
    def on(self, event: EC2MetricsUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply EC2 metrics event to the state."""
        self.ec2_instance_state_detail = event.instance_state_detail
        self.ec2_system_status_check = event.system_status_check
        self.ec2_last_checked_at = event.checked_at
        self.updated_at = event.updated_at

    @dispatch(EC2InstanceDetailsUpdatedDomainEvent)
    def on(self, event: EC2InstanceDetailsUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply EC2 instance details event to the state."""
        self.public_ip = event.public_ip
        self.private_ip = event.private_ip
        self.instance_type = event.instance_type
        self.ami_id = event.ami_id
        self.ami_name = event.ami_name
        self.ami_description = event.ami_description
        self.ami_creation_date = event.ami_creation_date
        self.updated_at = event.updated_at

    @dispatch(CloudWatchMetricsUpdatedDomainEvent)
    def on(self, event: CloudWatchMetricsUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply CloudWatch metrics event to the state."""
        self.cloudwatch_cpu_utilization = event.cpu_utilization
        self.cloudwatch_memory_utilization = event.memory_utilization
        self.cloudwatch_last_collected_at = event.collected_at
        self.updated_at = event.updated_at

    @dispatch(CMLMetricsUpdatedDomainEvent)
    def on(self, event: CMLMetricsUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply CML API metrics event to the state."""
        self.cml_version = event.cml_version
        self.cml_system_info = event.system_info
        self.cml_system_health = event.system_health
        self.cml_license_info = event.license_info
        self.cml_ready = event.ready
        self.cml_uptime_seconds = event.uptime_seconds
        self.cml_labs_count = event.labs_count
        self.cml_last_synced_at = event.synced_at
        self.updated_at = event.updated_at

    @dispatch(CMLWorkerTelemetryUpdatedDomainEvent)
    def on(self, event: CMLWorkerTelemetryUpdatedDomainEvent) -> None:
        """Handle telemetry updated event."""
        self.updated_at = event.updated_at
        if event.poll_interval is not None:
            self.poll_interval = event.poll_interval
        if event.next_refresh_at is not None:
            self.next_refresh_at = event.next_refresh_at

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

    @dispatch(CloudWatchMonitoringUpdatedDomainEvent)
    def on(self, event: CloudWatchMonitoringUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply the CloudWatch monitoring updated event to the state."""
        self.cloudwatch_detailed_monitoring_enabled = event.enabled
        self.updated_at = event.updated_at


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
        ami_description: str | None = None,
        ami_creation_date: str | None = None,
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
                    ami_description=ami_description,
                    ami_creation_date=ami_creation_date,
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
        ami_description: str | None = None,
        ami_creation_date: str | None = None,
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
            ami_description=ami_description,
            ami_creation_date=ami_creation_date,
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
        now = datetime.now(timezone.utc)
        transition_ts: datetime | None = None
        if new_status in (CMLWorkerStatus.PENDING, CMLWorkerStatus.STOPPING):
            transition_ts = now
        self.state.on(
            self.register_event(  # type: ignore
                CMLWorkerStatusUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    old_status=old_status,
                    new_status=new_status,
                    updated_at=now,
                    transition_initiated_at=transition_ts,
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

    def update_ec2_metrics(
        self,
        instance_state_detail: str,
        system_status_check: str,
        checked_at: datetime | None = None,
    ) -> None:
        """Update EC2 instance health metrics from AWS EC2 API.

        Args:
            instance_state_detail: Instance status check (e.g., "ok", "impaired")
            system_status_check: System status check (e.g., "ok", "impaired")
            checked_at: Timestamp of the status check
        """
        self.state.on(
            self.register_event(  # type: ignore
                EC2MetricsUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    instance_state_detail=instance_state_detail,
                    system_status_check=system_status_check,
                    checked_at=checked_at or datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_ec2_instance_details(
        self,
        public_ip: str | None = None,
        private_ip: str | None = None,
        instance_type: str | None = None,
        ami_id: str | None = None,
        ami_name: str | None = None,
        ami_description: str | None = None,
        ami_creation_date: str | None = None,
    ) -> None:
        """Update EC2 instance details from AWS EC2 API.

        Args:
            public_ip: Public IP address of the instance
            private_ip: Private IP address of the instance
            instance_type: EC2 instance type (e.g., "t3.medium")
            ami_id: AMI ID used to launch the instance
            ami_name: AMI name/description
        """
        self.state.on(
            self.register_event(  # type: ignore
                EC2InstanceDetailsUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    public_ip=public_ip,
                    private_ip=private_ip,
                    instance_type=instance_type,
                    ami_id=ami_id,
                    ami_name=ami_name,
                    ami_description=ami_description,
                    ami_creation_date=ami_creation_date,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_cloudwatch_metrics(
        self,
        cpu_utilization: float,
        memory_utilization: float,
        collected_at: datetime | None = None,
    ) -> None:
        """Update CloudWatch metrics from AWS CloudWatch API.

        Args:
            cpu_utilization: CPU utilization percentage (0-100)
            memory_utilization: Memory utilization percentage (0-100)
            collected_at: Timestamp when metrics were collected
        """
        self.state.on(
            self.register_event(  # type: ignore
                CloudWatchMetricsUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    cpu_utilization=cpu_utilization,
                    memory_utilization=memory_utilization,
                    collected_at=collected_at or datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_cml_metrics(
        self,
        cml_version: str | None,
        system_info: dict,
        system_health: dict | None,
        license_info: dict | None,
        ready: bool,
        uptime_seconds: int | None,
        labs_count: int,
        synced_at: datetime | None = None,
        change_threshold_percent: float | None = None,
    ) -> None:
        """Update CML application metrics from CML API.

        Args:
            cml_version: CML version string (e.g., "2.9.0")
            system_info: Full system information dictionary from CML
            system_health: System health checks from CML
            license_info: License information from CML (registration, authorization, features)
            ready: CML application ready state
            uptime_seconds: CML uptime in seconds
            labs_count: Number of labs from CML API
            synced_at: Timestamp when data was synced from CML API
        """
        # Domain-level suppression: only emit event if meaningful delta
        # Always emit when no prior system_info or threshold not provided
        emit_event = True
        if change_threshold_percent is not None and self.state.cml_system_info:
            try:
                prev_info = self.state.cml_system_info
                prev_first = next(iter(prev_info.values()), {}) if prev_info else {}
                new_first = next(iter(system_info.values()), {}) if system_info else {}
                prev_stats = prev_first.get("stats", {})
                new_stats = new_first.get("stats", {})

                def derive(
                    stats: dict,
                ) -> tuple[float | None, float | None, float | None]:
                    cpu_util = None
                    mem_util = None
                    storage_util = None
                    cpu_stats = stats.get("cpu", {})
                    mem_stats = stats.get("memory", {})
                    disk_stats = stats.get("disk", {})
                    if cpu_stats:
                        up = cpu_stats.get("user_percent")
                        sp = cpu_stats.get("system_percent")
                        if up is not None and sp is not None:
                            try:
                                cpu_util = float(up) + float(sp)
                            except (TypeError, ValueError):
                                cpu_util = None
                    if mem_stats:
                        total_kb = mem_stats.get("total_kb") or mem_stats.get("total")
                        available_kb = mem_stats.get("available_kb") or mem_stats.get(
                            "free"
                        )
                        if (
                            isinstance(total_kb, (int, float))
                            and isinstance(available_kb, (int, float))
                            and total_kb > 0
                        ):
                            used_kb = total_kb - available_kb
                            mem_util = (used_kb / total_kb) * 100
                    if disk_stats:
                        size_kb = disk_stats.get("size_kb") or disk_stats.get("used")
                        capacity_kb = disk_stats.get("capacity_kb") or disk_stats.get(
                            "total"
                        )
                        if (
                            isinstance(size_kb, (int, float))
                            and isinstance(capacity_kb, (int, float))
                            and capacity_kb > 0
                        ):
                            storage_util = (size_kb / capacity_kb) * 100
                    return cpu_util, mem_util, storage_util

                prev_cpu, prev_mem, prev_storage = derive(prev_stats)
                new_cpu, new_mem, new_storage = derive(new_stats)

                def pct_changed(old: float | None, new: float | None) -> float:
                    if old is None or new is None:
                        return 100.0 if old != new else 0.0
                    if old == 0:
                        return 100.0 if new != 0 else 0.0
                    return abs(new - old) / abs(old) * 100.0

                cpu_delta = pct_changed(prev_cpu, new_cpu)
                mem_delta = pct_changed(prev_mem, new_mem)
                storage_delta = pct_changed(prev_storage, new_storage)
                labs_changed = labs_count != self.state.cml_labs_count
                version_changed = cml_version != self.state.cml_version

                emit_event = (
                    labs_changed
                    or version_changed
                    or cpu_delta >= change_threshold_percent
                    or mem_delta >= change_threshold_percent
                    or storage_delta >= change_threshold_percent
                )
            except Exception:
                # Fail open: emit event if derivation fails
                emit_event = True

        if not emit_event:
            return

        self.state.on(
            self.register_event(  # type: ignore
                CMLMetricsUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    cml_version=cml_version,
                    system_info=system_info,
                    system_health=system_health,
                    license_info=license_info,
                    ready=ready,
                    uptime_seconds=uptime_seconds,
                    labs_count=labs_count,
                    synced_at=synced_at or datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        )

    def update_telemetry(
        self,
        last_activity_at: datetime,
        active_labs_count: int,
        cpu_utilization: float | None = None,
        memory_utilization: float | None = None,
        poll_interval: int | None = None,
        next_refresh_at: datetime | None = None,
    ) -> None:
        """Update worker telemetry data (DEPRECATED - use source-specific methods).

        This method is kept for backward compatibility. New code should use:
        - update_ec2_metrics() for EC2 instance status
        - update_cloudwatch_metrics() for CPU/memory metrics
        - update_cml_metrics() for CML application data

        Args:
            last_activity_at: Timestamp of last detected activity
            active_labs_count: Number of active labs running
            cpu_utilization: CPU utilization percentage (0-100)
            memory_utilization: Memory utilization percentage (0-100)
            poll_interval: Metrics collection interval in seconds (for countdown timer)
            next_refresh_at: Next scheduled metrics collection time (for countdown timer)
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
                    poll_interval=poll_interval,
                    next_refresh_at=next_refresh_at,
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

    def update_cloudwatch_monitoring(self, enabled: bool) -> bool:
        """Update the worker's CloudWatch detailed monitoring status.

        Args:
            enabled: Whether detailed monitoring is enabled

        Returns:
            True if monitoring status was updated, False if unchanged
        """
        if self.state.cloudwatch_detailed_monitoring_enabled == enabled:
            return False

        self.state.on(
            self.register_event(  # type: ignore
                CloudWatchMonitoringUpdatedDomainEvent(
                    aggregate_id=self.id(),
                    enabled=enabled,
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
        # Check last activity from either CloudWatch or CML metrics
        last_activity = (
            self.state.cloudwatch_last_collected_at or self.state.cml_last_synced_at
        )
        if not last_activity:
            return False

        if self.state.cml_labs_count > 0:
            return False

        now = datetime.now(timezone.utc)
        idle_duration = now - last_activity
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
