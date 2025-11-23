"""Sync Worker CML Data command with handler.

This command synchronizes the worker's CML service data including
version, health status, system stats, licensing, and labs.
"""

import logging
from dataclasses import asdict, dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.decorators import retry_on_concurrency_conflict
from application.services.cml_health_service import CMLHealthService
from application.settings import Settings
from domain.enums import CMLServiceStatus, CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class SyncWorkerCMLDataCommand(Command[OperationResult[dict]]):
    """Command to synchronize worker's CML service data.

    This command:
    1. Performs CML service health check
    2. Queries CML API for version and system information
    3. Collects system health and statistics
    4. Retrieves licensing information
    5. Updates worker with CML metrics

    Returns dict with sync summary.
    """

    worker_id: str


class SyncWorkerCMLDataCommandHandler(
    CommandHandlerBase,
    CommandHandler[SyncWorkerCMLDataCommand, OperationResult[dict]],
):
    """Handle CML service data synchronization for worker."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        cml_health_service: CMLHealthService,
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.cml_health_service = cml_health_service
        self.settings = settings

    @retry_on_concurrency_conflict(max_attempts=3, initial_delay=0.1)
    async def handle_async(self, request: SyncWorkerCMLDataCommand) -> OperationResult[dict]:
        """Handle sync worker CML data command.

        Args:
            request: Sync command with worker ID

        Returns:
            OperationResult with sync summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "sync_cml_data",
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # 1. Load worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(command.worker_id)

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("cml_worker.current_status", worker.state.status.value)
                span.set_attribute("cml_worker.has_endpoint", bool(worker.state.https_endpoint))
                span.set_attribute("cml_worker.service_status", worker.state.service_status.value)

            # 2. Skip if worker not running or has no endpoint
            if worker.state.status != CMLWorkerStatus.RUNNING:
                log.info(
                    f"Skipping CML data sync for worker {command.worker_id} - "
                    f"status is {worker.state.status.value}, not RUNNING"
                )
                return self.ok(
                    {
                        "worker_id": command.worker_id,
                        "status": worker.state.status.value,
                        "cml_data_synced": False,
                        "reason": "Worker not running",
                    }
                )

            if not worker.state.https_endpoint:
                log.warning(f"Skipping CML data sync for worker {command.worker_id} - " f"no HTTPS endpoint configured")
                return self.ok(
                    {
                        "worker_id": command.worker_id,
                        "status": worker.state.status.value,
                        "cml_data_synced": False,
                        "reason": "No HTTPS endpoint",
                    }
                )

            # 3. Query CML API for system information and health
            # Resilient approach: Try to collect as much data as possible without failing fast
            # Service status is determined based on what APIs respond successfully
            with tracer.start_as_current_span("query_cml_api") as span:
                # Determine endpoint to use (public or private based on settings)
                endpoint = worker.get_effective_endpoint(self.settings.use_private_ip_for_monitoring)
                if endpoint != worker.state.https_endpoint:
                    log.debug(f"Using private IP endpoint for monitoring: {endpoint}")

                log.info(f"Querying CML API for worker {command.worker_id} at {endpoint}")

                # Use CMLHealthService to check health and collect metrics
                health_result = await self.cml_health_service.check_health(
                    endpoint=endpoint,
                    timeout=15.0,
                )

                # Log any errors encountered during health check
                if health_result.errors:
                    for key, error in health_result.errors.items():
                        log.warning(f"⚠️ Health check error for {key} on worker {command.worker_id}: {error}")
                        span.set_attribute(f"{key}.error", error)

                # Determine service status based on what we successfully retrieved
                if not health_result.is_accessible:
                    # Nothing worked - service is unavailable
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.UNAVAILABLE,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.info(f"❌ CML service not accessible for worker {command.worker_id} - " f"all API calls failed")
                    # Save and return - don't bail completely, just mark unavailable
                    await self.cml_worker_repository.update_async(worker)
                    return self.ok(
                        {
                            "worker_id": command.worker_id,
                            "cml_data_synced": False,
                            "reason": "CML API not accessible",
                            "service_status": CMLServiceStatus.UNAVAILABLE.value,
                        }
                    )

                # At least one API worked - update service status based on health
                if health_result.is_healthy:
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.AVAILABLE,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.info(f"✅ CML service healthy for worker {command.worker_id} - " f"marked as AVAILABLE")
                elif health_result.is_accessible:
                    # System info worked but health didn't - mark as AVAILABLE anyway
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.AVAILABLE,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.info(
                        f"✅ CML service responding for worker {command.worker_id} - "
                        f"marked as AVAILABLE (health check unavailable)"
                    )
                else:
                    # Should be covered by is_accessible check above, but just in case
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.ERROR,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.warning(f"⚠️ CML service status unclear for worker {command.worker_id} - " f"marked as ERROR")

                # Update CML metrics with whatever data we have
                system_health_dict = None
                if health_result.system_health:
                    system_health_dict = {
                        "valid": health_result.system_health.valid,
                        "is_licensed": health_result.system_health.is_licensed,
                        "is_enterprise": health_result.system_health.is_enterprise,
                        "computes": health_result.system_health.computes,
                        "controller": health_result.system_health.controller,
                    }

                # Safely serialize system_stats
                system_info_dict = {}
                if health_result.system_stats:
                    try:
                        system_info_dict = asdict(health_result.system_stats)
                    except Exception as e:
                        log.warning(f"Failed to serialize system_stats for worker {command.worker_id}: {e}")

                # Update metrics (even with partial data)
                worker.update_cml_metrics(
                    cml_version=health_result.version,
                    system_info=system_info_dict,
                    system_health=system_health_dict,
                    license_info=health_result.license_info,
                    ready=health_result.ready,
                    uptime_seconds=None,
                    labs_count=health_result.labs_count,
                    change_threshold_percent=self.settings.metrics_change_threshold_percent,
                )

                # Set tracing attributes
                span.set_attribute("cml.version", health_result.version or "unknown")
                span.set_attribute("cml.ready", health_result.ready)
                span.set_attribute(
                    "cml.licensed",
                    health_result.system_health.is_licensed if health_result.system_health else False,
                )
                span.set_attribute("cml.valid", health_result.is_healthy)
                span.set_attribute(
                    "cml.nodes_running",
                    health_result.system_stats.running_nodes if health_result.system_stats else 0,
                )

                log.info(
                    f"✅ CML data synced for worker {command.worker_id}: "
                    f"version={health_result.version}, ready={health_result.ready}, "
                    f"service={worker.state.service_status.value}"
                )

            # 5. Save updated worker
            with tracer.start_as_current_span("save_worker"):
                await self.cml_worker_repository.update_async(worker)

            # 6. Build result summary
            result = {
                "worker_id": command.worker_id,
                "cml_data_synced": True,
                "service_status": worker.state.service_status.value,
                "cml_version": worker.state.metrics.version,
                "cml_ready": worker.state.metrics.ready,
                "labs_count": worker.state.metrics.labs_count,
            }

            log.info(
                f"Synced CML data for worker {command.worker_id}: "
                f"service={worker.state.service_status.value}, version={worker.state.metrics.version}"
            )

            return self.ok(result)

        except Exception as ex:
            log.error(
                f"Failed to sync CML data for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
            return self.internal_server_error(f"Failed to sync worker CML data: {str(ex)}")
