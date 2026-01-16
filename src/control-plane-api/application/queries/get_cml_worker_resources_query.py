"""Get CML Worker resources utilization query with handler."""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler

from domain.repositories import CMLWorkerRepository
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.services.aws_ec2_api_client import (
    AwsEc2Client,
    Ec2InstanceResourcesUtilization,
)

logger = logging.getLogger(__name__)


@dataclass
class GetCMLWorkerResourcesQuery(Query[OperationResult[Ec2InstanceResourcesUtilization]]):
    """Query to retrieve CML Worker CloudWatch resource utilization metrics."""

    worker_id: str | None = None
    aws_instance_id: str | None = None
    aws_region: AwsRegion | None = None
    relative_start_time: Ec2InstanceResourcesUtilizationRelativeStartTime = (
        Ec2InstanceResourcesUtilizationRelativeStartTime.ONE_MIN_AGO
    )


class GetCMLWorkerResourcesQueryHandler(
    QueryHandler[GetCMLWorkerResourcesQuery, OperationResult[Ec2InstanceResourcesUtilization]]
):
    """Handle retrieving CML Worker CloudWatch metrics."""

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        ec2_client: AwsEc2Client,
    ):
        super().__init__()
        self.worker_repository = worker_repository
        self.ec2_client = ec2_client

    async def handle_async(
        self, request: GetCMLWorkerResourcesQuery
    ) -> OperationResult[Ec2InstanceResourcesUtilization]:
        """Handle get CML worker resources query."""
        try:
            # Resolve worker to get AWS instance ID and region
            instance_id = request.aws_instance_id
            region = request.aws_region

            if request.worker_id:
                worker = await self.worker_repository.get_by_id_async(request.worker_id)
                if not worker:
                    return self.not_found("CML Worker", request.worker_id)

                instance_id = worker.state.aws_instance_id
                region = AwsRegion(worker.state.aws_region)

            if not instance_id:
                return self.bad_request("Worker has no assigned AWS instance ID")

            if not region:
                return self.bad_request("AWS region must be provided or resolved from worker")

            # Query CloudWatch metrics
            logger.info(f"Querying CloudWatch metrics for instance {instance_id} " f"in region {region.value}")

            metrics = self.ec2_client.get_instance_resources_utilization(
                aws_region=region,
                instance_id=instance_id,
                relative_start_time=request.relative_start_time,
            )

            if not metrics:
                return self.not_found(
                    "CloudWatch metrics",
                    f"instance {instance_id} in region {region.value}",
                )

            return self.ok(metrics)

        except Exception as e:
            logger.error(f"Error retrieving CML worker resources: {e}", exc_info=True)
            return self.internal_server_error(str(e))
