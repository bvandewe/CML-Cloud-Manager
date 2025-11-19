import logging
from typing import Annotated, Any

from classy_fastapi.decorators import delete, get, post
from fastapi import Depends, HTTPException, Path
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles
from api.models import (
    CreateCMLWorkerRequest,
    DeleteCMLWorkerRequest,
    ImportCMLWorkerRequest,
    RegisterLicenseRequest,
    UpdateCMLWorkerTagsRequest,
)
from application.commands import (
    BulkImportCMLWorkersCommand,
    CreateCMLWorkerCommand,
    DeleteCMLWorkerCommand,
    EnableWorkerDetailedMonitoringCommand,
    ImportCMLWorkerCommand,
    StartCMLWorkerCommand,
    StopCMLWorkerCommand,
    UpdateCMLWorkerStatusCommand,
    UpdateCMLWorkerTagsCommand,
)
from application.commands.request_worker_data_refresh_command import (
    RequestWorkerDataRefreshCommand,
)
from application.queries import (
    GetCMLWorkerByIdQuery,
    GetCMLWorkerResourcesQuery,
    GetCMLWorkersQuery,
)
from domain.enums import CMLWorkerStatus
from integration.enums import (
    AwsRegion,
    Ec2InstanceResourcesUtilizationRelativeStartTime,
)
from integration.services.aws_ec2_api_client import Ec2InstanceResourcesUtilization

logger = logging.getLogger(__name__)

aws_region_annotation = Annotated[
    AwsRegion,
    Path(
        description="The identifier of the AWS Region where the CML Worker instance is hosted."
    ),
]
instance_id_annotation = Annotated[
    str,
    Path(
        description="The AWS identifier of the CML Worker instance.",
        example="i-abcdef12345abcdef",
        min_length=19,
        max_length=19,
        pattern=r"^i-[a-z0-9]{17}$",
    ),
]
worker_id_annotation = Annotated[str, Path(description="The CML Worker UUID.")]


