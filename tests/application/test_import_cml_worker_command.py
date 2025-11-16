"""Unit tests for ImportCMLWorkerCommand and handler."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from application.commands.import_cml_worker_command import (
    ImportCMLWorkerCommand,
    ImportCMLWorkerCommandHandler,
)
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from integration.services.aws_ec2_api_client import Ec2InstanceDescriptor


@pytest.fixture
def mock_dependencies() -> dict:
    """Create mock dependencies for the command handler."""
    return {
        "mediator": Mock(),
        "mapper": Mock(),
        "cloud_event_bus": Mock(),
        "cloud_event_publishing_options": Mock(),
        "cml_worker_repository": Mock(),
        "aws_ec2_client": Mock(),
        "settings": Mock(),
    }


@pytest.fixture
def sample_instance_descriptor() -> Ec2InstanceDescriptor:
    """Sample EC2 instance descriptor for testing."""
    return Ec2InstanceDescriptor(
        id="i-0abcdef1234567890",
        type="c5.2xlarge",
        state="running",
        image_id="ami-0c55b159cbfafe1f0",
        name="test-cml-instance",
        launch_timestamp=datetime.now(timezone.utc),
        launch_time_relative="2 hours ago",
    )


class TestImportCMLWorkerCommand:
    """Tests for ImportCMLWorkerCommand."""

    def test_command_creation_with_instance_id(self):
        """Test creating command with instance ID."""
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            aws_instance_id="i-0abcdef1234567890",
            name="imported-worker-01",
        )

        assert command.aws_region == "us-east-1"
        assert command.aws_instance_id == "i-0abcdef1234567890"
        assert command.name == "imported-worker-01"
        assert command.ami_id is None
        assert command.ami_name is None

    def test_command_creation_with_ami_id(self):
        """Test creating command with AMI ID."""
        command = ImportCMLWorkerCommand(
            aws_region="us-west-2",
            ami_id="ami-0c55b159cbfafe1f0",
            name="imported-worker-02",
        )

        assert command.aws_region == "us-west-2"
        assert command.ami_id == "ami-0c55b159cbfafe1f0"
        assert command.aws_instance_id is None

    def test_command_creation_with_ami_name(self):
        """Test creating command with AMI name."""
        command = ImportCMLWorkerCommand(
            aws_region="eu-west-1",
            ami_name="cml-worker-ami-2.7.0",
            name="imported-worker-03",
        )

        assert command.aws_region == "eu-west-1"
        assert command.ami_name == "cml-worker-ami-2.7.0"
        assert command.aws_instance_id is None


class TestImportCMLWorkerCommandHandler:
    """Tests for ImportCMLWorkerCommandHandler."""

    @pytest.mark.asyncio
    async def test_import_by_instance_id_success(
        self, mock_dependencies, sample_instance_descriptor
    ):
        """Test successful import by instance ID."""
        # Arrange
        handler = ImportCMLWorkerCommandHandler(**mock_dependencies)
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            aws_instance_id="i-0abcdef1234567890",
            name="imported-worker",
            created_by="test-user",
        )

        # Mock AWS client to return instance
        mock_dependencies["aws_ec2_client"].get_instance_details.return_value = (
            sample_instance_descriptor
        )

        # Mock repository to return no existing worker
        mock_dependencies["cml_worker_repository"].get_by_aws_instance_id_async = (
            AsyncMock(return_value=None)
        )

        # Mock repository add
        mock_worker = Mock()
        mock_worker.id.return_value = "test-worker-id"
        mock_dependencies["cml_worker_repository"].add_async = AsyncMock(
            return_value=mock_worker
        )

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.succeeded
        assert result.data is not None
        assert result.data.aws_instance_id == "i-0abcdef1234567890"
        assert result.data.instance_name == "imported-worker"

        # Verify AWS client was called with correct parameters
        mock_dependencies["aws_ec2_client"].get_instance_details.assert_called_once()
        call_args = mock_dependencies["aws_ec2_client"].get_instance_details.call_args
        assert call_args[1]["instance_id"] == "i-0abcdef1234567890"

        # Verify repository methods called
        mock_dependencies[
            "cml_worker_repository"
        ].get_by_aws_instance_id_async.assert_called_once_with("i-0abcdef1234567890")
        mock_dependencies["cml_worker_repository"].add_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_fails_when_no_search_criteria(self, mock_dependencies):
        """Test import fails when no search criteria provided."""
        # Arrange
        handler = ImportCMLWorkerCommandHandler(**mock_dependencies)
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            aws_instance_id=None,
            ami_id=None,
            ami_name=None,
        )

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert not result.succeeded
        assert "at least one of" in result.errors[0].message.lower()

    @pytest.mark.asyncio
    async def test_import_fails_when_instance_not_found(self, mock_dependencies):
        """Test import fails when instance doesn't exist in AWS."""
        # Arrange
        handler = ImportCMLWorkerCommandHandler(**mock_dependencies)
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            aws_instance_id="i-nonexistent",
        )

        # Mock AWS client to return None
        mock_dependencies["aws_ec2_client"].get_instance_details.return_value = None

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert not result.succeeded
        assert "no matching ec2 instance" in result.errors[0].message.lower()

    @pytest.mark.asyncio
    async def test_import_fails_when_instance_already_registered(
        self, mock_dependencies, sample_instance_descriptor
    ):
        """Test import fails when instance is already registered."""
        # Arrange
        handler = ImportCMLWorkerCommandHandler(**mock_dependencies)
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            aws_instance_id="i-0abcdef1234567890",
        )

        # Mock AWS client to return instance
        mock_dependencies["aws_ec2_client"].get_instance_details.return_value = (
            sample_instance_descriptor
        )

        # Mock repository to return existing worker
        existing_worker = Mock()
        existing_worker.id.return_value = "existing-worker-id"
        mock_dependencies["cml_worker_repository"].get_by_aws_instance_id_async = (
            AsyncMock(return_value=existing_worker)
        )

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert not result.succeeded
        assert "already registered" in result.errors[0].message.lower()

    @pytest.mark.asyncio
    async def test_import_by_ami_id_success(
        self, mock_dependencies, sample_instance_descriptor
    ):
        """Test successful import by AMI ID."""
        # Arrange
        handler = ImportCMLWorkerCommandHandler(**mock_dependencies)
        command = ImportCMLWorkerCommand(
            aws_region="us-east-1",
            ami_id="ami-0c55b159cbfafe1f0",
            name="imported-from-ami",
        )

        # Mock AWS client to return list of instances
        mock_dependencies["aws_ec2_client"].list_instances.return_value = [
            sample_instance_descriptor
        ]

        # Mock repository to return no existing worker
        mock_dependencies["cml_worker_repository"].get_by_aws_instance_id_async = (
            AsyncMock(return_value=None)
        )

        # Mock repository add
        mock_worker = Mock()
        mock_worker.id.return_value = "test-worker-id"
        mock_dependencies["cml_worker_repository"].add_async = AsyncMock(
            return_value=mock_worker
        )

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.succeeded
        assert result.data is not None
        assert result.data.ami_id == "ami-0c55b159cbfafe1f0"

        # Verify AWS client was called with correct filters
        mock_dependencies["aws_ec2_client"].list_instances.assert_called_once()
        call_args = mock_dependencies["aws_ec2_client"].list_instances.call_args
        assert "image_ids" in call_args[1]
        assert "ami-0c55b159cbfafe1f0" in call_args[1]["image_ids"]


