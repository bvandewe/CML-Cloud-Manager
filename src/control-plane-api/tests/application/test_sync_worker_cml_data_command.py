"""Tests for SyncWorkerCMLDataCommand handler."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from neuroglia.eventing.cloud_events.infrastructure import CloudEventBus
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator

from application.commands import (SyncWorkerCMLDataCommand,
                                  SyncWorkerCMLDataCommandHandler)
from application.services.cml_health_service import CMLHealthResult, CMLHealthService
from application.settings import Settings
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLServiceStatus, CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLSystemStats
from tests.fixtures.mixins import BaseTestCase


class TestSyncWorkerCMLDataCommand(BaseTestCase):
    """Test SyncWorkerCMLDataCommand handler."""

    @pytest.fixture
    def mock_cml_worker_repository(self) -> MagicMock:
        """Mock CMLWorkerRepository."""
        return MagicMock(spec=CMLWorkerRepository)

    @pytest.fixture
    def mock_cml_health_service(self) -> MagicMock:
        """Mock CMLHealthService."""
        return MagicMock(spec=CMLHealthService)

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Mock Settings."""
        settings = MagicMock(spec=Settings)
        settings.metrics_change_threshold_percent = 5.0
        settings.use_private_ip_for_monitoring = False
        return settings

    @pytest.fixture
    def handler(
        self,
        mock_cml_worker_repository: MagicMock,
        mock_cml_health_service: MagicMock,
        mock_settings: MagicMock,
    ) -> SyncWorkerCMLDataCommandHandler:
        """Create handler with mocked dependencies."""
        return SyncWorkerCMLDataCommandHandler(
            mediator=MagicMock(spec=Mediator),
            mapper=MagicMock(spec=Mapper),
            cloud_event_bus=MagicMock(spec=CloudEventBus),
            cloud_event_publishing_options=MagicMock(),
            cml_worker_repository=mock_cml_worker_repository,
            cml_health_service=mock_cml_health_service,
            settings=mock_settings,
        )

    @pytest.mark.asyncio
    async def test_sync_success_healthy(
        self,
        handler: SyncWorkerCMLDataCommandHandler,
        mock_cml_worker_repository: MagicMock,
        mock_cml_health_service: MagicMock,
    ) -> None:
        """Test successful sync with healthy CML instance."""
        # Arrange
        worker_id = "worker-123"
        command = SyncWorkerCMLDataCommand(worker_id=worker_id)

        # Mock worker
        worker = MagicMock(spec=CMLWorker)
        worker.state = MagicMock()
        worker.state.status = CMLWorkerStatus.RUNNING
        worker.state.https_endpoint = "https://1.2.3.4"
        worker.get_effective_endpoint.return_value = "https://1.2.3.4"
        worker.state.service_status = CMLServiceStatus.UNAVAILABLE
        worker.state.metrics = MagicMock()
        worker.state.metrics.version = "2.6.0"
        worker.state.metrics.ready = True
        worker.state.metrics.labs_count = 5

        mock_cml_worker_repository.get_by_id_async = AsyncMock(return_value=worker)
        mock_cml_worker_repository.update_async = AsyncMock()

        # Mock health service result
        health_result = CMLHealthResult(
            is_accessible=True,
            is_healthy=True,
            version="2.7.0",
            ready=True,
            system_stats=CMLSystemStats(
                computes={"node1": "ok"},
                all_cpu_count=10,
                all_cpu_percent=10.0,
                all_memory_total=1000,
                all_memory_free=500,
                all_memory_used=500,
                all_disk_total=1000,
                all_disk_free=500,
                all_disk_used=500,
                controller_disk_total=1000,
                controller_disk_free=500,
                controller_disk_used=500,
                allocated_cpus=0,
                allocated_memory=0,
                total_nodes=0,
                running_nodes=10,
            ),
            system_health=MagicMock(valid=True, is_licensed=True, is_enterprise=True, computes={}, controller={}),
            license_info={"status": "Registered"},
        )
        mock_cml_health_service.check_health = AsyncMock(return_value=health_result)

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.is_success
        assert result.status_code == 200

        # Verify repository calls
        mock_cml_worker_repository.get_by_id_async.assert_called_once_with(worker_id)
        mock_cml_worker_repository.update_async.assert_called_once_with(worker)

        # Verify health service call
        mock_cml_health_service.check_health.assert_called_once_with(endpoint="https://1.2.3.4", timeout=15.0)

        # Verify worker updates
        worker.update_service_status.assert_called_with(
            new_service_status=CMLServiceStatus.AVAILABLE, https_endpoint="https://1.2.3.4"
        )
        worker.update_cml_metrics.assert_called_once()

        # Check result content
        data = result.data
        assert data["cml_data_synced"] is True
        assert data["cml_version"] == "2.6.0"  # From worker state (mocked)

    @pytest.mark.asyncio
    async def test_sync_worker_not_found(
        self,
        handler: SyncWorkerCMLDataCommandHandler,
        mock_cml_worker_repository: MagicMock,
    ) -> None:
        """Test sync when worker is not found."""
        # Arrange
        mock_cml_worker_repository.get_by_id_async = AsyncMock(return_value=None)
        command = SyncWorkerCMLDataCommand(worker_id="missing")

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert not result.is_success
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_sync_worker_not_running(
        self,
        handler: SyncWorkerCMLDataCommandHandler,
        mock_cml_worker_repository: MagicMock,
    ) -> None:
        """Test sync when worker is not running."""
        # Arrange
        worker = MagicMock(spec=CMLWorker)
        worker.state = MagicMock()
        worker.state.status = CMLWorkerStatus.STOPPED
        mock_cml_worker_repository.get_by_id_async = AsyncMock(return_value=worker)

        command = SyncWorkerCMLDataCommand(worker_id="stopped")

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.is_success
        assert result.data["cml_data_synced"] is False
        assert result.data["reason"] == "Worker not running"

    @pytest.mark.asyncio
    async def test_sync_service_unavailable(
        self,
        handler: SyncWorkerCMLDataCommandHandler,
        mock_cml_worker_repository: MagicMock,
        mock_cml_health_service: MagicMock,
    ) -> None:
        """Test sync when CML service is unavailable."""
        # Arrange
        worker = MagicMock(spec=CMLWorker)
        worker.state = MagicMock()
        worker.state.status = CMLWorkerStatus.RUNNING
        worker.state.https_endpoint = "https://1.2.3.4"
        mock_cml_worker_repository.get_by_id_async = AsyncMock(return_value=worker)
        mock_cml_worker_repository.update_async = AsyncMock()

        # Mock health service result (inaccessible)
        health_result = CMLHealthResult(is_accessible=False, errors={"system_info": "Connection refused"})
        mock_cml_health_service.check_health = AsyncMock(return_value=health_result)

        command = SyncWorkerCMLDataCommand(worker_id="worker-123")

        # Act
        result = await handler.handle_async(command)

        # Assert
        assert result.is_success
        assert result.data["cml_data_synced"] is False
        assert result.data["service_status"] == CMLServiceStatus.UNAVAILABLE.value

        worker.update_service_status.assert_called_with(
            new_service_status=CMLServiceStatus.UNAVAILABLE, https_endpoint="https://1.2.3.4"
        )