class WorkersController(ControllerBase):
    def __init__(
        self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator
    ):
        """Runs API Calls to AWS EC2."""
        ControllerBase.__init__(self, service_provider, mapper, mediator)

    @get(
        "/region/{aws_region}/workers",
        response_model=list[dict],
        response_description="List of CML Workers",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def list_cml_workers(
        self,
        aws_region: aws_region_annotation,
        status: CMLWorkerStatus | None = None,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Queries for all CML Worker instances in a region.

        (**Requires valid token.**)"""
        query = GetCMLWorkersQuery(aws_region=aws_region, status=status)
        return self.process(await self.mediator.execute_async(query))

    @get(
        "/region/{aws_region}/workers/{worker_id}",
        response_model=dict,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_worker_details(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Queries for CML Worker instance details by worker ID.

        (**Requires valid token.**)"""
        query = GetCMLWorkerByIdQuery(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(query))

    @get(
        "/region/{aws_region}/instance/{instance_id}",
        response_model=dict,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_worker_by_instance_id(
        self,
        aws_region: aws_region_annotation,
        instance_id: instance_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Queries for CML Worker instance details by AWS instance ID.

        (**Requires valid token.**)"""
        query = GetCMLWorkerByIdQuery(aws_instance_id=instance_id)
        return self.process(await self.mediator.execute_async(query))

    @get(
        "/region/{aws_region}/workers/{worker_id}/resources",
        response_model=Ec2InstanceResourcesUtilization,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_worker_resources(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        start_time: Ec2InstanceResourcesUtilizationRelativeStartTime,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Queries AWS CloudWatch for CML Worker instance resource utilization.

        (**Requires valid token.**)"""
        query = GetCMLWorkerResourcesQuery(
            worker_id=worker_id,
            aws_region=aws_region,
            relative_start_time=start_time,
        )
        return self.process(await self.mediator.execute_async(query))

    @post(
        "/region/{aws_region}/workers",
        response_model=Any,
        status_code=201,
        responses=ControllerBase.error_responses,
    )
    async def create_new_cml_worker(
        self,
        aws_region: aws_region_annotation,
        request: CreateCMLWorkerRequest,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Creates a new CML Worker instance in AWS EC2.

        (**Requires `admin` role!**)"""
        logger.info(f"Creating CML worker '{request.name}' in region {aws_region}")
        command = CreateCMLWorkerCommand(
            aws_region=aws_region,
            name=request.name,
            instance_type=request.instance_type,
            ami_id=request.ami_id,
            ami_name=request.ami_name,
            cml_version=request.cml_version,
        )
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/import",
        response_model=Any,
        status_code=201,
        responses=ControllerBase.error_responses,
    )
    async def import_existing_cml_worker(
        self,
        aws_region: aws_region_annotation,
        request: ImportCMLWorkerRequest,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Imports existing EC2 instance(s) as CML Worker(s).

        This endpoint allows you to register EC2 instances that were created
        outside of CML Cloud Manager (e.g., via AWS Console, Terraform, etc.)

        You can specify either:
        - aws_instance_id: Direct lookup by instance ID
        - ami_id: Search for instances using that AMI
        - ami_name: Search for instances with matching AMI name

        The 'name' field is optional - if not provided, the AWS instance's
        name will be used automatically.

        **Bulk Import**: Set `import_all=true` to import all matching instances.
        This will skip any instances that are already registered as workers.

        (**Requires `admin` role!**)"""

        # Check if bulk import requested
        if request.import_all:
            logger.info(
                f"Bulk importing all matching EC2 instances as CML workers in region {aws_region}"
            )
            command = BulkImportCMLWorkersCommand(
                aws_region=aws_region,
                ami_id=request.ami_id,
                ami_name=request.ami_name,
                created_by=None,  # TODO: Extract from token
            )
            return self.process(await self.mediator.execute_async(command))
        else:
            logger.info(
                f"Importing existing EC2 instance as CML worker in region {aws_region}"
            )
            command = ImportCMLWorkerCommand(
                aws_region=aws_region,
                aws_instance_id=request.aws_instance_id,
                ami_id=request.ami_id,
                ami_name=request.ami_name,
                name=request.name,
            )
            return self.process(await self.mediator.execute_async(command))

    @delete(
        "/region/{aws_region}/workers/{worker_id}",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def delete_cml_worker(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        request: DeleteCMLWorkerRequest,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Deletes a CML Worker from the local database.

        By default, only removes the worker record from the database.
        Set 'terminate_instance' to true to also terminate the EC2 instance.

        (**Requires `admin` role!**)

        Warning: This operation cannot be undone. The worker record will be
        permanently removed from the database.
        """
        logger.info(
            f"Deleting CML worker {worker_id} in region {aws_region}, "
            f"terminate_instance={request.terminate_instance}"
        )
        command = DeleteCMLWorkerCommand(
            worker_id=worker_id,
            terminate_instance=request.terminate_instance,
            deleted_by=token.get("sub") if isinstance(token, dict) else None,
        )
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/start",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def start_cml_worker(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Starts a stopped CML Worker instance.

        (**Requires `admin` role!**)"""
        logger.info(f"Starting CML worker {worker_id} in region {aws_region}")
        command = StartCMLWorkerCommand(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/stop",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def stop_cml_worker(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Stops a running CML Worker instance.

        (**Requires `admin` role!**)"""
        logger.info(f"Stopping CML worker {worker_id} in region {aws_region}")
        command = StopCMLWorkerCommand(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/tags",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def update_cml_worker_tags(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        request: UpdateCMLWorkerTagsRequest,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Updates tags for a CML Worker instance.

        (**Requires `admin` role!**)"""
        logger.info(f"Updating tags for CML worker {worker_id} in region {aws_region}")
        command = UpdateCMLWorkerTagsCommand(worker_id=worker_id, tags=request.tags)
        return self.process(await self.mediator.execute_async(command))

    @get(
        "/region/{aws_region}/workers/{worker_id}/status",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_cml_worker_status(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Gets the current status of a CML Worker instance.

        (**Requires valid token.**)"""
        logger.info(f"Getting status for CML worker {worker_id} in region {aws_region}")
        command = UpdateCMLWorkerStatusCommand(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/refresh",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def refresh_worker(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Request worker refresh (asynchronous, event-driven).

        This endpoint schedules a background job to refresh all worker data and
        returns immediately with a scheduling decision. SSE events notify the UI of progress.

        What gets refreshed:
        - EC2 instance status and metadata
        - CloudWatch metrics (CPU, memory, storage)
        - CML service data (version, license, uptime, stats)
        - Lab records (topology, nodes, state)

        SSE Events:
        - worker.refresh.requested: Job scheduled successfully (eta_seconds provided)
        - worker.refresh.skipped: Request rejected with reason (not_running, rate_limited,
          background_job_imminent, already_scheduled)

        Subsequent worker data will arrive via worker.snapshot and worker.metrics.updated
        SSE events when the background job completes.

        Returns:
        - scheduled: boolean indicating if job was scheduled
        - reason: skip reason if scheduled=false
        - eta_seconds: estimated seconds until execution
        - retry_after_seconds: if rate_limited, seconds until next allowed refresh

        (**Requires valid token.**)"""
        logger.info(
            f"Requesting async refresh for CML worker {worker_id} in region {aws_region}"
        )
        command = RequestWorkerDataRefreshCommand(
            worker_id=worker_id, region=aws_region
        )
        result = await self.mediator.execute_async(command)

        return self.process(result)

    @post(
        "/region/{aws_region}/workers/{worker_id}/monitoring",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def enable_detailed_monitoring(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Enables detailed CloudWatch monitoring on a CML Worker instance.

        This enables 1-minute metric granularity instead of 5-minute (costs ~$2.10/month).

        (**Requires `admin` role!**)"""
        logger.info(
            f"Enabling detailed monitoring for CML worker {worker_id} in region {aws_region}"
        )
        command = EnableWorkerDetailedMonitoringCommand(worker_id=worker_id)
        result = await self.mediator.execute_async(command)

        if not result or not result.is_success:
            logger.error(
                f"Failed to enable monitoring for worker {worker_id}: {result}"
            )
            raise HTTPException(
                status_code=500, detail="Failed to enable detailed monitoring"
            )

        logger.info(f"✅ Successfully enabled monitoring for worker {worker_id}")
        return self.process(result)

    @post(
        "/region/{aws_region}/workers/{worker_id}/license",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def register_license(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        request: RegisterLicenseRequest,
        token: str = Depends(require_roles("admin")),
    ) -> Any:
        """Registers a license for a CML Worker instance.

        (**Requires `admin` role!**)"""
        logger.info(
            f"Registering license for CML worker {worker_id} in region {aws_region}"
        )
        # TODO: Implement RegisterCMLWorkerLicenseCommand when ready
        raise HTTPException(
            status_code=501, detail="License registration endpoint not yet implemented"
        )

    @get(
        "/{aws_region}/{worker_id}/activity",
        response_model=dict[str, Any],
        summary="Get Worker Activity Tracking Data",
        description="Retrieve activity tracking information including recent telemetry events and lifecycle timestamps.",
    )
    async def get_worker_activity(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        current_user: Annotated[dict, Depends(get_current_user)],
    ) -> dict[str, Any]:
        """Get activity tracking data for a CML worker.

        Returns recent telemetry events, last activity timestamp, pause/resume history,
        and idle detection state.

        (**Requires authentication!**)"""
        logger.info(
            f"Fetching activity data for worker {worker_id} in region {aws_region}"
        )

        from application.queries.get_worker_activity_query import GetWorkerActivityQuery

        result = await self.mediator.execute_async(
            GetWorkerActivityQuery(worker_id=worker_id)
        )

        if not result.is_successful:
            logger.warning(
                f"Failed to retrieve activity for worker {worker_id}: {result.errors}"
            )
            raise HTTPException(status_code=404, detail=str(result.errors))

        return result.content

    @get(
        "/{aws_region}/{worker_id}/idle-status",
        response_model=dict[str, Any],
        summary="Check Worker Idle Status",
        description="Check if worker is idle and eligible for auto-pause based on activity thresholds.",
    )
    async def get_worker_idle_status(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        current_user: Annotated[dict, Depends(get_current_user)],
    ) -> dict[str, Any]:
        """Check idle status for a CML worker.

        Returns idle state, eligibility for auto-pause, snooze period status,
        and timing information for next checks.

        (**Requires authentication!**)"""
        logger.info(
            f"Checking idle status for worker {worker_id} in region {aws_region}"
        )

        from application.queries.get_worker_idle_status_query import (
            GetWorkerIdleStatusQuery,
        )

        result = await self.mediator.execute_async(
            GetWorkerIdleStatusQuery(worker_id=worker_id)
        )

        if not result.is_successful:
            logger.warning(
                f"Failed to check idle status for worker {worker_id}: {result.errors}"
            )
            raise HTTPException(status_code=404, detail=str(result.errors))

        return result.content
