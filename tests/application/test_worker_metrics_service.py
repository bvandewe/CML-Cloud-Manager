"""Tests for WorkerMetricsService."""

from unittest.mock import MagicMock

import pytest

from application.services.worker_metrics_service import (
    MetricsResult,
    WorkerMetricsService,
)
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from integration.enums import AwsRegion


@pytest.mark.asyncio
@pytest.mark.unit
class TestWorkerMetricsService:
    """Test suite for WorkerMetricsService."""

    @pytest.fixture
    def mock_aws_client(self):
        """Create mock AWS EC2 client."""
        client = MagicMock()
        client.get_instance_status_checks = MagicMock()
        client.get_instance_resources_utilization = MagicMock()
        return client

    @pytest.fixture
    def service(self, mock_aws_client):
        """Create WorkerMetricsService with mocked AWS client."""
        return WorkerMetricsService(mock_aws_client)

    @pytest.fixture
    def worker(self):
        """Create a test worker."""
        worker = CMLWorker(
            name="test-worker",
            aws_region=AwsRegion.US_EAST_1.value,
            instance_type="c5.xlarge",
            ami_id="ami-test123",
            created_by="test-user",
        )
        # Simulate assigned instance in running state
        worker.state.aws_instance_id = "i-test123"
        worker.state.status = CMLWorkerStatus.RUNNING
        return worker

    async def test_collect_metrics_without_cloudwatch(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics without CloudWatch data."""
        # Setup mock - instance is running
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "running",
            "instance_status_check": "ok",
            "ec2_system_status_check": "ok",
            "monitoring_state": "disabled",
        }

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify
        assert isinstance(result, MetricsResult)
        assert result.error is None
        assert result.ec2_state == "running"
        assert result.status_updated is False  # Already RUNNING
        assert result.cpu_utilization is None
        assert result.memory_utilization is None

        # Verify AWS client called
        mock_aws_client.get_instance_status_checks.assert_called_once_with(
            aws_region=AwsRegion.US_EAST_1,
            instance_id="i-test123",
        )
        mock_aws_client.get_instance_resources_utilization.assert_not_called()

    async def test_collect_metrics_with_cloudwatch(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics with CloudWatch data."""
        # Setup mocks
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "running",
            "instance_status_check": "ok",
            "ec2_system_status_check": "ok",
            "monitoring_state": "enabled",
        }

        # Mock CloudWatch metrics response
        from datetime import datetime

        from integration.enums import Ec2InstanceResourcesUtilizationRelativeStartTime
        from integration.services.aws_ec2_api_client import (
            Ec2InstanceResourcesUtilization,
        )

        mock_metrics = Ec2InstanceResourcesUtilization(
            id="i-test123",
            region_name=AwsRegion.US_EAST_1,
            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
            avg_cpu_utilization=45.5,
            avg_memory_utilization=62.3,
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        mock_aws_client.get_instance_resources_utilization.return_value = mock_metrics

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=True)

        # Verify
        assert result.error is None
        assert result.ec2_state == "running"
        assert result.cpu_utilization == 45.5
        assert result.memory_utilization == 62.3
        assert result.metrics_collected is True

        # Verify AWS client calls
        mock_aws_client.get_instance_status_checks.assert_called_once()
        mock_aws_client.get_instance_resources_utilization.assert_called_once()

    async def test_collect_metrics_stopped_instance(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics for stopped instance."""
        # Setup mock - instance is stopped
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "stopped",
            "instance_status_check": "not-applicable",
            "ec2_system_status_check": "not-applicable",
            "monitoring_state": "disabled",
        }

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify
        assert result.error is None
        assert result.ec2_state == "stopped"
        assert result.status_updated is True  # Changed from RUNNING to STOPPED
        assert result.cpu_utilization is None

        # Worker should be updated with STOPPED status
        assert worker.state.status == CMLWorkerStatus.STOPPED

    async def test_collect_metrics_instance_not_found(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics when instance not found."""
        # Setup mock - instance not found
        mock_aws_client.get_instance_status_checks.return_value = None

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify error is captured
        assert result.error is not None
        assert "not found" in result.error.lower()

    async def test_collect_metrics_cloudwatch_error(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics when CloudWatch fails but EC2 status succeeds."""
        # Setup mocks
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "running",
            "instance_status_check": "ok",
            "ec2_system_status_check": "ok",
            "monitoring_state": "enabled",
        }
        mock_aws_client.get_instance_resources_utilization.side_effect = Exception(
            "CloudWatch API error"
        )

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=True)

        # Verify - should still succeed with EC2 data, CloudWatch error logged
        assert result.error is None  # Not a critical error
        assert result.ec2_state == "running"
        assert result.cpu_utilization is None
        assert result.memory_utilization is None

    async def test_collect_metrics_updates_worker_state(
        self, service, worker, mock_aws_client
    ):
        """Test that metrics collection updates worker state correctly."""
        # Setup mocks
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "running",
            "instance_status_check": "ok",
            "ec2_system_status_check": "ok",
            "monitoring_state": "enabled",
        }

        from datetime import datetime

        from integration.enums import Ec2InstanceResourcesUtilizationRelativeStartTime
        from integration.services.aws_ec2_api_client import (
            Ec2InstanceResourcesUtilization,
        )

        mock_metrics = Ec2InstanceResourcesUtilization(
            id="i-test123",
            region_name=AwsRegion.US_EAST_1,
            relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.FIVE_MIN_AGO,
            avg_cpu_utilization=75.0,
            avg_memory_utilization=85.0,
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        mock_aws_client.get_instance_resources_utilization.return_value = mock_metrics

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=True)

        # Verify worker state was updated
        assert result.error is None
        assert worker.state.status == CMLWorkerStatus.RUNNING
        assert result.cpu_utilization == 75.0
        assert result.memory_utilization == 85.0

    async def test_collect_metrics_terminated_instance(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics for terminated instance."""
        # Setup mock - instance is terminated
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "terminated",
            "instance_status_check": "not-applicable",
            "ec2_system_status_check": "not-applicable",
            "monitoring_state": "disabled",
        }

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify
        assert result.error is None
        assert result.ec2_state == "terminated"
        assert result.status_updated is True

    async def test_collect_metrics_pending_instance(
        self, service, worker, mock_aws_client
    ):
        """Test collecting metrics for pending instance."""
        # Setup mock - instance is pending
        mock_aws_client.get_instance_status_checks.return_value = {
            "instance_state": "pending",
            "instance_status_check": "initializing",
            "ec2_system_status_check": "initializing",
            "monitoring_state": "disabled",
        }

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify
        assert result.error is None
        assert result.ec2_state == "pending"
        assert result.status_updated is True  # Changed from RUNNING to PENDING

    async def test_collect_metrics_worker_without_instance(
        self, service, mock_aws_client
    ):
        """Test collecting metrics for worker without AWS instance assigned."""
        # Create worker without instance ID
        worker = CMLWorker(
            name="test-worker-no-instance",
            aws_region=AwsRegion.US_EAST_1.value,
            instance_type="c5.xlarge",
            ami_id="ami-test123",
            created_by="test-user",
        )

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify
        assert result.error == "No AWS instance ID"
        assert result.ec2_state == "unknown"
        assert mock_aws_client.get_instance_status_checks.assert_not_called

    async def test_collect_metrics_terminated_worker_skipped(
        self, service, mock_aws_client
    ):
        """Test that terminated workers are skipped."""
        # Create terminated worker
        worker = CMLWorker(
            name="test-worker-terminated",
            aws_region=AwsRegion.US_EAST_1.value,
            instance_type="c5.xlarge",
            ami_id="ami-test123",
            created_by="test-user",
        )
        worker.state.aws_instance_id = "i-terminated123"
        worker.state.status = CMLWorkerStatus.TERMINATED

        # Execute
        result = await service.collect_worker_metrics(worker, collect_cloudwatch=False)

        # Verify - should skip collection
        assert result.error == "Worker already terminated"
        assert result.ec2_state == "terminated"
        assert mock_aws_client.get_instance_status_checks.assert_not_called
