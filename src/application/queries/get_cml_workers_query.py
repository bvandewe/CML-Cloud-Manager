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
                    "created_at": worker.state.created_at.isoformat(),
                    "updated_at": worker.state.updated_at.isoformat(),
                }
                for worker in filtered_workers
            ]

            logger.info(
                f"Retrieved {len(result)} CML workers in region {request.aws_region.value}"
            )
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML workers: {e}", exc_info=True)
            return self.internal_server_error(str(e))
