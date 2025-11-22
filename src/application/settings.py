"""Application settings configuration."""

import logging
import sys
from typing import Any

from neuroglia.hosting.abstractions import ApplicationSettings

from integration.enums import Ec2InstanceType


class Settings(ApplicationSettings):
    """Application settings with Keycloak OAuth2/OIDC configuration and observability."""

    # Debugging Configuration
    debug: bool = False
    environment: str = "development"  # development, production
    log_level: str = "INFO"

    # Application Configuration
    app_name: str = "Cml Cloud Manager"
    app_version: str = "1.0.0"
    app_url: str = "http://localhost:8020"  # External URL for callbacks
    app_host: str = "127.0.0.1"  # Uvicorn bind address (override in production as needed)
    app_port: int = 8080  # Uvicorn port

    # Observability Configuration
    service_name: str = "cml-cloud-manager"
    service_version: str = app_version
    deployment_environment: str = "development"

    observability_enabled: bool = True
    observability_metrics_enabled: bool = True
    observability_tracing_enabled: bool = True
    observability_logging_enabled: bool = True
    observability_health_endpoint: bool = True
    observability_metrics_endpoint: bool = True
    observability_ready_endpoint: bool = True
    observability_health_path: str = "/health"
    observability_metrics_path: str = "/metrics"
    observability_ready_path: str = "/ready"
    observability_health_checks: list[str] = []

    otel_enabled: bool = True
    otel_endpoint: str = "http://otel-collector:4317"
    otel_protocol: str = "grpc"
    otel_timeout: int = 10
    otel_console_export: bool = False
    otel_batch_max_queue_size: int = 2048
    otel_batch_schedule_delay_ms: int = 5000
    otel_batch_max_export_size: int = 512
    otel_metrics_interval_ms: int = 60000
    otel_metrics_timeout_ms: int = 30000
    otel_instrument_fastapi: bool = True
    otel_instrument_httpx: bool = True
    otel_instrument_logging: bool = True
    otel_instrument_system_metrics: bool = True
    otel_resource_attributes: dict[str, str] = {}

    # Session Configuration
    session_secret_key: str = "change-me-in-production-use-secrets-token-urlsafe"
    session_max_duration_minutes: int = 120  # 120 minutes default
    session_expiration_warning_minutes: int = 10  # Warning banner appears 10 minutes before expiration

    # Redis Configuration (for production session storage)
    redis_enabled: bool = False  # Set to True for production with Redis
    redis_url: str = "redis://redis:6379/0"  # Internal Docker network URL
    redis_key_prefix: str = "session:"

    # CORS Configuration
    enable_cors: bool = True
    cors_origins: list[str] = ["http://localhost:8020", "http://localhost:3000"]

    # Keycloak OAuth2/OIDC Configuration
    keycloak_url: str = "http://localhost:8031"  # External URL (browser/Swagger accessible)
    keycloak_url_internal: str | None = None  # Internal Docker network URL (auto-populated if not set)
    keycloak_realm: str = "cml-cloud-manager"

    # Backend confidential client for secure token exchange
    keycloak_client_id: str = "cml-cloud-manager-backend"
    keycloak_client_secret: str = "cml-cloud-manager-backend-secret-change-in-production"

    # Legacy public client (deprecated)
    keycloak_public_client_id: str = "cml-cloud-manager-public"  # Using existing client from realm config

    # Legacy JWT (deprecated - will be removed)
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # Token Claim Validation (optional hardened checks)
    verify_issuer: bool = False  # Set True to enforce 'iss' claim
    expected_issuer: str = ""  # e.g. "http://localhost:8031/realms/cml-cloud-manager"
    verify_audience: bool = False  # Set True to enforce 'aud' claim
    expected_audience: list[str] = ["cml-cloud-manager"]  # Audience claim expected in tokens
    refresh_auto_leeway_seconds: int = 60  # Auto-refresh if exp is within this window

    # Persistence Configuration
    consumer_group: str | None = "cml-cloud-manager-consumer-group"
    connection_strings: dict[str, str] = {
        "mongo": "mongodb://root:pass@mongodb:27017/?authSource=admin"  # pragma: allowlist secret
    }

    # Cloud Events Configuration
    cloud_event_sink: str | None = None
    cloud_event_source: str | None = None
    cloud_event_type_prefix: str = "io.system.cml-cloud-manager"
    cloud_event_retry_attempts: int = 5
    cloud_event_retry_delay: float = 1.0

    # AWS Account Credentials
    aws_access_key_id: str = "YOUR_ACCESS_KEY_ID"
    aws_secret_access_key: str = "YOUR_SECRET_ACCESS_KEY"

    # AWS EC2 CML Worker Settings
    cml_worker_ami_name_default: str = "my-cml2.7.0-lablet-v0.1.0"
    cml_worker_ami_ids: dict[str, str] = {
        "us-east-1": "ami-0123456789abcdef0",
        "us-west-2": "ami-0123456789abcdef0",
    }
    cml_worker_ami_names: dict[str, str] = {
        "us-east-1": "CML-2.7.0-Ubuntu-22.04",
        "us-west-2": "CML-2.7.0-Ubuntu-22.04",
    }
    cml_worker_instance_type: Ec2InstanceType = Ec2InstanceType.SMALL
    cml_worker_security_group_ids: list[str] = ["sg-0123456789abcdef0"]
    cml_worker_security_group_names: list[str] = ["ec2_cml_worker_sg"]
    cml_worker_vpc_id: str = "vpc-0123456789abcdef0"
    cml_worker_subnet_id: str = "subnet-0123456789abcdef0"
    cml_worker_key_name: str = "cml_worker_key_pair"
    cml_worker_username: str = "sys-admin"
    cml_worker_api_username: str = "admin"  # CML API username for system_stats
    cml_worker_api_password: str = "admin"  # CML API password (change in production)
    cml_worker_api_verify_ssl: bool = (
        False  # Verify SSL certificates for CML API calls (False for dev/self-signed certs)
    )
    cml_worker_default_tags: dict[str, str] = {
        "Environment": "dev",
        "ApplicationName": "CML-Cloud-Manager",
        "ManagedBy": "CML-Cloud-Manager",
        "Name": "cml-worker-{worker_id}",
    }

    # Worker Monitoring Configuration
    worker_monitoring_enabled: bool = True
    worker_metrics_poll_interval: int = 300  # 5 minutes (must match WorkerMetricsCollectionJob)

    # Worker Activity Detection & Idle Timeout Configuration
    worker_activity_detection_enabled: bool = True  # Feature flag
    worker_activity_detection_interval: int = 1800  # 30 minutes between checks
    worker_idle_timeout_minutes: int = 60  # Idle time before auto-pause
    worker_auto_pause_enabled: bool = True  # Enable automatic pause on idle
    worker_auto_pause_snooze_minutes: int = 60  # Prevent re-pause after resume
    worker_activity_events_max_stored: int = 10  # Max recent events to store

    # Event filtering for activity detection
    worker_activity_relevant_categories: list[str] = [
        "start_lab",
        "stop_lab",
        "wipe_lab",
        "import_lab",
        "export_lab",
        "start_node",
        "stop_node",
        "queue_node",
        "boot_node",
        "user_activity",  # Filtered further by user_id pattern
    ]
    worker_activity_excluded_user_pattern: str = "^00000000-0000-.*"  # Admin UUID pattern (automated API calls)
    worker_notification_webhooks: list[str] = []  # List of webhook URLs for notifications
    # Metrics Change Threshold (percentage delta required to broadcast utilization updates)
    metrics_change_threshold_percent: float = 5.0  # Override via METRICS_CHANGE_THRESHOLD_PERCENT
    # Labs Refresh Background Job Configuration
    labs_refresh_interval: int = 1800  # Seconds between labs refresh runs (default: 30 minutes)

    # Worker Refresh Rate Limiting
    worker_refresh_min_interval: int = 10  # Seconds - minimum time between manual refresh requests
    worker_refresh_check_upcoming_job_threshold: int = (
        10  # Seconds - skip manual refresh if background job is within this threshold
    )
    # Auto-Import Workers Configuration
    auto_import_workers_enabled: bool = False  # Enable/disable auto-import job
    auto_import_workers_interval: int = 3600  # Seconds between auto-import runs (default: 1 hour)
    auto_import_workers_region: str = "us-east-1"  # AWS region to scan for workers
    auto_import_workers_ami_name: str = ""  # AMI name pattern to search for (e.g., "CML-2.7.0-*")

    # Background Job Store Configuration (APScheduler persistence)
    background_job_store: dict[str, Any] = {
        # Redis configuration (recommended for production)
        "redis_host": "redis",
        "redis_port": 6379,
        "redis_db": 1,  # Use separate DB from session storage (DB 0)
        # Alternatively, use MongoDB (if Redis not available)
        # "mongo_uri": "mongodb://root:password123@mongodb:27017/?authSource=admin",  # pragma: allowlist secret
        # "mongo_db": "cml_cloud_manager",
        # "mongo_collection": "background_jobs",
    }

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables

    def __init__(self, **kwargs: Any) -> None:
        """Initialize settings."""
        super().__init__(**kwargs)
        # If keycloak_url_internal is not provided, use keycloak_url as fallback
        # This handles both Docker (with override) and Kubernetes (single URL) scenarios
        if not self.keycloak_url_internal:
            self.keycloak_url_internal = self.keycloak_url


