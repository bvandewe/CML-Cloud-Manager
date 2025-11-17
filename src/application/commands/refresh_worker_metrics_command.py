"""Refresh Worker Metrics command with handler.

This command orchestrates collecting fresh metrics from AWS for a worker
and updating the worker aggregate state. It's the single source of truth
for worker metrics refresh logic.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

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
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.exceptions import IntegrationException
from integration.services.aws_ec2_api_client import AwsEc2Client
from integration.services.cml_api_client import CMLApiClient
from observability.metrics import meter

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# OTEL Gauges for worker metrics
_worker_cpu_gauge = meter.create_gauge(
    name="cml.worker.cpu_utilization",
    description="Worker CPU utilization percentage",
    unit="%",
)

_worker_memory_gauge = meter.create_gauge(
    name="cml.worker.memory_utilization",
    description="Worker memory utilization percentage",
    unit="%",
)

_worker_labs_gauge = meter.create_gauge(
    name="cml.worker.labs_count",
    description="Number of active labs on worker",
    unit="1",
)

_worker_status_gauge = meter.create_gauge(
    name="cml.worker.status",
    description="Worker status (0=pending, 1=running, 2=stopped, 3=terminated)",
    unit="1",
)


@dataclass
class RefreshWorkerMetricsCommand(Command[OperationResult[dict]]):
    """Command to refresh worker metrics from AWS.

    This command:
    1. Queries AWS EC2 for current instance state
    2. Queries AWS CloudWatch for CPU/memory metrics
    3. Updates worker aggregate with latest data
    4. Updates OTEL metrics gauges
    5. Publishes domain events for state changes

    Returns dict with refreshed metrics summary.
    """

    worker_id: str


class RefreshWorkerMetricsCommandHandler(
    CommandHandlerBase,
    CommandHandler[RefreshWorkerMetricsCommand, OperationResult[dict]],
):
    """Handle worker metrics refresh from AWS sources."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client
        self.settings = settings

    async def handle_async(
        self, request: RefreshWorkerMetricsCommand
    ) -> OperationResult[dict]:
        """Handle refresh worker metrics command.

        Args:
            request: Refresh command with worker ID

        Returns:
            OperationResult with metrics summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "refresh_metrics",
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

                if not worker.state.aws_instance_id:
                    error_msg = (
                        f"CML Worker {command.worker_id} has no AWS instance assigned"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id)
                span.set_attribute(
                    "cml_worker.current_status", worker.state.status.value
                )

            # 2. Query AWS EC2 for current instance status
            with tracer.start_as_current_span("query_ec2_instance_status") as span:
                aws_region = AwsRegion(worker.state.aws_region)

                status_checks = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_checks:
                    error_msg = (
                        f"EC2 instance {worker.state.aws_instance_id} not found in AWS"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2.current_state", ec2_state)

                # Update EC2 health metrics
                worker.update_ec2_metrics(
                    instance_state_detail=status_checks["instance_status_check"],
                    system_status_check=status_checks["ec2_system_status_check"],
                )

                # Get EC2 instance details (IPs, type, AMI)
                instance_details = self.aws_ec2_client.get_instance_details(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if instance_details:
                    # Update instance details
                    worker.update_ec2_instance_details(
                        public_ip=instance_details.public_ip,
                        private_ip=instance_details.private_ip,
                        instance_type=instance_details.type,
                        ami_id=instance_details.image_id,
                        ami_name=None,  # AMI name can be fetched separately if needed
                    )

                    # Auto-populate HTTPS endpoint if public IP available and not already set
                    if instance_details.public_ip:
                        log.info(
                            f"Worker {command.worker_id} has public IP: {instance_details.public_ip}, "
                            f"current endpoint: {worker.state.https_endpoint}"
                        )
                        if not worker.state.https_endpoint:
                            worker.update_endpoint(
                                https_endpoint=f"https://{instance_details.public_ip}",
                                public_ip=instance_details.public_ip,
                            )
                            log.info(
                                f"Auto-populated HTTPS endpoint for worker {command.worker_id}: "
                                f"https://{instance_details.public_ip}"
                            )
                    else:
                        log.warning(
                            f"Worker {command.worker_id} has no public IP from AWS, cannot auto-populate endpoint"
                        )

                # Check CloudWatch detailed monitoring status
                monitoring_state = status_checks.get("monitoring_state", "disabled")
                monitoring_enabled = monitoring_state == "enabled"

                # Update worker monitoring status if changed
                if (
                    worker.state.cloudwatch_detailed_monitoring_enabled
                    != monitoring_enabled
                ):
                    worker.update_cloudwatch_monitoring(monitoring_enabled)
                    log.info(
                        f"Worker {command.worker_id} CloudWatch monitoring status updated: {monitoring_state}"
                    )

                # Map EC2 state to worker status
                ec2_state_to_worker_status = {
                    "pending": CMLWorkerStatus.PENDING,
                    "running": CMLWorkerStatus.RUNNING,
                    "stopping": CMLWorkerStatus.STOPPING,
                    "stopped": CMLWorkerStatus.STOPPED,
                    "shutting-down": CMLWorkerStatus.TERMINATED,
                    "terminated": CMLWorkerStatus.TERMINATED,
                }
                new_status = ec2_state_to_worker_status.get(
                    ec2_state, CMLWorkerStatus.PENDING
                )

                # Update worker status if changed
                status_changed = worker.update_status(new_status)
                if status_changed:
                    log.info(
                        f"Worker {command.worker_id} status updated: {worker.state.status.value}"
                    )

            # 3. Query AWS CloudWatch for metrics (only if running)
            metrics_summary = {}
            if new_status == CMLWorkerStatus.RUNNING:
                with tracer.start_as_current_span("query_cloudwatch_metrics") as span:
                    try:
                        metrics = self.aws_ec2_client.get_instance_resources_utilization(
                            aws_region=aws_region,
                            instance_id=worker.state.aws_instance_id,
                            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
                        )

                        if metrics:
                            # Parse metrics values - handle error strings from CloudWatch
                            try:
                                cpu_value = float(metrics.avg_cpu_utilization)
                                memory_value = float(metrics.avg_memory_utilization)
                            except (ValueError, TypeError):
                                log.warning(
                                    f"CloudWatch returned non-numeric metrics for worker {command.worker_id}: "
                                    f"CPU={metrics.avg_cpu_utilization}, Memory={metrics.avg_memory_utilization}"
                                )
                                # Skip telemetry update if metrics are invalid
                            else:
                                # Update CloudWatch metrics with source-specific method
                                worker.update_cloudwatch_metrics(
                                    cpu_utilization=cpu_value,
                                    memory_utilization=memory_value,
                                )

                                metrics_summary = {
                                    "cpu_utilization": metrics.avg_cpu_utilization,
                                    "memory_utilization": metrics.avg_memory_utilization,
                                    "start_time": metrics.start_time.isoformat(),
                                    "end_time": metrics.end_time.isoformat(),
                                }

                                span.set_attribute("metrics.cpu", cpu_value)
                                span.set_attribute("metrics.memory", memory_value)

                                log.info(
                                    f"Worker {command.worker_id} metrics: CPU={cpu_value}%, Memory={memory_value}%"
                                )
                    except IntegrationException as e:
                        log.warning(
                            f"Failed to collect CloudWatch metrics for worker {command.worker_id}: {e}"
                        )
                        # Continue anyway - not critical

            # 3.5 Health check CML service availability (if RUNNING and has endpoint)
            if new_status == CMLWorkerStatus.RUNNING and worker.state.https_endpoint:
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

            # 3.6 Query CML API for version and system stats (only if RUNNING and service AVAILABLE)
            log.info(
                f"CML API check for worker {command.worker_id}: "
                f"status={new_status}, "
                f"has_endpoint={bool(worker.state.https_endpoint)}, "
                f"endpoint={worker.state.https_endpoint}, "
                f"service_status={worker.state.service_status}"
            )

            if (
                new_status == CMLWorkerStatus.RUNNING
                and worker.state.https_endpoint
                and worker.state.service_status == CMLServiceStatus.AVAILABLE
            ):
                with tracer.start_as_current_span("query_cml_api") as span:
                    log.info(
                        f"Attempting to query CML API for worker {command.worker_id} "
                        f"at {worker.state.https_endpoint}"
                    )
                    try:
                        # Create CML API client for this worker
                        cml_client = CMLApiClient(
                            base_url=worker.state.https_endpoint,
                            username=self.settings.cml_worker_api_username,
                            password=self.settings.cml_worker_api_password,
                            verify_ssl=False,  # CML typically uses self-signed certs
                            timeout=15.0,
                        )

                        # Query system information (version, ready state) - no auth needed
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
                                uptime_seconds=None,  # Could parse from system_info if needed
                                labs_count=system_stats.running_nodes,
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
                            span.set_attribute(
                                "cml.nodes_total", system_stats.total_nodes
                            )
                            span.set_attribute(
                                "cml.cpu_allocated", system_stats.allocated_cpus
                            )

                            log.info(
                                f"Worker {command.worker_id} CML stats: "
                                f"Version={cml_version}, Ready={cml_ready}, "
                                f"Licensed={system_health.is_licensed if system_health else 'unknown'}, "
                                f"Nodes={system_stats.running_nodes}/{system_stats.total_nodes}, "
                                f"CPUs allocated={system_stats.allocated_cpus}"
                            )
                        else:
                            # No stats but we have version info
                            worker.update_cml_metrics(
                                cml_version=cml_version,
                                system_info={},
                                system_health=system_health_dict,
                                license_info=license_info_dict,
                                ready=cml_ready,
                                uptime_seconds=None,
                                labs_count=0,
                            )
                            log.warning(
                                f"CML API returned no stats for worker {command.worker_id}, version={cml_version}"
                            )

                    except IntegrationException as e:
                        log.warning(
                            f"Failed to collect CML metrics for worker {command.worker_id}: {e}"
                        )
                        # Update worker to mark CML as not ready
                        worker.update_cml_metrics(
                            cml_version=None,
                            system_info={},
                            system_health=None,
                            license_info=None,
                            ready=False,
                            uptime_seconds=None,
                            labs_count=0,
                        )
            else:
                log.info(
                    f"Skipping CML API query for worker {command.worker_id} - "
                    f"not meeting requirements (status={new_status}, "
                    f"has_endpoint={bool(worker.state.https_endpoint)}, "
                    f"service_status={worker.state.service_status})"
                )

            # 4. Persist worker aggregate (publishes domain events)
            with tracer.start_as_current_span("persist_worker") as span:
                await self.cml_worker_repository.update_async(worker)
                span.set_attribute("worker.persisted", True)

                log.info(f"✅ Worker {command.worker_id} state persisted to repository")

            # 5. Update OTEL metrics
            with tracer.start_as_current_span("update_otel_metrics"):
                metric_attributes = {
                    "worker_id": command.worker_id,
                    "region": worker.state.aws_region,
                    "worker_name": worker.state.name,
                }

                # Status gauge (numeric mapping)
                status_value_map = {
                    CMLWorkerStatus.PENDING: 0,
                    CMLWorkerStatus.RUNNING: 1,
                    CMLWorkerStatus.STOPPING: 2,
                    CMLWorkerStatus.STOPPED: 3,
                    CMLWorkerStatus.TERMINATED: 4,
                }
                _worker_status_gauge.set(
                    status_value_map.get(worker.state.status, 0), metric_attributes
                )

                # CPU/Memory gauges (from CloudWatch)
                if worker.state.cloudwatch_cpu_utilization is not None:
                    _worker_cpu_gauge.set(
                        worker.state.cloudwatch_cpu_utilization, metric_attributes
                    )

                if worker.state.cloudwatch_memory_utilization is not None:
                    _worker_memory_gauge.set(
                        worker.state.cloudwatch_memory_utilization, metric_attributes
                    )

                # Labs gauge (from CML API)
                _worker_labs_gauge.set(worker.state.cml_labs_count, metric_attributes)

                log.debug(f"OTEL metrics updated for worker {command.worker_id}")

            # 6. Build response summary
            response = {
                "worker_id": command.worker_id,
                "status": worker.state.status.value,
                "public_ip": worker.state.public_ip,
                "private_ip": worker.state.private_ip,
                "cpu_utilization": worker.state.cloudwatch_cpu_utilization,
                "memory_utilization": worker.state.cloudwatch_memory_utilization,
                "labs_count": worker.state.cml_labs_count,
                "https_endpoint": worker.state.https_endpoint,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics_summary,
            }

            # 7. Broadcast event to SSE clients for real-time UI updates
            try:
                from application.services.sse_event_relay import get_sse_relay

                sse_relay = get_sse_relay()
                await sse_relay.broadcast_event(
                    event_type="worker.metrics.updated",
                    data={
                        "worker_id": command.worker_id,
                        "status": worker.state.status.value,
                        "cpu_utilization": worker.state.cloudwatch_cpu_utilization,
                        "memory_utilization": worker.state.cloudwatch_memory_utilization,
                        "labs_count": worker.state.cml_labs_count,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                # Don't fail the command if SSE broadcast fails
                log.warning(
                    f"Failed to broadcast SSE event for worker {command.worker_id}: {e}"
                )

            log.info(f"✅ Metrics refresh completed for worker {command.worker_id}")
            return self.ok(response)

        except IntegrationException as ex:
            log.error(
                f"AWS integration error refreshing worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"AWS integration error: {ex}")

        except Exception as ex:
            log.error(
                f"Unexpected error refreshing worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"Unexpected error: {ex}")
