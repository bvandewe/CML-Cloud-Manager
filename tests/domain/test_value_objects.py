"""Tests for Domain Value Objects."""

from datetime import date, datetime

from domain.enums import LicenseStatus
from domain.value_object.cml_license import CMLLicense
from domain.value_object.cml_metrics import CMLMetrics


def test_cml_metrics_defaults():
    """Test CMLMetrics default values."""
    metrics = CMLMetrics()
    assert metrics.version is None
    assert metrics.ready is False
    assert metrics.uptime_seconds is None
    assert metrics.labs_count == 0
    assert metrics.system_info is None
    assert metrics.system_health is None
    assert metrics.last_synced_at is None


def test_cml_metrics_initialization():
    """Test CMLMetrics initialization with values."""
    now = datetime.now()
    metrics = CMLMetrics(
        version="2.7.0",
        ready=True,
        uptime_seconds=3600,
        labs_count=5,
        system_info={"cpu": "ok"},
        system_health={"valid": True},
        last_synced_at=now,
    )

    assert metrics.version == "2.7.0"
    assert metrics.ready is True
    assert metrics.uptime_seconds == 3600
    assert metrics.labs_count == 5
    assert metrics.system_info == {"cpu": "ok"}
    assert metrics.system_health == {"valid": True}
    assert metrics.last_synced_at == now


def test_cml_license_defaults():
    """Test CMLLicense default values."""
    license = CMLLicense()
    assert license.status == LicenseStatus.UNREGISTERED
    assert license.token is None
    assert license.operation_in_progress is False
    assert license.expiry_date is None
    assert license.features == ()
    assert license.raw_info is None


def test_cml_license_initialization():
    """Test CMLLicense initialization with values."""
    expiry = date(2025, 12, 31)
    license = CMLLicense(
        status=LicenseStatus.REGISTERED,
        token="abc-123",
        operation_in_progress=True,
        expiry_date=expiry,
        features=("base", "plus"),
        raw_info={"reg": "ok"},
    )

    assert license.status == LicenseStatus.REGISTERED
    assert license.token == "abc-123"
    assert license.operation_in_progress is True
    assert license.expiry_date == expiry
    assert license.features == ("base", "plus")
    assert license.raw_info == {"reg": "ok"}


def test_cml_metrics_utilization_calculation():
    """Test CMLMetrics utilization calculation logic."""
    # Test case 1: Valid stats
    stats = {
        "cpu": {"user_percent": 10.5, "system_percent": 5.5},
        "memory": {"total_kb": 1000, "available_kb": 400},
        "disk": {"size_kb": 500, "capacity_kb": 1000},
    }
    cpu, mem, storage = CMLMetrics.calculate_utilization_from_stats(stats)
    assert cpu == 16.0
    assert mem == 60.0
    assert storage == 50.0

    # Test case 2: Missing or invalid data
    stats_empty = {}
    cpu, mem, storage = CMLMetrics.calculate_utilization_from_stats(stats_empty)
    assert cpu is None
    assert mem is None
    assert storage is None

    # Test case 3: Partial data
    stats_partial = {
        "cpu": {"user_percent": 10.0},  # Missing system_percent
        "memory": {"total": 1000, "free": 200},  # Using alternative keys
    }
    cpu, mem, storage = CMLMetrics.calculate_utilization_from_stats(stats_partial)
    assert cpu is None  # Should be None because system_percent is missing
    assert mem == 80.0
    assert storage is None

    # Test case 4: Zero division protection
    stats_zero = {"memory": {"total_kb": 0, "available_kb": 0}, "disk": {"capacity_kb": 0, "size_kb": 0}}
    cpu, mem, storage = CMLMetrics.calculate_utilization_from_stats(stats_zero)
    assert mem is None
    assert storage is None
    assert storage is None
