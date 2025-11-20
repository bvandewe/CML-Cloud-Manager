"""Test concurrent processing in background jobs.

Verifies that background jobs process workers concurrently with semaphore controls.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from neuroglia.mediation import Mediator

from application.jobs.labs_refresh_job import LabsRefreshJob
from application.jobs.worker_metrics_collection_job import WorkerMetricsCollectionJob
from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository


@pytest.fixture
def mock_workers():
    """Create mock workers for testing."""
    workers = []
    for i in range(15):  # Create 15 workers to test concurrent processing
        worker = MagicMock(spec=CMLWorker)
        worker.id.return_value = f"worker-{i}"
        worker.state = MagicMock()
        worker.state.status = CMLWorkerStatus.RUNNING
        worker.state.https_endpoint = f"https://worker-{i}.example.com"
        worker.state.cml_ready = True
        workers.append(worker)
    return workers


@pytest.mark.asyncio
async def test_worker_metrics_job_uses_concurrent_processing(mock_workers):
    """Test that WorkerMetricsCollectionJob processes workers concurrently with semaphore."""
    # Mock dependencies
    mock_service_provider = MagicMock()
    mock_scope = MagicMock()
    mock_service_provider.create_scope.return_value = mock_scope

    mock_repository = AsyncMock(spec=CMLWorkerRepository)
    mock_repository.get_active_workers_async.return_value = mock_workers

    mock_mediator = AsyncMock(spec=Mediator)
    # Mock successful responses from commands
    success_result = MagicMock()
    success_result.status = 200
    success_result.data = {
        "operations": {
            "ec2_sync": {"worker_status": "running"},
            "cml_sync": {"cml_ready": True},
        }
    }
    mock_mediator.execute_async.return_value = success_result

    mock_scope.get_required_service.side_effect = lambda t: (
        mock_repository if t == CMLWorkerRepository else mock_mediator
    )

    # Create job instance
    job = WorkerMetricsCollectionJob()
    job._service_provider = mock_service_provider
    job.aws_ec2_client = MagicMock()  # Mock the required AWS client

    # Track concurrent execution
    active_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    original_execute = mock_mediator.execute_async

    async def tracked_execute(*args, **kwargs):
        nonlocal active_count, max_concurrent
        async with lock:
            active_count += 1
            if active_count > max_concurrent:
                max_concurrent = active_count

        # Simulate some processing time
        await asyncio.sleep(0.01)

        async with lock:
            active_count -= 1

        return await original_execute(*args, **kwargs)

    mock_mediator.execute_async = tracked_execute

    # Execute the job
    await job.run_every()

    # Verify concurrent processing happened
    assert mock_repository.get_active_workers_async.called
    assert original_execute.call_count >= len(mock_workers)  # At least one command per worker

    # Verify concurrency was controlled (should not exceed 10 based on semaphore)
    assert max_concurrent <= 10, f"Expected max 10 concurrent operations, got {max_concurrent}"
    assert max_concurrent > 1, f"Expected concurrent processing, but only {max_concurrent} concurrent"

    # Cleanup
    mock_scope.dispose.assert_called()


@pytest.mark.asyncio
async def test_labs_refresh_job_uses_concurrent_processing(mock_workers):
    """Test that LabsRefreshJob processes workers concurrently with semaphore."""
    # Mock dependencies
    mock_service_provider = MagicMock()
    mock_scope = MagicMock()
    mock_service_provider.create_scope.return_value = mock_scope

    mock_worker_repository = AsyncMock(spec=CMLWorkerRepository)
    mock_worker_repository.get_active_workers_async.return_value = mock_workers[:10]

    mock_lab_repository = AsyncMock()
    mock_lab_repository.get_all_by_worker_async.return_value = []

    mock_cml_client_factory = MagicMock()
    mock_cml_client = AsyncMock()
    mock_cml_client.get_labs.return_value = []
    mock_cml_client_factory.create.return_value = mock_cml_client

    def get_service(service_type):
        from domain.repositories.lab_record_repository import LabRecordRepository
        from integration.services.cml_api_client import CMLApiClientFactory

        if service_type == CMLWorkerRepository:
            return mock_worker_repository
        elif service_type == LabRecordRepository:
            return mock_lab_repository
        elif service_type == CMLApiClientFactory:
            return mock_cml_client_factory
        return None

    mock_scope.get_required_service.side_effect = get_service

    # Create job instance
    job = LabsRefreshJob()
    job._service_provider = mock_service_provider

    # Track concurrent execution
    active_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    original_get_labs = mock_cml_client.get_labs

    async def tracked_get_labs(*args, **kwargs):
        nonlocal active_count, max_concurrent
        async with lock:
            active_count += 1
            if active_count > max_concurrent:
                max_concurrent = active_count

        # Simulate some processing time
        await asyncio.sleep(0.01)

        async with lock:
            active_count -= 1

        return await original_get_labs(*args, **kwargs)

    mock_cml_client.get_labs = tracked_get_labs

    # Execute the job
    await job.run_every()

    # Verify concurrent processing happened
    assert mock_worker_repository.get_active_workers_async.called
    assert mock_cml_client_factory.create.call_count == 10  # One client per worker

    # Verify concurrency was controlled (should not exceed 5 based on semaphore)
    assert max_concurrent <= 5, f"Expected max 5 concurrent operations, got {max_concurrent}"
    assert max_concurrent > 1, f"Expected concurrent processing, but only {max_concurrent} concurrent"

    # Cleanup
    mock_scope.dispose.assert_called()


@pytest.mark.asyncio
async def test_semaphore_prevents_overload():
    """Test that semaphore actually limits concurrent operations."""
    # Create a semaphore with limit 3
    semaphore = asyncio.Semaphore(3)

    active_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def simulated_task(task_id):
        nonlocal active_count, max_concurrent
        async with semaphore:
            async with lock:
                active_count += 1
                if active_count > max_concurrent:
                    max_concurrent = active_count

            # Simulate work
            await asyncio.sleep(0.05)

            async with lock:
                active_count -= 1

        return f"task-{task_id}"

    # Execute 10 tasks concurrently
    results = await asyncio.gather(*[simulated_task(i) for i in range(10)])

    # Verify all tasks completed
    assert len(results) == 10

    # Verify semaphore limited concurrency to 3
    assert max_concurrent <= 3, f"Semaphore failed: {max_concurrent} concurrent (expected ≤3)"
    assert max_concurrent == 3, f"Expected exactly 3 concurrent, got {max_concurrent}"
