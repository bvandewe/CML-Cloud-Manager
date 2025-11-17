"""Get CML Workers query with handler."""

import logging
from dataclasses import dataclass
from typing import Any

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository
from integration.enums import AwsRegion

logger = logging.getLogger(__name__)


@dataclass
class GetCMLWorkersQuery(Query[OperationResult[list[dict[str, Any]]]]):
    """Query to retrieve CML Workers filtered by region and/or status."""

    aws_region: AwsRegion
    status: CMLWorkerStatus | None = None


class GetCMLWorkersQueryHandler(
    QueryHandler[GetCMLWorkersQuery, OperationResult[list[dict[str, Any]]]]
):
    """Handle retrieving CML Workers with optional filtering."""

    def __init__(self, worker_repository: CMLWorkerRepository):
        super().__init__()
        self.worker_repository = worker_repository

    async def handle_async(
        self, request: GetCMLWorkersQuery
    ) -> OperationResult[list[dict[str, Any]]]:
        """Handle get CML workers query."""
        try:
            # Get workers based on status filter
            if request.status:
                workers = await self.worker_repository.get_by_status_async(
                    request.status
                )
            else:
                workers = await self.worker_repository.get_active_workers_async()

            # Filter by AWS region
            filtered_workers = [
                worker
                for worker in workers
                if worker.state.aws_region == request.aws_region.value
            ]

            # Convert to dict representations
            result = [
                {
                    "id": worker.state.id,
                    "name": worker.state.name,
                    "aws_region": worker.state.aws_region,
                    "aws_instance_id": worker.state.aws_instance_id,
                    "instance_type": worker.state.instance_type,
                    "status": worker.state.status.value,
                    "service_status": worker.state.service_status.value,
                    "cml_version": worker.state.cml_version,
                    "https_endpoint": worker.state.https_endpoint,
                    "public_ip": worker.state.public_ip,
                    "private_ip": worker.state.private_ip,
                    "license_status": worker.state.license_status.value,
                    "cml_labs_count": worker.state.cml_labs_count,
                    "created_at": worker.state.created_at.isoformat(),
                    "updated_at": worker.state.updated_at.isoformat(),
                }
                for worker in filtered_workers
            ]

            # Extract CML metrics (CPU, memory, storage) from cml_system_info if available
            for idx, worker in enumerate(filtered_workers):
                system_info = worker.state.cml_system_info or {}
                # Get first compute node stats
                first_compute = next(iter(system_info.values()), {})
                stats = first_compute.get("stats", {})

                # Extract CML telemetry metrics
                cpu_stats = stats.get("cpu", {})
                memory_stats = stats.get("memory", {})
                disk_stats = stats.get("disk", {})

                # CPU utilization: calculate from user + system time
                cpu_util = None
                if cpu_stats:
                    user_percent = cpu_stats.get("user_percent", 0.0)
                    system_percent = cpu_stats.get("system_percent", 0.0)
                    if user_percent is not None and system_percent is not None:
                        cpu_util = user_percent + system_percent

                # Memory utilization: calculate from available vs total
                memory_util = None
                if memory_stats:
                    available_kb = memory_stats.get("available_kb", 0)
                    total_kb = memory_stats.get("total_kb", 1)
                    if total_kb > 0 and available_kb is not None:
                        used_kb = total_kb - available_kb
                        memory_util = (used_kb / total_kb) * 100

                # Storage utilization: calculate from size vs capacity
                storage_util = None
                if disk_stats:
                    size_kb = disk_stats.get("size_kb", 0)
                    capacity_kb = disk_stats.get("capacity_kb", 1)
                    if capacity_kb > 0 and size_kb is not None:
                        storage_util = (size_kb / capacity_kb) * 100

                result[idx]["cpu_utilization"] = cpu_util
                result[idx]["memory_utilization"] = memory_util
                result[idx]["storage_utilization"] = storage_util

            logger.info(
                f"Retrieved {len(result)} CML workers in region {request.aws_region.value}"
            )
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML workers: {e}", exc_info=True)
            return self.internal_server_error(str(e))
