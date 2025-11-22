"""Service for checking CML instance health and collecting system metrics.

This service encapsulates the logic for querying multiple CML API endpoints
to determine the overall health and status of a CML instance.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from integration.exceptions import IntegrationException
from integration.services.cml_api_client import CMLApiClientFactory

if TYPE_CHECKING:
    from neuroglia.hosting.web import WebApplicationBuilder

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class CMLHealthResult:
    """Consolidated result of a CML health check operation."""

    is_accessible: bool = False
    is_healthy: bool = False
    version: str | None = None
    ready: bool = False
    system_info: Any | None = None
    system_health: Any | None = None
    system_stats: Any | None = None
    license_info: dict | None = None
    labs_count: int = 0
    errors: dict[str, str] = field(default_factory=dict)


class CMLHealthService:
    """Service to check CML health and collect metrics."""

    def __init__(self, cml_api_client_factory: CMLApiClientFactory):
        self.cml_client_factory = cml_api_client_factory

    @classmethod
    def configure(cls, builder: "WebApplicationBuilder") -> None:
        """Configure the CMLHealthService in the dependency injection container."""
        builder.services.add_singleton(cls)

    async def check_health(self, endpoint: str, timeout: float = 15.0) -> CMLHealthResult:
        """Check health of a CML instance by querying multiple endpoints.

        Args:
            endpoint: The base URL of the CML instance (e.g., https://1.2.3.4)
            timeout: Request timeout in seconds

        Returns:
            CMLHealthResult containing consolidated status and metrics
        """
        result = CMLHealthResult(errors={})

        # Create client
        cml_client = self.cml_client_factory.create(base_url=endpoint, timeout=timeout)

        with tracer.start_as_current_span("cml_health_check") as span:
            span.set_attribute("cml.endpoint", endpoint)

            # 1. System Information (No Auth) - Best for basic connectivity
            try:
                system_info = await cml_client.get_system_information()
                if system_info:
                    result.is_accessible = True
                    result.system_info = system_info
                    result.version = system_info.version
                    result.ready = system_info.ready
                    log.debug(f"System info retrieved: version={result.version}, ready={result.ready}")
            except IntegrationException as e:
                log.warning(f"Failed to get system info from {endpoint}: {e}")
                result.errors["system_info"] = str(e)

            # 2. System Health (Auth Required)
            try:
                system_health = await cml_client.get_system_health()
                if system_health:
                    result.is_accessible = True
                    result.system_health = system_health
                    # Consider healthy if valid is true
                    result.is_healthy = system_health.valid
                    log.debug(f"System health retrieved: valid={system_health.valid}")
            except IntegrationException as e:
                log.warning(f"Failed to get system health from {endpoint}: {e}")
                result.errors["system_health"] = str(e)

            # 3. System Stats (Auth Required)
            try:
                system_stats = await cml_client.get_system_stats()
                if system_stats:
                    result.is_accessible = True
                    result.system_stats = system_stats
                    log.debug("System stats retrieved")
            except IntegrationException as e:
                log.warning(f"Failed to get system stats from {endpoint}: {e}")
                result.errors["system_stats"] = str(e)

            # 4. Licensing Info (Auth Required)
            try:
                license_info = await cml_client.get_licensing()
                if license_info:
                    result.license_info = license_info.raw_data
                    log.debug(f"License info retrieved: {license_info.registration_status}")
            except Exception as e:
                log.warning(f"Failed to get licensing info from {endpoint}: {e}")
                result.errors["licensing"] = str(e)

            # 5. Labs Count (Auth Required)
            try:
                labs = await cml_client.get_labs(show_all=True)
                if labs is not None:
                    result.labs_count = len(labs)
                    log.debug(f"Labs count retrieved: {result.labs_count}")
            except IntegrationException as e:
                log.warning(f"Failed to get labs count from {endpoint}: {e}")
                result.errors["labs_count"] = str(e)

            # Final health determination logic
            # If we got system_health, trust its 'valid' flag
            # If we only got system_info, we can consider it accessible but health is unknown (default false)
            # However, for practical purposes, if it's accessible and ready, we might consider it 'healthy enough'
            if not result.is_healthy and result.system_info and result.system_info.ready:
                # Fallback: if system_health failed (e.g. auth error) but system_info says ready
                # We might want to flag this differently, but for now let's keep is_healthy strict
                pass

            return result
