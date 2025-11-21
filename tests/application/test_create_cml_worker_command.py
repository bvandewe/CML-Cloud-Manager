from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator

from application.commands.create_cml_worker_command import CreateCMLWorkerCommand, CreateCMLWorkerCommandHandler
from application.events.domain.provision_cml_worker_event_handler import ProvisionCMLWorkerEventHandler
from application.settings import Settings
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.events.cml_worker import CMLWorkerCreatedDomainEvent
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.models import CMLWorkerInstanceDto
from integration.services.aws_ec2_api_client import AwsEc2Client


@pytest.fixture
def mock_mediator():
    return AsyncMock(spec=Mediator)


@pytest.fixture
def mock_mapper():
    return MagicMock(spec=Mapper)


@pytest.fixture
def mock_cloud_event_bus():
    return AsyncMock(spec=CloudEventBus)


@pytest.fixture
def mock_cloud_event_publishing_options():
    return MagicMock(spec=CloudEventPublishingOptions)


@pytest.fixture
def mock_repository():
    repo = AsyncMock(spec=CMLWorkerRepository)
    repo.add_async = AsyncMock()
    repo.get_by_id_async = AsyncMock()
    repo.update_async = AsyncMock()
    return repo


@pytest.fixture
def mock_aws_client():
    client = AsyncMock(spec=AwsEc2Client)
    client.get_ami_details = AsyncMock(return_value=None)
    client.create_instance = AsyncMock()
    return client


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.cml_worker_ami_ids = {"us-east-1": "ami-123"}
    settings.cml_worker_ami_names = {"us-east-1": "Test AMI"}
    settings.cml_worker_security_group_ids = ["sg-1"]
    settings.cml_worker_subnet_id = "subnet-1"
    settings.cml_worker_key_name = "key-1"
    return settings


@pytest.mark.asyncio
class TestCreateCMLWorkerCommand:
    async def test_create_worker_command_success(
        self,
        mock_mediator,
        mock_mapper,
        mock_cloud_event_bus,
        mock_cloud_event_publishing_options,
        mock_repository,
        mock_aws_client,
        mock_settings,
    ):
        # Arrange
        handler = CreateCMLWorkerCommandHandler(
            mock_mediator,
            mock_mapper,
            mock_cloud_event_bus,
            mock_cloud_event_publishing_options,
            mock_repository,
            mock_aws_client,
            mock_settings,
        )

        command = CreateCMLWorkerCommand(
            name="test-worker",
            aws_region="us-east-1",
            instance_type="t3.medium",
            created_by="user",
        )

        # Mock repository add_async to return the worker
        async def add_side_effect(worker, token=None):
            # Set ID on state, don't overwrite .id() method
            worker.state.id = "worker-123"
            return worker

        mock_repository.add_async.side_effect = add_side_effect

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.status_code == 201
        assert result.data["id"] == "worker-123"
        assert result.data["status"] == "pending"

        # Verify repository called
        mock_repository.add_async.assert_called_once()

        # Verify AWS create_instance NOT called (moved to event handler)
        mock_aws_client.create_instance.assert_not_called()

        # Verify AMI details fetched
        mock_aws_client.get_ami_details.assert_called_once()


@pytest.mark.asyncio
class TestProvisionCMLWorkerEventHandler:
    async def test_provision_worker_success(
        self,
        mock_repository,
        mock_aws_client,
        mock_settings,
    ):
        # Arrange
        handler = ProvisionCMLWorkerEventHandler(
            mock_repository,
            mock_aws_client,
            mock_settings,
        )

        event = CMLWorkerCreatedDomainEvent(
            aggregate_id="worker-123",
            name="test-worker",
            aws_region="us-east-1",
            aws_instance_id=None,
            instance_type="t3.medium",
            ami_id="ami-123",
            ami_name="Test AMI",
            ami_description=None,
            ami_creation_date=None,
            status=CMLWorkerStatus.PENDING,
            cml_version=None,
            created_at=datetime.now(timezone.utc),
            created_by="user",
        )

        # Mock AWS response
        instance_dto = CMLWorkerInstanceDto(
            id="dto-1",
            aws_instance_id="i-1234567890abcdef0",
            aws_region=AwsRegion.US_EAST_1,
            instance_name="test-worker",
            ami_id="ami-123",
            ami_name="Test AMI",
            instance_type="t3.medium",
            security_group_ids=["sg-1"],
            subnet_id="subnet-1",
            instance_state="running",
            public_ip="1.2.3.4",
            private_ip="10.0.0.1",
        )
        mock_aws_client.create_instance.return_value = instance_dto

        # Mock repository get_by_id
        worker = MagicMock(spec=CMLWorker)
        worker.id.return_value = "worker-123"
        worker.state = MagicMock()
        worker.state.aws_instance_id = None
        worker.state.status = CMLWorkerStatus.PENDING
        mock_repository.get_by_id_async.return_value = worker

        # Act
        await handler.handle_async(event)

        # Assert
        # Verify AWS called
        mock_aws_client.create_instance.assert_called_once()

        # Verify worker updated
        mock_repository.update_async.assert_called_once()
        worker.assign_instance.assert_called_once_with(
            aws_instance_id="i-1234567890abcdef0",
            public_ip="1.2.3.4",
            private_ip="10.0.0.1",
        )
        worker.update_status.assert_called_once_with(CMLWorkerStatus.RUNNING)

    async def test_provision_worker_failure(
        self,
        mock_repository,
        mock_aws_client,
        mock_settings,
    ):
        # Arrange
        handler = ProvisionCMLWorkerEventHandler(
            mock_repository,
            mock_aws_client,
            mock_settings,
        )

        event = CMLWorkerCreatedDomainEvent(
            aggregate_id="worker-123",
            name="test-worker",
            aws_region="us-east-1",
            aws_instance_id=None,
            instance_type="t3.medium",
            ami_id="ami-123",
            ami_name="Test AMI",
            ami_description=None,
            ami_creation_date=None,
            status=CMLWorkerStatus.PENDING,
            cml_version=None,
            created_at=datetime.now(timezone.utc),
            created_by="user",
        )

        # Mock AWS failure
        mock_aws_client.create_instance.side_effect = Exception("AWS Error")

        # Mock repository get_by_id
        worker = MagicMock(spec=CMLWorker)
        worker.id.return_value = "worker-123"
        mock_repository.get_by_id_async.return_value = worker

        # Act
        await handler.handle_async(event)

        # Assert
        # Verify AWS called
        mock_aws_client.create_instance.assert_called_once()

        # Verify worker updated to FAILED
        mock_repository.update_async.assert_called_once()
        worker.update_status.assert_called_once_with(CMLWorkerStatus.FAILED)
