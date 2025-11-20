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


class GetCMLWorkersQueryHandler(QueryHandler[GetCMLWorkersQuery, OperationResult[list[dict[str, Any]]]]):
    """Handle retrieving CML Workers with optional filtering."""

    def __init__(self, worker_repository: CMLWorkerRepository):
        super().__init__()
        self.worker_repository = worker_repository

    async def handle_async(self, request: GetCMLWorkersQuery) -> OperationResult[list[dict[str, Any]]]:
        """Handle get CML workers query."""
        try:
            # Get workers based on status filter
            if request.status:
                workers = await self.worker_repository.get_by_status_async(request.status)
            else:
                workers = await self.worker_repository.get_active_workers_async()

            # Filter by AWS region
            filtered_workers = [worker for worker in workers if worker.state.aws_region == request.aws_region.value]

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
                    "aws_tags": worker.state.aws_tags,
                    "license_status": worker.state.license_status.value,
                    "cml_labs_count": worker.state.cml_labs_count,
                    "created_at": worker.state.created_at.isoformat(),
                    "updated_at": worker.state.updated_at.isoformat(),
                    "start_initiated_at": (
                        worker.state.start_initiated_at.isoformat() if worker.state.start_initiated_at else None
                    ),
                    "stop_initiated_at": (
                        worker.state.stop_initiated_at.isoformat() if worker.state.stop_initiated_at else None
                    ),
                    # Include raw system info so UI can derive additional metrics/fallbacks
                    "cml_system_info": worker.state.cml_system_info,
                }
                for worker in filtered_workers
            ]

            # Extract CML metrics (CPU, memory, storage) from cml_system_info if available
            # Fall back to CloudWatch metrics if CML metrics are not available
            for idx, worker in enumerate(filtered_workers):
                system_info = worker.state.cml_system_info or {}
                # Get first compute node stats
                first_compute = next(iter(system_info.values()), {})
                stats = first_compute.get("stats", {})

                # Extract CML telemetry metrics
                cpu_stats = stats.get("cpu", {})
                memory_stats = stats.get("memory", {})
                disk_stats = stats.get("disk", {})

                # Derive CPU utilization from CML
                cpu_util = None
                if cpu_stats:
                    # Prefer consolidated percent if available
                    percent = cpu_stats.get("percent")
                    if percent is not None:
                        try:
                            cpu_util = float(percent)
                        except (ValueError, TypeError):
                            cpu_util = None
                    else:
                        user_percent = cpu_stats.get("user_percent")
                        system_percent = cpu_stats.get("system_percent")
                        if user_percent is not None and system_percent is not None:
                            try:
                                cpu_util = float(user_percent) + float(system_percent)
                            except (ValueError, TypeError):
                                cpu_util = None

                # Fallback to CloudWatch CPU if CML not available
                if cpu_util is None and worker.state.cloudwatch_cpu_utilization is not None:
                    cpu_util = worker.state.cloudwatch_cpu_utilization

                # Derive Memory utilization from CML (require both total_kb & available_kb)
                memory_util = None
                if memory_stats:
                    total_kb = memory_stats.get("total_kb")
                    available_kb = memory_stats.get("available_kb")
                    if (
                        isinstance(total_kb, (int, float))
                        and isinstance(available_kb, (int, float))
                        and total_kb > 0
                        and available_kb <= total_kb
                    ):
                        used_kb = total_kb - available_kb
                        memory_util = (used_kb / total_kb) * 100

                # Fallback to CloudWatch memory if CML not available
                if memory_util is None and worker.state.cloudwatch_memory_utilization is not None:
                    memory_util = worker.state.cloudwatch_memory_utilization

                # Derive Storage utilization from CML (require both size_kb & capacity_kb)
                storage_util = None
                if disk_stats:
                    size_kb = disk_stats.get("size_kb")
                    capacity_kb = disk_stats.get("capacity_kb")
                    if (
                        isinstance(size_kb, (int, float))
                        and isinstance(capacity_kb, (int, float))
                        and capacity_kb > 0
                        and size_kb <= capacity_kb
                    ):
                        storage_util = (size_kb / capacity_kb) * 100

                # Clamp values to [0,100]
                def _clamp(v):
                    if v is None:
                        return None
                    try:
                        fv = float(v)
                    except (ValueError, TypeError):
                        return None
                    return max(0.0, min(100.0, fv))

                result[idx]["cpu_utilization"] = _clamp(cpu_util)
                result[idx]["memory_utilization"] = _clamp(memory_util)
                result[idx]["storage_utilization"] = _clamp(storage_util)

                # Debug logging
                logger.debug(
                    f"Worker {worker.state.name}: cpu={result[idx]['cpu_utilization']}, "
                    f"mem={result[idx]['memory_utilization']}, disk={result[idx]['storage_utilization']} "
                    f"(cml_system_info={'present' if worker.state.cml_system_info else 'missing'}, "
                    f"cloudwatch_cpu={worker.state.cloudwatch_cpu_utilization}, "
                    f"cloudwatch_mem={worker.state.cloudwatch_memory_utilization})"
                )

            logger.info(f"Retrieved {len(result)} CML workers in region {request.aws_region.value}")
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML workers: {e}", exc_info=True)
            return self.internal_server_error(str(e))
