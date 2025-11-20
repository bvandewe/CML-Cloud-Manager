"""Main application entry point with SubApp mounting."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neuroglia.data.infrastructure.mongo import MotorRepository
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_ingestor import (
    CloudEventIngestor,
)
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_middleware import (
    CloudEventMiddleware,
)
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublisher,
)
from neuroglia.hosting.web import SubAppConfig, WebApplicationBuilder
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.observability import Observability
from neuroglia.serialization.json import JsonSerializer

from api.services import DualAuthService
from api.services.openapi_config import (
    configure_api_openapi,
    configure_mounted_apps_openapi_prefix,
)
from application.services.background_scheduler import BackgroundTaskScheduler
from application.services.sse_event_relay import SSEEventRelayHostedService
from application.services.system_health_service import SystemHealthService
from application.settings import app_settings, configure_logging
from domain.entities import Task
from domain.entities.cml_worker import CMLWorker
from domain.entities.lab_record import LabRecord
from domain.repositories import TaskRepository
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from domain.repositories.lab_record_repository import LabRecordRepository
from infrastructure.services.worker_refresh_throttle import WorkerRefreshThrottle
from integration.repositories.motor_cml_worker_repository import (
    MongoCMLWorkerRepository,
)
from integration.repositories.motor_lab_record_repository import (
    MongoLabRecordRepository,
)
from integration.repositories.motor_task_repository import MongoTaskRepository
from integration.services.aws_ec2_api_client import AwsEc2Client
from integration.services.cml_api_client import CMLApiClientFactory

"""Pre-config logging file truncation for LOCAL_DEV before handlers attach."""
try:
    if os.getenv("LOCAL_DEV", "").lower() in ("1", "true", "yes", True):
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        debug_log_path = logs_dir / "debug.log"  # actual log file used by configure_logging
        # Truncate (create empty) before FileHandler opens in append mode
        debug_log_path.write_text("")
except Exception:
    # Safe to ignore; will still proceed with logging configuration
    print("Truncating log file failed")

configure_logging(log_level=app_settings.log_level)
log = logging.getLogger(__name__)


def _mask_env_value(key: str, value: str) -> str:
    """Mask sensitive environment variable values.

    Any key containing common secret indicators will be masked to avoid leaking credentials.
    """
    sensitive_markers = ["SECRET", "PASSWORD", "TOKEN", "KEY", "ACCESS_KEY"]
    upper_key = key.upper()
    if any(marker in upper_key for marker in sensitive_markers):
        # Preserve length for debugging without exposing content
        return f"***MASKED(len={len(value)})***" if value else "***MASKED***"
    return value


def debug_log_environment(prefix_only: tuple[str, ...] = ("AUTO_IMPORT_",)) -> None:
    """Dump environment variables at DEBUG level for diagnostic purposes.

    Sensitive values are masked. Optionally highlight certain prefixes (e.g. AUTO_IMPORT_).
    """
    if not log.isEnabledFor(logging.DEBUG):
        return
    try:
        log.debug("🔍 Dumping environment variables for startup diagnostics (masked)")
        highlighted = {}
        for k, v in sorted(os.environ.items()):
            masked = _mask_env_value(k, v)
            # Log all variables
            log.debug("ENV %s=%s", k, masked)
            if prefix_only and any(k.startswith(p) for p in prefix_only):
                highlighted[k] = v
        if highlighted:
            log.debug("✅ Highlighted AUTO_IMPORT settings: %s", highlighted)
        # Also log resolved settings object values of interest
        log.debug(
            "🧪 Resolved auto-import settings: enabled=%s interval=%s region=%s ami_name=%s",
            app_settings.auto_import_workers_enabled,
            app_settings.auto_import_workers_interval,
            app_settings.auto_import_workers_region,
            app_settings.auto_import_workers_ami_name,
        )
    except Exception as ex:
        log.warning("Failed to dump environment variables: %s", ex)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Creates separate apps for:
    - API backend (/api prefix) - REST API for task management
    - UI frontend (/ prefix) - Web interface

    Returns:
        Configured FastAPI application with multiple mounted apps
    """
    log.debug("🚀 Creating Cml Cloud Manager application...")

    # Early environment diagnostics before service configuration & scheduler startup
    debug_log_environment()

    builder = WebApplicationBuilder(app_settings=app_settings)

    # Configure core services
    Mediator.configure(
        builder,
        [
            "application.commands",
            "application.queries",
            "application.events.domain",
            "application.events.integration",
        ],
    )
    Mapper.configure(
        builder,
        [
            "application.commands",
            "application.queries",
            "application.mapping",
            "integration.models",
        ],
    )
    JsonSerializer.configure(
        builder,
        [
            "domain.entities",
            "domain.models",
            "integration.models",
        ],
    )
    CloudEventPublisher.configure(builder)
    CloudEventIngestor.configure(builder, ["application.events.integration"])
    Observability.configure(builder)

    # Configure MongoDB repository
    MotorRepository.configure(
        builder,
        entity_type=Task,
        key_type=str,
        database_name="cml_cloud_manager",
        collection_name="tasks",
        domain_repository_type=TaskRepository,
        implementation_type=MongoTaskRepository,
    )

    # Configure CML Worker MongoDB repository
    MotorRepository.configure(
        builder,
        entity_type=CMLWorker,
        key_type=str,
        database_name="cml_cloud_manager",
        collection_name="cml_workers",
        domain_repository_type=CMLWorkerRepository,
        implementation_type=MongoCMLWorkerRepository,
    )

    # Configure Lab Record Repository
    MotorRepository.configure(
        builder,
        entity_type=LabRecord,
        key_type=str,
        database_name="cml_cloud_manager",
        collection_name="lab_records",
        domain_repository_type=LabRecordRepository,
        implementation_type=MongoLabRecordRepository,
    )

    # Configure AWS EC2 Client
    AwsEc2Client.configure(builder)

    # Configure CML API Client Factory
    CMLApiClientFactory.configure(builder)

    # Configure BackgroundTaskScheduler for worker monitoring jobs
    BackgroundTaskScheduler.configure(
        builder,
        modules=["application.jobs"],  # Scan for @backgroundjob decorated classes
    )

    # Configure SystemHealthService (aggregated health checks)
    SystemHealthService.configure(builder)

    # Configure WorkerRefreshThrottle as singleton for rate-limiting
    WorkerRefreshThrottle.configure(builder)

    # Configure SSE Event Relay hosted service
    SSEEventRelayHostedService.configure(builder)

    # Schedule recurring background jobs if monitoring enabled
    if app_settings.worker_monitoring_enabled:
        # Jobs will be scheduled after application startup via lifespan context
        log.info("✅ Worker monitoring enabled - jobs will be scheduled on startup")

    # Configure authentication services (session store + auth service)
    DualAuthService.configure(builder)

    # Add SubApp for API with controllers
    builder.add_sub_app(
        SubAppConfig(
            path="/api",
            name="api",
            title=f"{app_settings.app_name} API",
            description="Task management REST API with OAuth2/JWT authentication",
            version=app_settings.app_version,
            controllers=["api.controllers"],
            custom_setup=lambda app, service_provider: configure_api_openapi(app, app_settings),
            docs_url="/docs",
        )
    )

    # UI sub-app: Web interface serving static files built by Parcel
    # Get absolute path to static directory
    static_dir = Path(__file__).parent.parent / "static"

    # Add SubApp for UI at root path
    builder.add_sub_app(
        SubAppConfig(
            path="/",
            name="ui",
            title=app_settings.app_name,
            controllers=["ui.controllers"],
            static_files={"/static": str(static_dir)},
            docs_url=None,  # Disable docs for UI
        )
    )

    # Build the application
    app = builder.build_app_with_lifespan(
        title="Cml Cloud Manager",
        description="Task management application with multi-app architecture",
        version="1.0.0",
        debug=True,
    )

    # Configure OpenAPI path prefixes for all mounted sub-apps
    configure_mounted_apps_openapi_prefix(app)

    # Configure middlewares
    DualAuthService.configure_middleware(app)
    app.add_middleware(CloudEventMiddleware, service_provider=app.state.services)

    if app_settings.enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    log.info("✅ Application created successfully!")
    log.info("📊 Access points:")
    log.info(f"   - UI: http://localhost:{app_settings.app_port}/")
    log.info(f"   - API Docs: http://localhost:{app_settings.app_port}/api/docs")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:create_app",
        factory=True,
        host=app_settings.app_host,
        port=app_settings.app_port,
        reload=app_settings.debug,
    )
