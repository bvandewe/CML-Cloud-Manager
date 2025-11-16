import logging
from typing import Annotated, Any, List

from classy_fastapi.decorators import delete, get, post
from fastapi import Depends, Path
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.controllers.oauth2_scheme import has_role, validate_token
from application.commands import CreateNewIolVmCommand, TerminateIolVmCommand
from application.queries import (GetIolVmInstanceDetailsQuery,
                                 IolVmInstanceResourcesUtilizationQuery,
                                 ListIolVmInstancesQuery)
from domain.models import IolVmInstanceId
from integration.enums import (AwsRegion,
                               Ec2InstanceResourcesUtilizationRelativeStartTime,
                               LabletType)
from integration.models import CreateNewIolVmCommandDto
from integration.services.aws_ec2_api_client import (Ec2InstanceDescriptor,
                                                     Ec2InstanceResourcesUtilization)

log = logging.getLogger(__name__)

lablet_type_annotation = Annotated[LabletType, Path(description="The type of the Lablet.")]
aws_region_annotation = Annotated[AwsRegion, Path(description="The identifier of the AWS Region where the CML VM instance is hosted.")]
instance_id_annotation = Annotated[str, Path(description="The AWS identifier of the CML VM instance.", example="i-abcdef12345abcdef", min_length=19, max_length=19, pattern=r"^i-[a-z0-9]{17}$")]


class WorkersController(ControllerBase):
    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
        """Runs API Calls to AWS EC2."""
        ControllerBase.__init__(self, service_provider, mapper, mediator)

    @get("/region/{aws_region}/lablet_type/{lablet_type}", response_model=List[Ec2InstanceDescriptor], response_description="List of Ec2InstanceDescriptor(s)", status_code=200, responses=ControllerBase.error_responses)
    async def list_running_cml_workers(self, aws_region: aws_region_annotation, lablet_type: lablet_type_annotation, token: str = Depends(validate_token)) -> Any:
        """Queries AWS EC2 for all currently running CML Worker instances.

        (**Requires valid token.**)"""
        return self.process(await self.mediator.execute_async(ListIolVmInstancesQuery(aws_region=aws_region, lablet_type=lablet_type)))

    @get("/region/{aws_region}/instance/{instance_id}", response_model=List[Ec2InstanceDescriptor], status_code=200, responses=ControllerBase.error_responses)
    async def get_instance_details(self, aws_region: aws_region_annotation, instance_id: instance_id_annotation, token: str = Depends(validate_token)) -> Any:
        """Queries AWS EC2 for CML Worker instance details.

        (**Requires valid token.**)"""
        return self.process(await self.mediator.execute_async(GetIolVmInstanceDetailsQuery(aws_region=aws_region, instance_id=IolVmInstanceId(id=instance_id))))

    @post("/region/{aws_region}", response_model=Any, status_code=201, responses=ControllerBase.error_responses)
    async def create_new_cml_worker(self, aws_region: aws_region_annotation, command_dto: CreateNewIolVmCommandDto, token: str = Depends(has_role(role="lablets-admin"))) -> Any:
        """Creates a new CML Worker instance in AWS EC2.

        (**Requires `lablets-admin` role!**)"""
        return self.process(await self.mediator.execute_async(CreateNewIolVmCommand(aws_region=aws_region, instance_type=command_dto.iolvm_instance_type, registration_id=command_dto.registration_id, item_id=command_dto.item_id, instance_name=command_dto.iolvm_instance_name)))

    # TODO: Fix response_model
    @delete("/region/{aws_region}/instance/{instance_id}", response_model=Any, status_code=200, responses=ControllerBase.error_responses)
    async def terminate_cml_worker(self, aws_region: aws_region_annotation, instance_id: instance_id_annotation, token: str = Depends(has_role(role="lablets-admin"))) -> Any:
        """Terminates a CML Worker instance from AWS EC2.

        (**Requires `lablets-admin` role!**)"""
        return self.process(await self.mediator.execute_async(TerminateIolVmCommand(aws_region=aws_region, instance_id=IolVmInstanceId(id=instance_id))))

    @get("/region/{aws_region}/instance/{instance_id}/resources", response_model=Ec2InstanceResourcesUtilization, status_code=200, responses=ControllerBase.error_responses)
    async def pull_avg_cpu_and_memory_utilization(self, aws_region: aws_region_annotation, instance_id: instance_id_annotation, relative_start_time: Ec2InstanceResourcesUtilizationRelativeStartTime, token: str = Depends(validate_token)) -> Any:
        """Queries AWS CloudWatch for CML Worker instance resource utilization.

        (**Requires valid token.**)"""
        return self.process(await self.mediator.execute_async(IolVmInstanceResourcesUtilizationQuery(aws_region=aws_region, instance_id=IolVmInstanceId(id=instance_id), relative_start_time=relative_start_time)))
