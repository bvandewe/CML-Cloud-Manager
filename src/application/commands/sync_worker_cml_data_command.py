"""Sync Worker CML Data command with handler.

This command synchronizes the worker's CML service data including
version, health status, system stats, licensing, and labs.
"""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.settings import Settings
from domain.enums import CMLServiceStatus, CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.exceptions import IntegrationException
from integration.services.cml_api_client import CMLApiClient

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
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.settings = settings

    async def handle_async(
        self, request: SyncWorkerCMLDataCommand
    ) -> OperationResult[dict]:
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
                worker = await self.cml_worker_repository.get_by_id_async(
                    command.worker_id
                )

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute(
                    "cml_worker.current_status", worker.state.status.value
                )
                span.set_attribute(
                    "cml_worker.has_endpoint", bool(worker.state.https_endpoint)
                )
                span.set_attribute(
                    "cml_worker.service_status", worker.state.service_status.value
                )

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
                log.warning(
                    f"Skipping CML data sync for worker {command.worker_id} - "
                    f"no HTTPS endpoint configured"
                )
                return self.ok(
                    {
                        "worker_id": command.worker_id,
                        "status": worker.state.status.value,
                        "cml_data_synced": False,
                        "reason": "No HTTPS endpoint",
                    }
                )

            # 3. Health check CML service availability
            with tracer.start_as_current_span("health_check_cml_service") as span:
                log.info(
                    f"Performing CML service health check for worker {command.worker_id} "
                    f"at {worker.state.https_endpoint}"
                )
                try:
                    # Create CML API client for health check
                    health_check_client = CMLApiClient(
                        base_url=worker.state.https_endpoint,
                        username=self.settings.cml_worker_api_username,
                        password=self.settings.cml_worker_api_password,
                        verify_ssl=False,
                        timeout=10.0,
                    )

                    # Try to call system_health endpoint
                    system_health = await health_check_client.get_system_health()

                    if system_health and system_health.valid:
                        # Service is available and healthy
                        status_updated = worker.update_service_status(
                            new_service_status=CMLServiceStatus.AVAILABLE,
                            https_endpoint=worker.state.https_endpoint,
                        )
                        if status_updated:
                            log.info(
                                f"✅ CML service health check passed for worker {command.worker_id} - "
                                f"service marked as AVAILABLE (licensed={system_health.is_licensed}, "
                                f"enterprise={system_health.is_enterprise})"
                            )
                        span.set_attribute("health_check.passed", True)
                        span.set_attribute(
                            "service.licensed", system_health.is_licensed
                        )
                    else:
                        # Service responded but not healthy
                        worker.update_service_status(
                            new_service_status=CMLServiceStatus.ERROR,
                            https_endpoint=worker.state.https_endpoint,
                        )
                        log.warning(
                            f"⚠️  CML service health check failed for worker {command.worker_id} - "
                            f"service returned invalid health status"
                        )
                        span.set_attribute("health_check.passed", False)
                        # Don't continue if health check failed
                        await self.cml_worker_repository.update_async(worker)
                        return self.ok(
                            {
                                "worker_id": command.worker_id,
                                "cml_data_synced": False,
                                "reason": "CML service health check failed",
                            }
                        )

                except IntegrationException as e:
                    # Service not accessible
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.UNAVAILABLE,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.info(
                        f"❌ CML service not accessible for worker {command.worker_id}: {e} - "
                        f"service marked as UNAVAILABLE"
                    )
                    span.set_attribute("health_check.passed", False)
                    span.set_attribute("health_check.error", str(e))
                    # Save status and return
                    await self.cml_worker_repository.update_async(worker)
                    return self.ok(
                        {
                            "worker_id": command.worker_id,
                            "cml_data_synced": False,
                            "reason": f"CML service not accessible: {str(e)}",
                        }
                    )

                except Exception as e:
                    # Unexpected error during health check
                    worker.update_service_status(
                        new_service_status=CMLServiceStatus.ERROR,
                        https_endpoint=worker.state.https_endpoint,
                    )
                    log.warning(
                        f"⚠️  Unexpected error during CML health check for worker {command.worker_id}: {e}"
                    )
                    span.set_attribute("health_check.passed", False)
                    span.record_exception(e)
                    # Save status and return
                    await self.cml_worker_repository.update_async(worker)
                    return self.ok(
                        {
                            "worker_id": command.worker_id,
                            "cml_data_synced": False,
                            "reason": f"Health check error: {str(e)}",
                        }
                    )

            # 4. Query CML API for version and system stats (only if service AVAILABLE)
            if worker.state.service_status == CMLServiceStatus.AVAILABLE:
                with tracer.start_as_current_span("query_cml_api") as span:
                    log.info(
                        f"Querying CML API for worker {command.worker_id} "
                        f"at {worker.state.https_endpoint}"
                    )
                    try:
                        # Create CML API client for this worker
                        cml_client = CMLApiClient(
                            base_url=worker.state.https_endpoint,
                            username=self.settings.cml_worker_api_username,
                            password=self.settings.cml_worker_api_password,
                            verify_ssl=False,
                            timeout=15.0,
                        )

                        # Query system information (version, ready state)
                        system_info = await cml_client.get_system_information()
                        cml_version = system_info.version if system_info else None
                        cml_ready = system_info.ready if system_info else False

                        # Query system health (requires auth)
                        system_health = await cml_client.get_system_health()
                        system_health_dict = None
                        if system_health:
                            system_health_dict = {
                                "valid": system_health.valid,
                                "is_licensed": system_health.is_licensed,
                                "is_enterprise": system_health.is_enterprise,
                                "computes": system_health.computes,
                                "controller": system_health.controller,
                            }

                        # Query system stats (requires auth)
                        system_stats = await cml_client.get_system_stats()

                        # Query licensing information (requires auth)
                        license_info_dict = None
                        try:
                            license_info = await cml_client.get_licensing()
                            if license_info:
                                license_info_dict = license_info.raw_data
                                log.info(
                                    f"✅ CML licensing info collected for worker {command.worker_id}: "
                                    f"{license_info.active_license} ({license_info.registration_status})"
                                )
                        except Exception as e:
                            log.warning(
                                f"⚠️ Could not fetch CML licensing info for worker {command.worker_id}: {e}"
                            )

                        if system_stats:
                            # Update CML metrics in worker aggregate
                            worker.update_cml_metrics(
                                cml_version=cml_version,
                                system_info=system_stats.computes,
                                system_health=system_health_dict,
                                license_info=license_info_dict,
                                ready=cml_ready,
                                uptime_seconds=None,
                                labs_count=system_stats.running_nodes,
                                change_threshold_percent=self.settings.metrics_change_threshold_percent,
                            )

                            span.set_attribute("cml.version", cml_version or "unknown")
                            span.set_attribute("cml.ready", cml_ready)
                            span.set_attribute(
                                "cml.licensed",
                                system_health.is_licensed if system_health else False,
                            )
                            span.set_attribute(
                                "cml.valid",
                                system_health.valid if system_health else False,
                            )
                            span.set_attribute(
                                "cml.nodes_running", system_stats.running_nodes
                            )

                            log.info(
                                f"✅ CML data synced for worker {command.worker_id}: "
                                f"version={cml_version}, nodes={system_stats.running_nodes}"
                            )

                    except IntegrationException as e:
                        log.warning(
                            f"⚠️ Failed to query CML API for worker {command.worker_id}: {e}"
                        )
                        span.set_attribute("cml_api.error", str(e))
                        # Continue anyway - not critical

            # 5. Save updated worker
            with tracer.start_as_current_span("save_worker"):
                await self.cml_worker_repository.update_async(worker)

            # 6. Build result summary
            result = {
                "worker_id": command.worker_id,
                "cml_data_synced": True,
                "service_status": worker.state.service_status.value,
                "cml_version": worker.state.cml_version,
                "cml_ready": worker.state.cml_ready,
                "labs_count": worker.state.cml_labs_count,
            }

            log.info(
                f"Synced CML data for worker {command.worker_id}: "
                f"service={worker.state.service_status.value}, version={worker.state.cml_version}"
            )

            return self.ok(result)

        except Exception as ex:
            log.error(
                f"Failed to sync CML data for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(
                f"Failed to sync worker CML data: {str(ex)}"
            )
