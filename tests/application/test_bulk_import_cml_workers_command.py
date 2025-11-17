"""Tests for bulk import CML Workers command."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.commands.bulk_import_cml_workers_command import (
    BulkImportCMLWorkersCommand,
    BulkImportCMLWorkersCommandHandler,
    BulkImportResult,
)
from integration.services.aws_ec2_api_client import AmiDetails, Ec2InstanceDescriptor
from tests.fixtures.factories import CMLWorkerFactory


@pytest.mark.asyncio
class TestBulkImportCMLWorkersCommand:
    """Test suite for bulk import CML Workers command."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for the command handler."""
        mediator = MagicMock()
        mapper = MagicMock()
        cloud_event_bus = MagicMock()
        cloud_event_publishing_options = MagicMock()
        cml_worker_repository = AsyncMock()
        aws_ec2_client = MagicMock()
        settings = MagicMock()

        return {
            "mediator": mediator,
            "mapper": mapper,
            "cloud_event_bus": cloud_event_bus,
            "cloud_event_publishing_options": cloud_event_publishing_options,
            "cml_worker_repository": cml_worker_repository,
            "aws_ec2_client": aws_ec2_client,
            "settings": settings,
        }

    def create_handler(self, mock_dependencies):
        """Create command handler with mocked dependencies."""
        return BulkImportCMLWorkersCommandHandler(
            mediator=mock_dependencies["mediator"],
            mapper=mock_dependencies["mapper"],
            cloud_event_bus=mock_dependencies["cloud_event_bus"],
            cloud_event_publishing_options=mock_dependencies[
                "cloud_event_publishing_options"
            ],
            cml_worker_repository=mock_dependencies["cml_worker_repository"],
            aws_ec2_client=mock_dependencies["aws_ec2_client"],
            settings=mock_dependencies["settings"],
        )

    def create_mock_instance_descriptor(
        self, instance_id: str, name: str = None
    ) -> Ec2InstanceDescriptor:
        """Create a mock EC2 instance descriptor."""
        import datetime

        return Ec2InstanceDescriptor(
            id=instance_id,
            type="m5.xlarge",
            state="running",
            image_id="ami-0abc123def456",
            name=name or f"instance-{instance_id}",
            launch_timestamp=datetime.datetime.now(),
            launch_time_relative="2 hours ago",
            public_ip="1.2.3.4",
            private_ip="10.0.1.10",
        )

    async def test_bulk_import_all_new_instances(self, mock_dependencies):
        """Test bulk import when all instances are new (not registered)."""
        handler = self.create_handler(mock_dependencies)

        # Mock AWS client to return 3 instances
        mock_instances = [
            self.create_mock_instance_descriptor("i-001", "worker-01"),
            self.create_mock_instance_descriptor("i-002", "worker-02"),
            self.create_mock_instance_descriptor("i-003", "worker-03"),
        ]
        mock_dependencies["aws_ec2_client"].get_ami_ids_by_name.return_value = [
            "ami-0abc123def456"
        ]
        mock_dependencies["aws_ec2_client"].list_instances.return_value = mock_instances
        mock_dependencies["aws_ec2_client"].get_ami_details.return_value = AmiDetails(
            ami_id="ami-0abc123def456",
            ami_name="test-ami",
            ami_description="Test AMI",
            ami_creation_date="2024-01-01T00:00:00.000Z",
        )

        # Mock repository to return no existing workers
        mock_dependencies["cml_worker_repository"].get_all_async.return_value = []

        # Mock repository add_async to return saved workers
        async def mock_add_async(worker):
            return worker

        mock_dependencies["cml_worker_repository"].add_async.side_effect = (
            mock_add_async
        )

        # Execute command
        command = BulkImportCMLWorkersCommand(
            aws_region="us-west-2", ami_name="test-ami", created_by="test-user"
        )

        result = await handler.handle_async(command)

        # Verify success
        assert result.is_successful
        assert isinstance(result.value, BulkImportResult)
        assert result.value.total_found == 3
        assert result.value.total_imported == 3
        assert result.value.total_skipped == 0
        assert len(result.value.imported) == 3
        assert len(result.value.skipped) == 0

        # Verify repository was called 3 times
        assert mock_dependencies["cml_worker_repository"].add_async.call_count == 3

    async def test_bulk_import_skip_existing_instances(self, mock_dependencies):
        """Test bulk import skips instances that are already registered."""
        handler = self.create_handler(mock_dependencies)

        # Mock AWS client to return 3 instances
        mock_instances = [
            self.create_mock_instance_descriptor("i-001", "worker-01"),
            self.create_mock_instance_descriptor("i-002", "worker-02"),
            self.create_mock_instance_descriptor("i-003", "worker-03"),
        ]
        mock_dependencies["aws_ec2_client"].get_ami_ids_by_name.return_value = [
            "ami-0abc123def456"
        ]
        mock_dependencies["aws_ec2_client"].list_instances.return_value = mock_instances
        mock_dependencies["aws_ec2_client"].get_ami_details.return_value = AmiDetails(
            ami_id="ami-0abc123def456",
            ami_name="test-ami",
            ami_description="Test AMI",
            ami_creation_date="2024-01-01T00:00:00.000Z",
        )

        # Mock repository to return 1 existing worker (i-002)
        existing_worker = CMLWorkerFactory.import_from_existing(
            name="worker-02",
            aws_region="us-west-2",
            aws_instance_id="i-002",
            instance_type="m5.xlarge",
            ami_id="ami-0abc123def456",
            instance_state="running",
        )
        mock_dependencies["cml_worker_repository"].get_all_async.return_value = [
            existing_worker
        ]

        # Mock repository add_async
        async def mock_add_async(worker):
            return worker

        mock_dependencies["cml_worker_repository"].add_async.side_effect = (
            mock_add_async
        )

        # Execute command
        command = BulkImportCMLWorkersCommand(
            aws_region="us-west-2", ami_name="test-ami", created_by="test-user"
        )

        result = await handler.handle_async(command)

        # Verify success
        assert result.is_successful
        assert isinstance(result.value, BulkImportResult)
        assert result.value.total_found == 3
        assert result.value.total_imported == 2
        assert result.value.total_skipped == 1
        assert len(result.value.imported) == 2
        assert len(result.value.skipped) == 1
        assert result.value.skipped[0]["instance_id"] == "i-002"
        assert "Already registered" in result.value.skipped[0]["reason"]

        # Verify repository was called only 2 times (skipped i-002)
        assert mock_dependencies["cml_worker_repository"].add_async.call_count == 2

    async def test_bulk_import_no_instances_found(self, mock_dependencies):
        """Test bulk import when no instances match criteria."""
        handler = self.create_handler(mock_dependencies)

        # Mock AWS client to return empty list
        mock_dependencies["aws_ec2_client"].get_ami_ids_by_name.return_value = [
            "ami-0abc123def456"
        ]
        mock_dependencies["aws_ec2_client"].list_instances.return_value = []

        # Execute command
        command = BulkImportCMLWorkersCommand(
            aws_region="us-west-2", ami_name="test-ami", created_by="test-user"
        )

        result = await handler.handle_async(command)

        # Verify success with empty result
        assert result.is_successful
        assert isinstance(result.value, BulkImportResult)
        assert result.value.total_found == 0
        assert result.value.total_imported == 0
        assert result.value.total_skipped == 0

        # Verify repository was never called
        assert mock_dependencies["cml_worker_repository"].add_async.call_count == 0

    async def test_bulk_import_requires_ami_criteria(self, mock_dependencies):
        """Test bulk import fails without AMI search criteria."""
        handler = self.create_handler(mock_dependencies)

        # Execute command without ami_id or ami_name
        command = BulkImportCMLWorkersCommand(
            aws_region="us-west-2", created_by="test-user"
        )

        result = await handler.handle_async(command)

        # Verify failure
        assert not result.is_successful
        assert "Must provide at least one of: ami_id or ami_name" in result.reason
