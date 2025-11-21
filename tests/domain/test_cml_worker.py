"""Tests for CMLWorker Aggregate."""

from datetime import datetime, timezone

from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus, LicenseStatus
from domain.value_object.cml_license import CMLLicense
from domain.value_object.cml_metrics import CMLMetrics


class TestCMLWorker:
    """Test CMLWorker aggregate."""

    def test_initialization(self):
        """Test worker initialization with default values."""
        worker = CMLWorker(name="test-worker", aws_region="us-east-1", instance_type="t3.medium")

        assert worker.state.name == "test-worker"
        assert worker.state.status == CMLWorkerStatus.PENDING
        assert isinstance(worker.state.metrics, CMLMetrics)
        assert isinstance(worker.state.license, CMLLicense)
        assert worker.state.metrics.labs_count == 0
        assert worker.state.license.status == LicenseStatus.UNREGISTERED

    def test_update_cml_metrics(self):
        """Test updating CML metrics."""
        worker = CMLWorker(name="test-worker", aws_region="us-east-1", instance_type="t3.medium")

        system_info = {"version": "2.7.0", "ready": True}
        system_health = {"valid": True}
        license_info = {"registration_status": "COMPLETED"}

        worker.update_cml_metrics(
            cml_version="2.7.0",
            system_info=system_info,
            system_health=system_health,
            license_info=license_info,
            ready=True,
            uptime_seconds=100,
            labs_count=2,
        )

        assert worker.state.metrics.version == "2.7.0"
        assert worker.state.metrics.ready is True
        assert worker.state.metrics.uptime_seconds == 100
        assert worker.state.metrics.labs_count == 2
        assert worker.state.metrics.system_info == system_info

        # Check license status update side-effect
        assert worker.state.license.status == LicenseStatus.REGISTERED

    def test_update_license(self):
        """Test updating license directly."""
        worker = CMLWorker(name="test-worker", aws_region="us-east-1", instance_type="t3.medium")

        worker.update_license(license_status=LicenseStatus.REGISTERED, license_token="token-123")

        assert worker.state.license.status == LicenseStatus.REGISTERED
        assert worker.state.license.token == "token-123"

    def test_is_idle_logic(self):
        """Test idle detection logic using new metrics structure."""
        worker = CMLWorker(name="test-worker", aws_region="us-east-1", instance_type="t3.medium")

        # No activity yet
        assert worker.is_idle(idle_threshold_minutes=30) is False

        # Update metrics with labs running
        worker.update_cml_metrics(
            cml_version="2.7.0",
            system_info={},
            system_health={},
            license_info={},
            ready=True,
            uptime_seconds=100,
            labs_count=1,  # Active labs
            synced_at=datetime.now(timezone.utc),
        )

        assert worker.is_idle(idle_threshold_minutes=30) is False

        # Update metrics with 0 labs, but recent sync
        worker.update_cml_metrics(
            cml_version="2.7.0",
            system_info={},
            system_health={},
            license_info={},
            ready=True,
            uptime_seconds=200,
            labs_count=0,  # No labs
            synced_at=datetime.now(timezone.utc),
        )

        assert worker.is_idle(idle_threshold_minutes=30) is False

        # Simulate old sync time (idle)
        # We need to manually set the state because update_cml_metrics uses current time if not provided,
        # or we can pass an old time.
        old_time = datetime.now(timezone.utc).replace(year=2020)

        # We can't easily inject old time via update_cml_metrics because it might filter out if no change?
        # But we can force it.
        worker.update_cml_metrics(
            cml_version="2.7.0",
            system_info={"changed": "yes"},  # Force change
            system_health={},
            license_info={},
            ready=True,
            uptime_seconds=300,
            labs_count=0,
            synced_at=old_time,
        )

        assert worker.is_idle(idle_threshold_minutes=30) is True