# Instantiate application settings
app_settings = Settings()


def configure_logging(log_level: str = "INFO") -> None:
    """Configure application-wide logging with support for console and file output.

    This function configures the root logger and sets appropriate levels for
    third-party libraries to reduce noise. It's designed to be portable and
    work across different deployment environments (local, Docker, Kubernetes).

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    import os

    # Ensure log_level is uppercase for consistency
    log_level = log_level.upper()

    # Get root logger and clear any existing handlers to prevent duplicates
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Set the root logger level
    root_logger.setLevel(log_level)

    # Define log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)

    # Console handler (always enabled for cloud-native environments)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional, for local development)
    # Only enable if LOG_FILE environment variable is set or logs/ directory exists
    log_file = os.getenv("LOG_FILE", "logs/debug.log")
    if os.path.exists("logs") or os.getenv("LOG_FILE"):
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except (OSError, PermissionError):
            # Silently fail if we can't create log file (e.g., read-only filesystem in containers)
            pass

    # Set third-party loggers to WARNING to reduce noise
    third_party_loggers = [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "httpx",
        "httpcore",
        "httpcore.http11",
        "httpcore.connection",
        "pymongo",
        "pymongo.topology",
        "pymongo.connection",
        "pymongo.serverSelection",
        "asyncio",
    ]

    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
