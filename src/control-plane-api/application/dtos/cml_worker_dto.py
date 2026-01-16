"""CML Worker Data Transfer Object."""

from dataclasses import dataclass


@dataclass
class CMLWorkerDto:
    """DTO for CML Worker data transfer (API responses, SSE events, etc.)."""

    # Identity
    id: str
    name: str
    aws_region: str
    aws_instance_id: str | None
    instance_type: str

    # Status
    status: str
    service_status: str

    # AMI information
    ami_id: str | None
    ami_name: str | None
    ami_description: str | None
    ami_creation_date: str | None

    # Network
    https_endpoint: str | None
    public_ip: str | None
    private_ip: str | None

    # AWS Tags
    aws_tags: dict[str, str] | None

    # License
    license_status: str | None
    license_token: str | None
    cml_license_info: dict | None

    # CML Metrics
    cml_version: str | None
    cml_ready: bool | None
    cml_uptime_seconds: int | None
    cml_labs_count: int | None
    cml_system_info: dict | None
    cml_system_health: dict | None
    cml_last_synced_at: str | None

    # EC2 Metrics
    ec2_instance_state_detail: str | None
    ec2_system_status_check: str | None
    ec2_last_checked_at: str | None

    # CloudWatch Metrics
    cloudwatch_cpu_utilization: float | None
    cloudwatch_memory_utilization: float | None
    cloudwatch_last_collected_at: str | None
    cloudwatch_detailed_monitoring_enabled: bool | None

    # Calculated utilization (from CML or CloudWatch)
    cpu_utilization: float | None
    memory_utilization: float | None
    storage_utilization: float | None
    disk_utilization: float | None  # Alias for storage_utilization

    # Backward compatibility
    active_labs_count: int | None

    # Timing
    poll_interval: int | None
    next_refresh_at: str | None
    created_at: str
    updated_at: str
    start_initiated_at: str | None
    stop_initiated_at: str | None
    terminated_at: str | None
    created_by: str | None

    # Activity tracking and idle detection
    last_activity_at: str | None
    last_activity_check_at: str | None
    next_idle_check_at: str | None
    target_pause_at: str | None
    is_idle_detection_enabled: bool

    # Pause/resume tracking
    auto_pause_count: int
    manual_pause_count: int
    auto_resume_count: int
    manual_resume_count: int
    last_paused_at: str | None
    last_resumed_at: str | None
    paused_by: str | None
    pause_reason: str | None
