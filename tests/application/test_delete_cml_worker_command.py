"""Tests for delete CML Worker command."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator

from application.commands.delete_cml_worker_command import (
    DeleteCMLWorkerCommand,
    DeleteCMLWorkerCommandHandler,
)
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.exceptions import (
    EC2InstanceNotFoundException,
    EC2InstanceOperationException,
)
from integration.services.aws_ec2_api_client import AwsEc2Client


@pytest.fixture
def mock_repository():
    """Create a mock CML Worker repository."""
    repo = AsyncMock(spec=CMLWorkerRepository)
    return repo


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS EC2 client."""
    client = MagicMock(spec=AwsEc2Client)
    return client


@pytest.fixture
def mock_mediator():
    """Create a mock mediator."""
    return MagicMock(spec=Mediator)


@pytest.fixture
def mock_mapper():
    """Create a mock mapper."""
    return MagicMock(spec=Mapper)


@pytest.fixture
def mock_cloud_event_bus():
    """Create a mock cloud event bus."""
    return MagicMock(spec=CloudEventBus)


@pytest.fixture
def mock_cloud_event_options():
    """Create mock cloud event publishing options."""
    options = MagicMock(spec=CloudEventPublishingOptions)
    options.source = "test-source"
    options.type_prefix = "test.prefix"
    return options


@pytest.fixture
def command_handler(
    mock_mediator,
    mock_mapper,
    mock_cloud_event_bus,
    mock_cloud_event_options,
    mock_repository,
    mock_aws_client,
):
    """Create a DeleteCMLWorkerCommandHandler instance."""
    return DeleteCMLWorkerCommandHandler(
        mediator=mock_mediator,
        mapper=mock_mapper,
        cloud_event_bus=mock_cloud_event_bus,
        cloud_event_publishing_options=mock_cloud_event_options,
        cml_worker_repository=mock_repository,
        aws_ec2_client=mock_aws_client,
    )


@pytest.fixture
def sample_worker():
    """Create a sample CML Worker."""
    worker = CMLWorker(
        name="test-worker",
        aws_region=AwsRegion.US_EAST_1.value,
        instance_type="c5.xlarge",
        ami_id="ami-12345",
        created_by="test-user",
    )
    # Simulate assigned instance
    worker.state.aws_instance_id = "i-1234567890abcdef0"
    worker.state.status = CMLWorkerStatus.RUNNING
    return worker


@pytest.mark.asyncio
@pytest.mark.command
class TestDeleteCMLWorkerCommand:
    """Tests for DeleteCMLWorkerCommand."""

    async def test_delete_worker_without_terminating_instance(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test deleting worker without terminating EC2 instance."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=False,
            deleted_by="test-admin",
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        mock_repository.get_by_id_async.assert_called_once_with(sample_worker.id())
        # AWS client should not be called when terminate_instance=False
        mock_aws_client.terminate_instance.assert_not_called()
        # Repository delete should be called with worker for event publishing
        mock_repository.delete_async.assert_called_once()
        call_args = mock_repository.delete_async.call_args
        assert call_args[0][0] == sample_worker.id()
        assert call_args[0][1] == sample_worker

    async def test_delete_worker_with_terminating_instance(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test deleting worker and terminating EC2 instance."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True
        mock_aws_client.terminate_instance.return_value = True

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=True,
            deleted_by="test-admin",
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        mock_aws_client.terminate_instance.assert_called_once_with(
            aws_region=AwsRegion.US_EAST_1,
            instance_id=sample_worker.state.aws_instance_id,
        )
        mock_repository.delete_async.assert_called_once()

    async def test_delete_worker_not_found(self, command_handler, mock_repository):
        """Test deleting non-existent worker returns error."""
        # Arrange
        mock_repository.get_by_id_async.return_value = None
        command = DeleteCMLWorkerCommand(worker_id="nonexistent-id")

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 400
        assert "not found" in result.detail.lower()
        mock_repository.delete_async.assert_not_called()

    async def test_delete_worker_instance_not_found_continues(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test deletion continues if EC2 instance not found."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True
        mock_aws_client.terminate_instance.side_effect = EC2InstanceNotFoundException(
            "Instance not found"
        )

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=True,
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        # Should still delete from database even if instance not found
        mock_repository.delete_async.assert_called_once()

    async def test_delete_worker_terminate_fails_stops_deletion(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test deletion stops if EC2 termination fails."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_aws_client.terminate_instance.side_effect = EC2InstanceOperationException(
            "Termination failed"
        )

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=True,
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 400
        assert "failed to terminate" in result.detail.lower()
        # Should NOT delete from database if termination fails
        mock_repository.delete_async.assert_not_called()

    async def test_delete_worker_without_instance_id(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test deleting worker that has no instance ID."""
        # Arrange
        sample_worker.state.aws_instance_id = None
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=True,  # Request termination but no instance exists
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        # AWS client should not be called if no instance ID
        mock_aws_client.terminate_instance.assert_not_called()
        mock_repository.delete_async.assert_called_once()

    async def test_delete_worker_marks_as_terminated(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test that worker is marked as terminated before deletion."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True

        initial_status = sample_worker.state.status
        assert initial_status != CMLWorkerStatus.TERMINATED

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=False,
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        # Worker should be marked as terminated
        assert sample_worker.state.status == CMLWorkerStatus.TERMINATED

    async def test_delete_already_terminated_worker(
        self, command_handler, mock_repository, sample_worker
    ):
        """Test deleting a worker that's already terminated."""
        # Arrange
        sample_worker.state.status = CMLWorkerStatus.TERMINATED
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = True

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=False,
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 200
        mock_repository.delete_async.assert_called_once()

    async def test_delete_worker_database_deletion_fails(
        self, command_handler, mock_repository, mock_aws_client, sample_worker
    ):
        """Test handling of database deletion failure."""
        # Arrange
        mock_repository.get_by_id_async.return_value = sample_worker
        mock_repository.delete_async.return_value = False  # Deletion failed

        command = DeleteCMLWorkerCommand(
            worker_id=sample_worker.id(),
            terminate_instance=False,
        )

        # Act
        result = await command_handler.handle_async(command)

        # Assert
        assert result.status_code == 400
        assert "failed to delete" in result.detail.lower()