class TestCMLWorkerImportFromExisting:
    """Tests for CMLWorker.import_from_existing_instance factory method."""

    def test_import_creates_worker_with_correct_state(self):
        """Test import factory method creates worker with correct state."""
        # Act
        worker = CMLWorker.import_from_existing_instance(
            name="imported-worker",
            aws_region="us-east-1",
            aws_instance_id="i-0abcdef1234567890",
            instance_type="c5.2xlarge",
            ami_id="ami-0c55b159cbfafe1f0",
            instance_state="running",
            created_by="test-user",
            ami_name="cml-worker-ami",
            public_ip="54.123.45.67",
            private_ip="10.0.1.100",
        )

        # Assert
        assert worker.state.name == "imported-worker"
        assert worker.state.aws_region == "us-east-1"
        assert worker.state.aws_instance_id == "i-0abcdef1234567890"
        assert worker.state.instance_type == "c5.2xlarge"
        assert worker.state.ami_id == "ami-0c55b159cbfafe1f0"
        assert worker.state.ami_name == "cml-worker-ami"
        assert worker.state.public_ip == "54.123.45.67"
        assert worker.state.private_ip == "10.0.1.100"
        assert worker.state.created_by == "test-user"
        assert worker.state.status == CMLWorkerStatus.RUNNING

    def test_import_maps_instance_states_correctly(self):
        """Test import correctly maps EC2 instance states to worker status."""
        # Test running state
        worker_running = CMLWorker.import_from_existing_instance(
            name="test",
            aws_region="us-east-1",
            aws_instance_id="i-123",
            instance_type="c5.2xlarge",
            ami_id="ami-123",
            instance_state="running",
        )
        assert worker_running.state.status == CMLWorkerStatus.RUNNING

        # Test stopped state
        worker_stopped = CMLWorker.import_from_existing_instance(
            name="test",
            aws_region="us-east-1",
            aws_instance_id="i-456",
            instance_type="c5.2xlarge",
            ami_id="ami-123",
            instance_state="stopped",
        )
        assert worker_stopped.state.status == CMLWorkerStatus.STOPPED

        # Test pending state
        worker_pending = CMLWorker.import_from_existing_instance(
            name="test",
            aws_region="us-east-1",
            aws_instance_id="i-789",
            instance_type="c5.2xlarge",
            ami_id="ami-123",
            instance_state="pending",
        )
        assert worker_pending.state.status == CMLWorkerStatus.PENDING

        # Test stopping state
        worker_stopping = CMLWorker.import_from_existing_instance(
            name="test",
            aws_region="us-east-1",
            aws_instance_id="i-abc",
            instance_type="c5.2xlarge",
            ami_id="ami-123",
            instance_state="stopping",
        )
        assert worker_stopping.state.status == CMLWorkerStatus.STOPPING

        # Test unknown state
        worker_unknown = CMLWorker.import_from_existing_instance(
            name="test",
            aws_region="us-east-1",
            aws_instance_id="i-xyz",
            instance_type="c5.2xlarge",
            ami_id="ami-123",
            instance_state="shutting-down",
        )
        assert worker_unknown.state.status == CMLWorkerStatus.UNKNOWN
