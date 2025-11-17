import logging
from typing import Annotated, Any, List

from classy_fastapi.decorators import delete, get, post
from fastapi import Depends, HTTPException, Path
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles
from api.models import (CreateCMLWorkerRequest, ImportCMLWorkerRequest,
                        RegisterLicenseRequest, UpdateCMLWorkerTagsRequest)
from application.commands import (CreateCMLWorkerCommand, ImportCMLWorkerCommand,
                                  StartCMLWorkerCommand, StopCMLWorkerCommand,
                                  TerminateCMLWorkerCommand,
                                  UpdateCMLWorkerStatusCommand,
                                  UpdateCMLWorkerTagsCommand)
from application.queries import (GetCMLWorkerByIdQuery, GetCMLWorkerResourcesQuery,
                                 GetCMLWorkersQuery)
from domain.enums import CMLWorkerStatus
from integration.enums import (AwsRegion,
                               Ec2InstanceResourcesUtilizationRelativeStartTime)
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
        response_model=List[dict],
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
        """Imports an existing EC2 instance as a CML Worker.

        This endpoint allows you to register EC2 instances that were created
        outside of CML Cloud Manager (e.g., via AWS Console, Terraform, etc.)

        You can specify either:
        - aws_instance_id: Direct lookup by instance ID
        - ami_id: Search for instances using that AMI
        - ami_name: Search for instances with matching AMI name

        The 'name' field is optional - if not provided, the AWS instance's
        name will be used automatically.

        (**Requires `admin` role!**)"""
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
    async def terminate_cml_worker(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(require_roles("lablets-admin")),
    ) -> Any:
        """Terminates a CML Worker instance from AWS EC2.

        (**Requires `lablets-admin` role!**)"""
        logger.info(f"Terminating CML worker {worker_id} in region {aws_region}")
        command = TerminateCMLWorkerCommand(worker_id=worker_id)
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
        token: str = Depends(require_roles("lablets-admin")),
    ) -> Any:
        """Starts a stopped CML Worker instance.

        (**Requires `lablets-admin` role!**)"""
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
        token: str = Depends(require_roles("lablets-admin")),
    ) -> Any:
        """Stops a running CML Worker instance.

        (**Requires `lablets-admin` role!**)"""
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
        token: str = Depends(require_roles("lablets-admin")),
    ) -> Any:
        """Updates tags for a CML Worker instance.

        (**Requires `lablets-admin` role!**)"""
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
        """Refreshes worker state from AWS and ensures monitoring is active.

        This endpoint:
        1. Dispatches RefreshWorkerMetricsCommand to collect latest AWS data
        2. Command handler updates worker aggregate (emitting domain events)
        3. Command handler updates OTEL metrics
        4. Starts monitoring if not already active (for running/pending workers)

        (**Requires valid token.**)"""
        logger.info(f"Refreshing CML worker {worker_id} in region {aws_region}")

        # Dispatch command to refresh metrics
        from application.commands import RefreshWorkerMetricsCommand

        command = RefreshWorkerMetricsCommand(worker_id=worker_id)
        refresh_result = await self.mediator.execute_async(command)

        # Check if refresh succeeded - return early if it failed
        if not refresh_result or not refresh_result.is_success:
            logger.error(f"Failed to refresh worker {worker_id}: {refresh_result}")
            return self.process(refresh_result)

        # Get the monitoring scheduler from main module
        from main import _monitoring_scheduler

        # If monitoring is enabled and scheduler exists, ensure worker is being monitored
        if _monitoring_scheduler:
            try:
                await _monitoring_scheduler.start_monitoring_worker_async(worker_id)
                logger.info(f"✅ Monitoring started/verified for worker {worker_id}")
            except Exception as e:
                logger.warning(
                    f"⚠️ Could not start monitoring for worker {worker_id}: {e}"
                )

        # Return the command result (which already includes the refreshed worker data)
        return self.process(refresh_result)

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

        from application.commands import EnableWorkerDetailedMonitoringCommand

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
        token: str = Depends(require_roles("lablets-admin")),
    ) -> Any:
        """Registers a license for a CML Worker instance.

        (**Requires `lablets-admin` role!**)"""
        logger.info(
            f"Registering license for CML worker {worker_id} in region {aws_region}"
        )
        # TODO: Implement RegisterCMLWorkerLicenseCommand when ready
        raise HTTPException(
            status_code=501, detail="License registration endpoint not yet implemented"
        )

    @get(
        "/region/{aws_region}/workers/{worker_id}/labs",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_worker_labs(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Get labs running on a CML Worker instance."""
        from application.queries.get_worker_labs_query import GetWorkerLabsQuery

        logger.info(
            f"Getting labs for CML worker {worker_id} in region {aws_region}"
        )

        query = GetWorkerLabsQuery(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(query))

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/refresh",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def refresh_worker_labs(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Refresh labs data from CML API for a specific worker.

        This endpoint:
        1. Fetches current lab data from CML API
        2. Updates lab_records in database with change detection
        3. Records state changes in operation history
        4. Returns summary of labs synced

        This is useful for on-demand lab refresh between the scheduled 30-minute
        global refresh cycles.

        (**Requires valid token.**)
        """
        logger.info(f"Refreshing labs for CML worker {worker_id} in region {aws_region}")

        from application.commands import RefreshWorkerLabsCommand

        command = RefreshWorkerLabsCommand(worker_id=worker_id)
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/{lab_id}/start",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def start_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        lab_id: str,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Start all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
        from application.commands import ControlLabCommand, LabAction

        logger.info(f"Starting lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(
            worker_id=worker_id, lab_id=lab_id, action=LabAction.START
        )
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/{lab_id}/stop",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def stop_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        lab_id: str,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Stop all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
        from application.commands import ControlLabCommand, LabAction

        logger.info(f"Stopping lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(
            worker_id=worker_id, lab_id=lab_id, action=LabAction.STOP
        )
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/{lab_id}/wipe",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def wipe_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        lab_id: str,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Wipe all nodes in a lab (factory reset).

        (**Requires `admin` or `manager` role!**)
        """
        from application.commands import ControlLabCommand, LabAction

        logger.info(f"Wiping lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(
            worker_id=worker_id, lab_id=lab_id, action=LabAction.WIPE
        )
        return self.process(await self.mediator.execute_async(command))
