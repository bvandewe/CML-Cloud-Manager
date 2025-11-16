"""Main application entry point with SubApp mounting."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
from application.services import (
    BackgroundTasksBus,
    BackgroundTaskScheduler,
    WorkerMonitoringScheduler,
    WorkerNotificationHandler,
)
from application.settings import app_settings, configure_logging
from domain.entities import Task
from domain.entities.cml_worker import CMLWorker
from domain.repositories import TaskRepository
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.repositories.motor_cml_worker_repository import (
    MongoCMLWorkerRepository,
)
from integration.repositories.motor_task_repository import MongoTaskRepository
from integration.services.aws_ec2_api_client import AwsEc2Client

configure_logging(log_level=app_settings.log_level)
log = logging.getLogger(__name__)


# Global reference to monitoring scheduler for lifecycle management
_monitoring_scheduler: WorkerMonitoringScheduler | None = None


@asynccontextmanager
async def lifespan_with_monitoring(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for worker monitoring startup and shutdown.

    Manages the lifecycle of the worker monitoring scheduler:
    - Startup: Creates and starts the monitoring scheduler with scoped dependencies
    - Shutdown: Stops the monitoring scheduler

    Args:
        app: FastAPI application instance with configured services

    Yields:
        Control to the application during its runtime
    """
    global _monitoring_scheduler

    # Startup
    if app_settings.worker_monitoring_enabled:
        log.info("🚀 Starting worker monitoring scheduler...")

        # Create a scope to access scoped services like repositories
        # Note: create_scope() returns a regular context manager, not async
        scope = app.state.services.create_scope()
        try:
            # Get required dependencies from scoped service provider
            worker_repository = scope.get_required_service(CMLWorkerRepository)
            aws_client = scope.get_required_service(AwsEc2Client)
            background_task_bus = scope.get_required_service(BackgroundTasksBus)
            background_task_scheduler = scope.get_required_service(
                BackgroundTaskScheduler
            )

            # Get notification handler singleton from service provider
            notification_handler = scope.get_required_service(WorkerNotificationHandler)

            # Create monitoring scheduler
            scheduler = WorkerMonitoringScheduler(
                worker_repository=worker_repository,
                aws_client=aws_client,
                notification_handler=notification_handler,
                background_task_bus=background_task_bus,
                background_task_scheduler=background_task_scheduler,
                poll_interval=app_settings.worker_metrics_poll_interval,
            )

            # Store reference for lifecycle management
            _monitoring_scheduler = scheduler

            # Start the scheduler
            await _monitoring_scheduler.start_async()

            log.info("✅ Worker monitoring scheduler started")
        finally:
            # Dispose the scope after initialization
            scope.dispose()
    else:
        log.info("⚠️ Worker monitoring disabled in settings")

    yield  # Application runs

    # Shutdown
    if _monitoring_scheduler:
        log.info("🛑 Stopping worker monitoring scheduler...")
        await _monitoring_scheduler.stop_async()
        log.info("✅ Worker monitoring scheduler stopped")


def configure_worker_monitoring(
    app: FastAPI,
) -> None:
    """Configure worker monitoring services and lifecycle hooks.

    Note: This function is now a placeholder for backwards compatibility.
    The actual lifecycle management is handled by the lifespan_with_monitoring
    context manager which is integrated into the application build process.

    Args:
        app: FastAPI application instance with configured services
    """
    if not app_settings.worker_monitoring_enabled:
        log.info("⚠️ Worker monitoring disabled in settings")
        return

    log.info("📊 Worker monitoring will be configured via lifespan events")
    log.info("✅ Worker monitoring services configured with APScheduler")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Creates separate apps for:
    - API backend (/api prefix) - REST API for task management
    - UI frontend (/ prefix) - Web interface

    Returns:
        Configured FastAPI application with multiple mounted apps
    """
    log.debug("🚀 Creating Cml Cloud Manager application...")

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

    # Configure AWS EC2 Client
    AwsEc2Client.configure(builder)

    # Configure BackgroundTaskScheduler for worker monitoring jobs
    BackgroundTaskScheduler.configure(
        builder,
        modules=["application.services"],  # Scan for @backgroundjob decorated classes
    )

    # Register WorkerNotificationHandler as singleton service
    # This allows jobs to look it up from service provider without pickling callback references
    if app_settings.worker_monitoring_enabled:
        notification_handler_instance = WorkerNotificationHandler(
            cpu_threshold=90.0,
            memory_threshold=90.0,
        )
        builder.services.add_singleton(
            WorkerNotificationHandler, singleton=notification_handler_instance
        )
        log.info("✅ Registered WorkerNotificationHandler as singleton service")

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
            custom_setup=lambda app, service_provider: configure_api_openapi(
                app, app_settings
            ),
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

    # Integrate worker monitoring lifespan
    # Since build_app_with_lifespan already manages core lifespan,
    # we add monitoring as an additional router with lifespan
    from fastapi import APIRouter

    monitoring_router = APIRouter(lifespan=lifespan_with_monitoring)
    app.include_router(monitoring_router)

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

    # Configure worker monitoring (after app is built and services are available)
    configure_worker_monitoring(app)

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
