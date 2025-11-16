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


class GetCMLWorkerByIdQueryHandler(
    QueryHandler[GetCMLWorkerByIdQuery, OperationResult[dict[str, Any]]]
):
    """Handle retrieving a single CML Worker."""

    def __init__(self, worker_repository: CMLWorkerRepository):
        super().__init__()
        self.worker_repository = worker_repository

    async def handle_async(
        self, request: GetCMLWorkerByIdQuery
    ) -> OperationResult[dict[str, Any]]:
        """Handle get CML worker by ID query."""
        try:
            # Retrieve worker by ID or AWS instance ID
            if request.worker_id:
                worker = await self.worker_repository.get_by_id_async(request.worker_id)
                identifier = request.worker_id
            elif request.aws_instance_id:
                worker = await self.worker_repository.get_by_aws_instance_id_async(
                    request.aws_instance_id
                )
                identifier = request.aws_instance_id
            else:
                return self.bad_request(
                    "Either worker_id or aws_instance_id must be provided"
                )

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
                "status": worker.state.status.value,
                "service_status": worker.state.service_status.value,
                "cml_version": worker.state.cml_version,
                "license_status": worker.state.license_status.value,
                "license_token": worker.state.license_token,
                "https_endpoint": worker.state.https_endpoint,
                "public_ip": worker.state.public_ip,
                "private_ip": worker.state.private_ip,
                "last_activity_at": (
                    worker.state.last_activity_at.isoformat()
                    if worker.state.last_activity_at
                    else None
                ),
                "active_labs_count": worker.state.active_labs_count,
                "cpu_utilization": worker.state.cpu_utilization,
                "memory_utilization": worker.state.memory_utilization,
                "created_at": worker.state.created_at.isoformat(),
                "updated_at": worker.state.updated_at.isoformat(),
                "terminated_at": (
                    worker.state.terminated_at.isoformat()
                    if worker.state.terminated_at
                    else None
                ),
                "created_by": worker.state.created_by,
            }

            logger.info(f"Retrieved CML worker {worker.state.id}")
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML worker: {e}", exc_info=True)
            return self.internal_server_error(str(e))
