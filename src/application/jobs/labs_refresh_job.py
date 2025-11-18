"""Labs refresh background job for synchronizing lab data from CML Workers.

This module defines a RecurrentBackgroundJob for refreshing lab records from CML API.
It runs every 30 minutes and updates the lab_records collection with current state.
"""

import logging
from datetime import datetime
from typing import Optional

from opentelemetry import trace

from application.services.background_scheduler import (
    RecurrentBackgroundJob,
    backgroundjob,
)
from domain.entities.lab_record import LabRecord
from domain.enums import CMLWorkerStatus
from domain.repositories import CMLWorkerRepository
from domain.repositories.lab_record_repository import LabRecordRepository
from integration.services.cml_api_client import CMLApiClient

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _parse_cml_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse CML timestamp string to datetime object.

    Args:
        timestamp_str: ISO format timestamp string from CML API

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning(f"Failed to parse timestamp: {timestamp_str}")
        return None


@backgroundjob(task_type="recurrent", interval=1800)  # 30 minutes
class LabsRefreshJob(RecurrentBackgroundJob):
    """Recurrent background job for refreshing lab data from all active workers.

    This job runs every 30 minutes and:
    - Fetches labs from CML API for all active workers
    - Upserts lab records to database
    - Creates lab_records collection indexes on first run
    - Creates or updates lab_records with change detection
    - Records state changes in operation history
    - Maintains a ring buffer of last 50 operations per lab

    Attributes:
        worker_repository: Repository for accessing CML workers
        lab_record_repository: Repository for persisting lab records
    """

    def __init__(
        self,
        worker_repository: Optional[CMLWorkerRepository] = None,
        lab_record_repository: Optional[LabRecordRepository] = None,
    ):
        """Initialize the labs refresh job.

        Args:
            worker_repository: Worker repository instance
            lab_record_repository: Lab record repository instance
        """
        self.worker_repository = worker_repository
        self.lab_record_repository = lab_record_repository
        self._service_provider = None

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["worker_repository"] = None
        state["lab_record_repository"] = None
        state["_service_provider"] = None
        return state

    def __setstate__(self, state):
        """Custom pickle deserialization - restore state."""
        self.__dict__.update(state)

    def configure(self, service_provider=None, **kwargs):
        """Configure the background job with dependencies.

        Args:
            service_provider: (Optional) Service provider for dependency injection
            **kwargs: Additional configuration parameters
        """
        logger.info("🔧 Configuring LabsRefreshJob")

        if service_provider:
            self._service_provider = service_provider

            # Ensure database indexes are created (idempotent operation)
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule for later if event loop is running
                    asyncio.create_task(self._ensure_indexes_async(service_provider))
                else:
                    # Run synchronously if no loop
                    loop.run_until_complete(
                        self._ensure_indexes_async(service_provider)
                    )
            except Exception as e:
                logger.warning(f"Could not create indexes during configure: {e}")

        # Inject worker repository
        if not hasattr(self, "worker_repository") or not self.worker_repository:
            from domain.repositories.cml_worker_repository import CMLWorkerRepository

            if self._service_provider:
                self.worker_repository = self._service_provider.get_required_service(
                    CMLWorkerRepository
                )
            else:
                raise RuntimeError("Worker repository not available")

            logger.info("✅ Configured Worker Repository")

        # Inject lab record repository
        if not hasattr(self, "lab_record_repository") or not self.lab_record_repository:
            from domain.repositories.lab_record_repository import LabRecordRepository

            if self._service_provider:
                self.lab_record_repository = (
                    self._service_provider.get_required_service(LabRecordRepository)
                )
            else:
                raise RuntimeError("Lab record repository not available")

            logger.info("✅ Configured Lab Record Repository")

    async def _ensure_indexes_async(self, service_provider):
        """Ensure database indexes exist (helper for configure)."""
        try:
            scope = service_provider.create_scope()
            try:
                lab_record_repo = scope.get_required_service(LabRecordRepository)
                await lab_record_repo.ensure_indexes_async()
                logger.info("✅ Lab record indexes ensured")
            finally:
                scope.dispose()
        except Exception as e:
            logger.error(f"Failed to ensure indexes: {e}", exc_info=True)

    async def run_every(self, *args, **kwargs) -> None:
        """Execute the labs refresh task - fetch and update lab records.

        This method is called by the BackgroundTaskScheduler at regular intervals (30 minutes).
        """
        with tracer.start_as_current_span("labs_refresh_job.run_every") as span:
            try:
                logger.info("🔄 Starting labs refresh cycle")

                # Get all active workers
                workers = await self.worker_repository.get_active_workers_async()
                span.set_attribute("workers.count", len(workers))

                total_labs_synced = 0
                total_labs_created = 0
                total_labs_updated = 0

                for worker in workers:
                    # Skip workers without HTTPS endpoint or not running
                    if (
                        not worker.state.https_endpoint
                        or worker.state.status != CMLWorkerStatus.RUNNING
                    ):
                        logger.debug(
                            f"Skipping worker {worker.id()} - "
                            f"status={worker.state.status}, endpoint={worker.state.https_endpoint}"
                        )
                        continue

                    try:
                        synced, created, updated = await self._refresh_worker_labs(
                            worker
                        )
                        total_labs_synced += synced
                        total_labs_created += created
                        total_labs_updated += updated
                    except Exception as e:
                        logger.error(
                            f"Failed to refresh labs for worker {worker.id()}: {e}",
                            exc_info=True,
                        )
                        span.record_exception(e)
                        # Continue with next worker instead of failing the entire job
                        continue

                logger.info(
                    f"✅ Labs refresh complete: synced={total_labs_synced}, "
                    f"created={total_labs_created}, updated={total_labs_updated}"
                )

                span.set_attribute("labs.synced", total_labs_synced)
                span.set_attribute("labs.created", total_labs_created)
                span.set_attribute("labs.updated", total_labs_updated)

            except Exception as e:
                logger.error(f"Labs refresh job failed: {e}", exc_info=True)
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    async def _refresh_worker_labs(self, worker) -> tuple[int, int, int]:
        """Refresh labs for a single worker.

        Args:
            worker: CML Worker entity

        Returns:
            Tuple of (synced_count, created_count, updated_count)
        """
        worker_id = worker.id()
        https_endpoint = worker.state.https_endpoint

        logger.debug(f"Refreshing labs for worker {worker_id} at {https_endpoint}")

        # Get settings for CML credentials
        from application.settings import app_settings

        # Create CML API client
        cml_client = CMLApiClient(
            base_url=https_endpoint,
            username=app_settings.cml_worker_api_username,
            password=app_settings.cml_worker_api_password,
            verify_ssl=False,  # TODO: Make this configurable
        )

        # Fetch lab IDs from CML
        try:
            lab_ids = await cml_client.get_labs()
        except Exception as e:
            logger.error(
                f"Failed to fetch labs from worker {worker_id}: {e}", exc_info=True
            )
            return (0, 0, 0)

        if not lab_ids:
            logger.debug(f"No labs found for worker {worker_id}")
            return (0, 0, 0)

        synced = 0
        created = 0
        updated = 0

        # Process each lab
        for lab_id in lab_ids:
            try:
                # Fetch lab details
                lab_details = await cml_client.get_lab_details(lab_id)
                if not lab_details:
                    logger.warning(f"Failed to fetch details for lab {lab_id}")
                    continue

                # Check if lab record exists
                existing_record = await self.lab_record_repository.get_by_lab_id_async(
                    worker_id, lab_id
                )

                if existing_record:
                    # Update existing record
                    existing_record.update_from_cml(
                        title=lab_details.lab_title,
                        description=lab_details.lab_description,
                        notes=lab_details.lab_notes,
                        state=lab_details.state,
                        owner_username=lab_details.owner_username,
                        owner_fullname=lab_details.owner_fullname,
                        node_count=lab_details.node_count,
                        link_count=lab_details.link_count,
                        groups=lab_details.groups,
                        cml_modified_at=_parse_cml_timestamp(lab_details.modified),
                    )
                    await self.lab_record_repository.update_async(existing_record)
                    updated += 1
                else:
                    # Create new record
                    new_record = LabRecord.create(
                        lab_id=lab_id,
                        worker_id=worker_id,
                        title=lab_details.lab_title,
                        description=lab_details.lab_description,
                        notes=lab_details.lab_notes,
                        state=lab_details.state,
                        owner_username=lab_details.owner_username,
                        owner_fullname=lab_details.owner_fullname,
                        node_count=lab_details.node_count,
                        link_count=lab_details.link_count,
                        groups=lab_details.groups,
                        cml_created_at=_parse_cml_timestamp(lab_details.created),
                        cml_modified_at=_parse_cml_timestamp(lab_details.modified),
                    )
                    await self.lab_record_repository.add_async(new_record)
                    created += 1

                synced += 1

            except Exception as e:
                logger.error(
                    f"Failed to sync lab {lab_id} for worker {worker_id}: {e}",
                    exc_info=True,
                )
                # Continue with next lab
                continue

        logger.info(
            f"Worker {worker_id}: synced={synced}, created={created}, updated={updated}"
        )

        return (synced, created, updated)
