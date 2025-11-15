"""Main application entry point with SubApp mounting."""

import logging
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
from application.services import configure_logging
from application.settings import app_settings
from domain.entities import Task
from domain.repositories import TaskRepository
from integration.repositories.motor_task_repository import MongoTaskRepository

configure_logging(log_level=app_settings.log_level)
log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Creates separate apps for:
    - API backend (/api prefix) - REST API for task management
    - UI frontend (/ prefix) - Web interface

    Returns:
        Configured FastAPI application with multiple mounted apps
    """
    log.debug("🚀 Creating Starter App application...")

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
        database_name="starter_app",
        collection_name="tasks",
        domain_repository_type=TaskRepository,
        implementation_type=MongoTaskRepository,
    )

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
        title="Starter App",
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
    log.info("   - UI: http://localhost:8020/")
    log.info("   - API Docs: http://localhost:8020/api/docs")
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
