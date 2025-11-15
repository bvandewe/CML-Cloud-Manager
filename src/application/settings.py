"""Application settings configuration."""

import logging
import sys
from typing import Optional

from neuroglia.hosting.abstractions import ApplicationSettings


class Settings(ApplicationSettings):
    """Application settings with Keycloak OAuth2/OIDC configuration and observability."""

    # Debugging Configuration
    debug: bool = True
    environment: str = "development"  # development, production
    log_level: str = "INFO"

    # Application Configuration
    app_name: str = "Starter App"
    app_version: str = "1.0.0"
    app_url: str = "http://localhost:8020"  # External URL for callbacks
    app_host: str = (
        "127.0.0.1"  # Uvicorn bind address (override in production as needed)
    )
    app_port: int = 8080  # Uvicorn port

    # Observability Configuration
    service_name: str = "starter-app"
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
    otel_resource_attributes: dict = {}

    # Session Configuration
    session_secret_key: str = "change-me-in-production-use-secrets-token-urlsafe"
    session_timeout_hours: int = 8

    # Redis Configuration (for production session storage)
    redis_enabled: bool = False  # Set to True for production with Redis
    redis_url: str = "redis://redis:6379/0"  # Internal Docker network URL
    redis_key_prefix: str = "session:"

    # CORS Configuration
    enable_cors: bool = True
    cors_origins: list[str] = ["http://localhost:8020", "http://localhost:3000"]

    # Keycloak OAuth2/OIDC Configuration
    keycloak_url: str = "http://localhost:8021"  # External URL (browser accessible)
    keycloak_url_internal: str = "http://keycloak:8080"  # Internal Docker network URL
    keycloak_realm: str = "starter-app"

    # Backend confidential client for secure token exchange
    keycloak_client_id: str = "starter-app-backend"
    keycloak_client_secret: str = "starter-app-backend-secret-change-in-production"

    # Legacy public client (deprecated)
    keycloak_public_client_id: str = (
        "starter-app-public"  # Using existing client from realm config
    )

    # Legacy JWT (deprecated - will be removed)
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # Token Claim Validation (optional hardened checks)
    verify_issuer: bool = False  # Set True to enforce 'iss' claim
    expected_issuer: str = ""  # e.g. "http://localhost:8021/realms/starter-app"
    verify_audience: bool = False  # Set True to enforce 'aud' claim
    expected_audience: list[str] = []  # e.g. ["starter-app-backend"]
    refresh_auto_leeway_seconds: int = 60  # Auto-refresh if exp is within this window

    # Persistence Configuration
    consumer_group: Optional[str] = "starter-app-consumer-group"
    connection_strings: dict[str, str] = {
        "mongo": "mongodb://root:pass@mongodb:27017/?authSource=admin"  # pragma: allowlist secret
    }

    # Cloud Events Configuration
    cloud_event_sink: Optional[str] = None
    cloud_event_source: Optional[str] = None
    cloud_event_type_prefix: str = "io.system.starter-app"
    cloud_event_retry_attempts: int = 5
    cloud_event_retry_delay: float = 1.0

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


app_settings = Settings()


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure application-wide logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
