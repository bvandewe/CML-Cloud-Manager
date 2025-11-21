"""Get CML Worker by ID query with handler."""

import logging
from dataclasses import dataclass
from typing import Any

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from domain.repositories import CMLWorkerRepository

logger = logging.getLogger(__name__)


@dataclass
class GetCMLWorkerByIdQuery(Query[OperationResult[dict[str, Any]]]):
    """Query to retrieve a single CML Worker by ID or AWS instance ID."""

    worker_id: str | None = None
    aws_instance_id: str | None = None


class GetCMLWorkerByIdQueryHandler(QueryHandler[GetCMLWorkerByIdQuery, OperationResult[dict[str, Any]]]):
    """Handle retrieving a single CML Worker."""

    def __init__(self, worker_repository: CMLWorkerRepository):
        super().__init__()
        self.worker_repository = worker_repository

    async def handle_async(self, request: GetCMLWorkerByIdQuery) -> OperationResult[dict[str, Any]]:
        """Handle get CML worker by ID query."""
        try:
            # Retrieve worker by ID or AWS instance ID
            if request.worker_id:
                worker = await self.worker_repository.get_by_id_async(request.worker_id)
                identifier = request.worker_id
            elif request.aws_instance_id:
                worker = await self.worker_repository.get_by_aws_instance_id_async(request.aws_instance_id)
                identifier = request.aws_instance_id
            else:
                return self.bad_request("Either worker_id or aws_instance_id must be provided")

            if not worker:
                return self.not_found("CML Worker", identifier)

            # Convert to dict representation
            result = {
                "id": worker.state.id,
                "name": worker.state.name,
                "aws_region": worker.state.aws_region,
                "aws_instance_id": worker.state.aws_instance_id,
                "instance_type": worker.state.instance_type,
                "ami_id": worker.state.ami_id,
                "ami_name": worker.state.ami_name,
                "ami_description": worker.state.ami_description,
                "ami_creation_date": worker.state.ami_creation_date,
                "status": worker.state.status.value,
                "service_status": worker.state.service_status.value,
                "cml_version": worker.state.metrics.version,
                "license_status": worker.state.license.status.value,
                "license_token": worker.state.license.token,
                "https_endpoint": worker.state.https_endpoint,
                "public_ip": worker.state.public_ip,
                "private_ip": worker.state.private_ip,
                # AWS Tags
                "aws_tags": worker.state.aws_tags,
                # EC2 Metrics
                "ec2_instance_state_detail": worker.state.ec2_instance_state_detail,
                "ec2_system_status_check": worker.state.ec2_system_status_check,
                "ec2_last_checked_at": (
                    worker.state.ec2_last_checked_at.isoformat() if worker.state.ec2_last_checked_at else None
                ),
                # CloudWatch Metrics
                "cloudwatch_cpu_utilization": worker.state.cloudwatch_cpu_utilization,
                "cloudwatch_memory_utilization": worker.state.cloudwatch_memory_utilization,
                "cloudwatch_last_collected_at": (
                    worker.state.cloudwatch_last_collected_at.isoformat()
                    if worker.state.cloudwatch_last_collected_at
                    else None
                ),
                "cloudwatch_detailed_monitoring_enabled": worker.state.cloudwatch_detailed_monitoring_enabled,
                # CML Metrics
                "cml_system_info": worker.state.metrics.system_info,
                "cml_system_health": worker.state.metrics.system_health,
                "cml_license_info": worker.state.license.raw_info,
                "cml_ready": worker.state.metrics.ready,
                "cml_uptime_seconds": worker.state.metrics.uptime_seconds,
                "cml_labs_count": worker.state.metrics.labs_count,
                "cml_last_synced_at": (
                    worker.state.metrics.last_synced_at.isoformat() if worker.state.metrics.last_synced_at else None
                ),
                # Metrics Timing
                "poll_interval": worker.state.poll_interval,
                "next_refresh_at": (worker.state.next_refresh_at.isoformat() if worker.state.next_refresh_at else None),
                # Backward compatibility (deprecated - use cloudwatch_last_collected_at)
                "active_labs_count": worker.state.metrics.labs_count,
                "cpu_utilization": worker.state.cloudwatch_cpu_utilization,
                "memory_utilization": worker.state.cloudwatch_memory_utilization,
                "created_at": worker.state.created_at.isoformat(),
                "updated_at": worker.state.updated_at.isoformat(),
                "start_initiated_at": (
                    worker.state.start_initiated_at.isoformat() if worker.state.start_initiated_at else None
                ),
                "stop_initiated_at": (
                    worker.state.stop_initiated_at.isoformat() if worker.state.stop_initiated_at else None
                ),
                "terminated_at": (worker.state.terminated_at.isoformat() if worker.state.terminated_at else None),
                "created_by": worker.state.created_by,
                # Activity tracking and idle detection
                "last_activity_at": (
                    worker.state.last_activity_at.isoformat() if worker.state.last_activity_at else None
                ),
                "last_activity_check_at": (
                    worker.state.last_activity_check_at.isoformat() if worker.state.last_activity_check_at else None
                ),
                "next_idle_check_at": (
                    worker.state.next_idle_check_at.isoformat() if worker.state.next_idle_check_at else None
                ),
                "target_pause_at": (worker.state.target_pause_at.isoformat() if worker.state.target_pause_at else None),
                "is_idle_detection_enabled": worker.state.is_idle_detection_enabled,
                # Pause/resume tracking
                "auto_pause_count": worker.state.auto_pause_count,
                "manual_pause_count": worker.state.manual_pause_count,
                "auto_resume_count": worker.state.auto_resume_count,
                "manual_resume_count": worker.state.manual_resume_count,
                "last_paused_at": (worker.state.last_paused_at.isoformat() if worker.state.last_paused_at else None),
                "last_resumed_at": (worker.state.last_resumed_at.isoformat() if worker.state.last_resumed_at else None),
                "paused_by": worker.state.paused_by,
                "pause_reason": worker.state.pause_reason,
            }

            logger.info(f"Retrieved CML worker {worker.state.id}")
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML worker: {e}", exc_info=True)
            return self.internal_server_error(str(e))
