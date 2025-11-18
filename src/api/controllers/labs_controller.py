import logging
from typing import Annotated, Any

from classy_fastapi.decorators import get, post
from fastapi import Depends, Path
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles
from application.commands import ControlLabCommand, RefreshWorkerLabsCommand
from application.commands.control_lab_command import LabAction
from application.queries import GetWorkerLabsQuery
from integration.enums import AwsRegion

logger = logging.getLogger(__name__)

aws_region_annotation = Annotated[
    AwsRegion,
    Path(
        description="The identifier of the AWS Region where the CML Worker instance is hosted."
    ),
]
worker_id_annotation = Annotated[str, Path(description="The CML Worker UUID.")]
lab_id_annotation = Annotated[str, Path(description="The Lab ID.")]


class LabsController(ControllerBase):
    def __init__(
        self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator
    ):
        """Handles lab management operations for CML Workers."""
        ControllerBase.__init__(self, service_provider, mapper, mediator)

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
        """Get labs running on a CML Worker instance.

        (**Requires valid token.**)"""
        logger.info(f"Getting labs for CML worker {worker_id} in region {aws_region}")
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
        logger.info(
            f"Refreshing labs for CML worker {worker_id} in region {aws_region}"
        )
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
        lab_id: lab_id_annotation,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Start all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
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
        lab_id: lab_id_annotation,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Stop all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
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
        lab_id: lab_id_annotation,
        token: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Wipe all nodes in a lab (factory reset).

        (**Requires `admin` or `manager` role!**)
        """
        logger.info(f"Wiping lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(
            worker_id=worker_id, lab_id=lab_id, action=LabAction.WIPE
        )
        return self.process(await self.mediator.execute_async(command))
