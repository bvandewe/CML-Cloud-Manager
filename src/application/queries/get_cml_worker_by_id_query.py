"""Get CML Worker by ID query with handler."""

import logging
from dataclasses import dataclass
from typing import Any

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from application.mappers import map_worker_to_dto, worker_dto_to_dict
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

            # Use DTO mapper for consistent transformation
            dto = map_worker_to_dto(worker)
            result = worker_dto_to_dict(dto)

            logger.info(f"Retrieved CML worker {worker.state.id}")
            return self.ok(result)

        except Exception as e:
            logger.error(f"Error retrieving CML worker: {e}", exc_info=True)
            return self.internal_server_error(str(e))
