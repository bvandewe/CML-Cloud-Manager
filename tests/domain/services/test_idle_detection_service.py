"""Tests for IdleDetectionService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from domain.entities.cml_worker import CMLWorker
from domain.services.idle_detection_service import IdleDetectionService
from domain.value_object.cml_metrics import CMLMetrics


def test_is_worker_idle_with_active_labs():
    """Test that worker is not idle if labs are running."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=1)

    assert service.is_worker_idle(worker, 30) is False


def test_is_worker_idle_timeout_exceeded():
    """Test that worker is idle if timeout exceeded and no labs."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=0)
    worker.state.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=31)

    assert service.is_worker_idle(worker, 30) is True


def test_is_worker_idle_timeout_not_exceeded():
    """Test that worker is not idle if timeout not exceeded."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=0)
    worker.state.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=29)

    assert service.is_worker_idle(worker, 30) is False


def test_is_worker_idle_fallback_to_resumed_at():
    """Test fallback to last_resumed_at if last_activity_at is None."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=0)
    worker.state.last_activity_at = None
    worker.state.last_resumed_at = datetime.now(timezone.utc) - timedelta(minutes=31)

    assert service.is_worker_idle(worker, 30) is True


def test_is_worker_idle_fallback_to_created_at():
    """Test fallback to created_at if others are None."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=0)
    worker.state.last_activity_at = None
    worker.state.last_resumed_at = None
    worker.state.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)

    assert service.is_worker_idle(worker, 30) is True


def test_is_worker_idle_no_timestamps():
    """Test safe fallback if no timestamps available."""
    service = IdleDetectionService()
    worker = MagicMock(spec=CMLWorker)
    worker.state = MagicMock()
    worker.state.metrics = CMLMetrics(labs_count=0)
    worker.state.last_activity_at = None
    worker.state.last_resumed_at = None
    worker.state.created_at = None

    assert service.is_worker_idle(worker, 30) is False
    assert service.is_worker_idle(worker, 30) is False
