import logging
from typing import Annotated, Any

from classy_fastapi.decorators import get, post
from fastapi import Depends, File, HTTPException, Path, UploadFile
from fastapi.responses import PlainTextResponse
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user
from application.commands import (ControlLabCommand, DeleteLabCommand,
                                  DownloadLabCommand, ImportLabCommand, LabAction,
                                  RefreshWorkerLabsCommand)
from application.queries import GetWorkerLabsQuery
from integration.enums import AwsRegion

logger = logging.getLogger(__name__)

aws_region_annotation = Annotated[
    AwsRegion,
    Path(description="The identifier of the AWS Region where the CML Worker instance is hosted."),
]
worker_id_annotation = Annotated[str, Path(description="The CML Worker UUID.")]
lab_id_annotation = Annotated[str, Path(description="The Lab ID.")]


class LabsController(ControllerBase):
    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
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
        logger.info(f"Refreshing labs for CML worker {worker_id} in region {aws_region}")
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
        token: str = Depends(get_current_user),
    ) -> Any:
        """Start all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
        logger.info(f"Starting lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(worker_id=worker_id, lab_id=lab_id, action=LabAction.START)
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
        token: str = Depends(get_current_user),
    ) -> Any:
        """Stop all nodes in a lab.

        (**Requires `admin` or `manager` role!**)
        """
        logger.info(f"Stopping lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(worker_id=worker_id, lab_id=lab_id, action=LabAction.STOP)
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
        token: str = Depends(get_current_user),
    ) -> Any:
        """Wipe all nodes in a lab (factory reset).

        (**Requires `admin` or `manager` role!**)
        """
        logger.info(f"Wiping lab {lab_id} on worker {worker_id}")
        command = ControlLabCommand(worker_id=worker_id, lab_id=lab_id, action=LabAction.WIPE)
        return self.process(await self.mediator.execute_async(command))

    @get(
        "/region/{aws_region}/workers/{worker_id}/labs/{lab_id}/download",
        response_class=PlainTextResponse,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def download_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        lab_id: lab_id_annotation,
        token: str = Depends(get_current_user),
    ) -> PlainTextResponse:
        """Download lab topology as YAML.

        Returns the lab topology in YAML format suitable for import/backup.

        (**Requires valid token.**)
        """
        logger.info(f"Downloading lab {lab_id} from worker {worker_id}")
        command = DownloadLabCommand(worker_id=worker_id, lab_id=lab_id)
        result = await self.mediator.execute_async(command)

        if not result.is_success:
            return self.process(result)

        return PlainTextResponse(content=result.data, media_type="text/yaml")

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/import",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def import_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        file: UploadFile = File(..., description="Lab YAML file to import"),
        token: str = Depends(get_current_user),
    ) -> Any:
        """Import a lab topology from uploaded YAML file.

        Uploads a CML2 YAML topology file and creates a new lab on the worker.
        The lab title will be taken from the YAML file unless overridden.

        (**Requires valid token.**)
        """
        logger.info(f"Importing lab to worker {worker_id} from file {file.filename}")

        # Read file content
        try:
            yaml_content = await file.read()
            yaml_str = yaml_content.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to read uploaded file: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

        # Execute import command
        command = ImportLabCommand(worker_id=worker_id, yaml_content=yaml_str)
        return self.process(await self.mediator.execute_async(command))

    @post(
        "/region/{aws_region}/workers/{worker_id}/labs/{lab_id}/delete",
        response_model=Any,
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def delete_lab(
        self,
        aws_region: aws_region_annotation,
        worker_id: worker_id_annotation,
        lab_id: lab_id_annotation,
        token: str = Depends(get_current_user),
    ) -> Any:
        """Delete a lab from the worker.

        Permanently deletes the specified lab and all its resources.
        This action cannot be undone.

        (**Requires valid token.**)
        """
        logger.info(f"Deleting lab {lab_id} from worker {worker_id}")
        command = DeleteLabCommand(worker_id=worker_id, lab_id=lab_id)
        return self.process(await self.mediator.execute_async(command))
