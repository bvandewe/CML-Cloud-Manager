"""Refresh Worker Labs command with handler.

This command orchestrates collecting fresh lab data from CML API for a specific worker
and updating the lab_records collection. It provides on-demand lab refresh capability
in addition to the scheduled 30-minute global refresh job.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pymongo.errors import DuplicateKeyError

from application.settings import Settings
from domain.entities.lab_record import LabRecord
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from domain.repositories.lab_record_repository import LabRecordRepository
from integration.services.cml_api_client import CMLApiClientFactory

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _parse_cml_timestamp(timestamp_str: str | None) -> datetime | None:
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
        log.warning(f"Failed to parse timestamp: {timestamp_str}")
        return None


@dataclass
class RefreshWorkerLabsCommand(Command[OperationResult[dict]]):
    """Command to refresh lab data from CML API for a specific worker.

    This command:
    1. Queries CML API for current lab data
    2. Creates or updates lab_records in database
    3. Records state changes in operation history
    4. Returns summary of labs synced

    Returns dict with refresh summary (synced, created, updated counts).
    """

    worker_id: str


class RefreshWorkerLabsCommandHandler(
    CommandHandlerBase,
    CommandHandler[RefreshWorkerLabsCommand, OperationResult[dict]],
):
    """Handle worker labs refresh from CML API."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        worker_repository: CMLWorkerRepository,
        lab_record_repository: LabRecordRepository,
        cml_api_client_factory: CMLApiClientFactory,
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self._worker_repository = worker_repository
        self._lab_record_repository = lab_record_repository
        self._cml_client_factory = cml_api_client_factory
        self._settings = settings

    @tracer.start_as_current_span("refresh_worker_labs_command_handler")
    async def handle_async(self, request: RefreshWorkerLabsCommand) -> OperationResult[dict]:
        """Handle refresh worker labs command.

        Args:
            request: Refresh command with worker ID

        Returns:
            OperationResult with refresh summary dict or error
        """
        command = request
        span = trace.get_current_span()
        span.set_attribute("worker.id", command.worker_id)

        try:
            # 1. Load worker from repository
            worker = await self._worker_repository.get_by_id_async(command.worker_id)
            if not worker:
                error = f"Worker {command.worker_id} not found"
                log.warning(error)
                span.set_status(Status(StatusCode.ERROR, error))
                return self.bad_request(error)

            # 2. Verify worker has endpoint (status check is more lenient)
            if not worker.state.https_endpoint:
                error = f"Worker {command.worker_id} has no HTTPS endpoint configured"
                log.warning(error)
                span.set_status(Status(StatusCode.ERROR, error))
                return self.bad_request(error)

            # Warn if worker is not running, but allow refresh attempt
            if worker.state.status != CMLWorkerStatus.RUNNING:
                log.warning(
                    f"Worker {command.worker_id} is not in RUNNING status "
                    f"(current: {worker.state.status.value}). Attempting refresh anyway..."
                )

            span.set_attribute("worker.endpoint", worker.state.https_endpoint)
            span.set_attribute("worker.status", worker.state.status.value)

            # 3. Refresh labs for this worker
            log.info(f"Refreshing labs for worker {command.worker_id}")
            synced, created, updated = await self._refresh_worker_labs(worker)

            summary = {
                "worker_id": command.worker_id,
                "labs_synced": synced,
                "labs_created": created,
                "labs_updated": updated,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            span.set_attribute("labs.synced", synced)
            span.set_attribute("labs.created", created)
            span.set_attribute("labs.updated", updated)
            span.set_status(Status(StatusCode.OK))

            # SSE events are broadcast automatically by domain event handlers
            # when lab records are created/updated via repository operations

            log.info(
                f"✅ Labs refreshed for worker {command.worker_id}: "
                f"synced={synced}, created={created}, updated={updated}"
            )

            return self.ok(summary)

        except Exception as e:
            error = f"Failed to refresh labs for worker {command.worker_id}: {str(e)}"
            log.exception(error)
            span.set_status(Status(StatusCode.ERROR, error))
            span.record_exception(e)
            return self.bad_request(str(e))

    async def _refresh_worker_labs(self, worker) -> tuple[int, int, int]:
        """Refresh labs for a single worker.

        Args:
            worker: CMLWorker aggregate

        Returns:
            Tuple of (synced_count, created_count, updated_count)
        """
        worker_id = worker.id()

        # Determine endpoint to use (public or private based on settings)
        https_endpoint = worker.get_effective_endpoint(self._settings.use_private_ip_for_monitoring)
        if https_endpoint != worker.state.https_endpoint:
            log.debug(f"Using private IP endpoint for labs refresh: {https_endpoint}")

        log.debug(f"Refreshing labs for worker {worker_id} at {https_endpoint}")

        # Create CML API client for this worker using factory
        cml_client = self._cml_client_factory.create(base_url=https_endpoint)

        # Fetch lab IDs from CML
        try:
            lab_ids = await cml_client.get_labs()
        except Exception as e:
            log.error(f"Failed to fetch labs from worker {worker_id}: {e}", exc_info=True)
            return (0, 0, 0)

        # Detect and remove orphaned lab records (labs deleted outside our system)
        existing_records = await self._lab_record_repository.get_all_by_worker_async(worker_id)
        existing_lab_ids = {record.state.lab_id for record in existing_records}
        current_lab_ids = set(lab_ids) if lab_ids else set()
        orphaned_lab_ids = existing_lab_ids - current_lab_ids

        log.info(
            f"Worker {worker_id}: Found {len(existing_records)} existing lab records in DB, "
            f"{len(current_lab_ids)} labs in CML"
        )
        log.debug(f"Existing lab IDs in DB: {existing_lab_ids}")
        log.debug(f"Current lab IDs in CML: {current_lab_ids}")

        if orphaned_lab_ids:
            log.info(
                f"Found {len(orphaned_lab_ids)} orphaned lab records for worker {worker_id}: "
                f"{list(orphaned_lab_ids)}"
            )
            for orphaned_lab_id in orphaned_lab_ids:
                try:
                    # Use direct MongoDB deletion instead of aggregate remove_async
                    deleted = await self._lab_record_repository.remove_by_lab_id_async(worker_id, orphaned_lab_id)
                    if deleted:
                        log.info(f"Removed orphaned lab record: {orphaned_lab_id}")
                    else:
                        log.warning(f"Orphaned lab record {orphaned_lab_id} not found in DB")
                except Exception as e:
                    log.error(
                        f"Failed to remove orphaned lab record {orphaned_lab_id}: {e}",
                        exc_info=True,
                    )

        if not lab_ids:
            log.debug(f"No labs found for worker {worker_id}")
            return (0, 0, 0)

        synced = 0
        created = 0
        updated = 0

        # Collect lab records for batch operations
        labs_to_create = []
        labs_to_update = []

        # Process each lab and collect for batch operations
        for lab_id in lab_ids:
            try:
                # Fetch lab details
                lab_details = await cml_client.get_lab_details(lab_id)
                if not lab_details:
                    log.warning(f"Failed to fetch details for lab {lab_id}")
                    continue

                # Check if lab record exists
                existing_record = await self._lab_record_repository.get_by_lab_id_async(worker_id, lab_id)

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
                    labs_to_update.append(existing_record)
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
                    labs_to_create.append(new_record)

                synced += 1

            except Exception as e:
                log.error(
                    f"Failed to sync lab {lab_id} for worker {worker_id}: {e}",
                    exc_info=True,
                )
                # Continue with next lab
                continue

        # Batch create new lab records
        if labs_to_create:
            try:
                created = await self._lab_record_repository.add_many_async(labs_to_create)
                log.debug(f"Batch created {created} lab records for worker {worker_id}")
            except DuplicateKeyError:
                # Race condition: some records were created by another process
                # Fall back to individual inserts with duplicate handling
                log.warning(
                    f"Duplicate key error in batch insert for worker {worker_id}, falling back to individual inserts"
                )
                for new_record in labs_to_create:
                    try:
                        await self._lab_record_repository.add_async(new_record)
                        created += 1
                    except DuplicateKeyError:
                        # Fetch and update the existing record instead
                        log.warning(
                            f"Duplicate lab record detected for worker {worker_id}, lab {new_record.state.lab_id}. "
                            f"Fetching and updating existing record."
                        )
                        existing_record = await self._lab_record_repository.get_by_lab_id_async(
                            worker_id, new_record.state.lab_id
                        )
                        if existing_record:
                            # Copy the state from new_record to existing_record
                            existing_record.update_from_cml(
                                title=new_record.state.title,
                                description=new_record.state.description,
                                notes=new_record.state.notes,
                                state=new_record.state.state,
                                owner_username=new_record.state.owner_username,
                                owner_fullname=new_record.state.owner_fullname,
                                node_count=new_record.state.node_count,
                                link_count=new_record.state.link_count,
                                groups=new_record.state.groups,
                                cml_modified_at=new_record.state.cml_modified_at,
                            )
                            labs_to_update.append(existing_record)
            except Exception as e:
                log.error(f"Failed to batch create lab records: {e}", exc_info=True)
                # Fall back to individual inserts
                for new_record in labs_to_create:
                    try:
                        await self._lab_record_repository.add_async(new_record)
                        created += 1
                    except Exception as insert_error:
                        log.error(
                            f"Failed to insert lab record {new_record.state.lab_id}: {insert_error}",
                            exc_info=True,
                        )

        # Batch update existing lab records
        if labs_to_update:
            try:
                updated = await self._lab_record_repository.update_many_async(labs_to_update)
                log.debug(f"Batch updated {updated} lab records for worker {worker_id}")
            except Exception as e:
                log.error(f"Failed to batch update lab records: {e}", exc_info=True)
                # Fall back to individual updates
                for existing_record in labs_to_update:
                    try:
                        await self._lab_record_repository.update_async(existing_record)
                        updated += 1
                    except Exception as update_error:
                        log.error(
                            f"Failed to update lab record {existing_record.id()}: {update_error}",
                            exc_info=True,
                        )

        log.info(f"Worker {worker_id}: synced={synced}, created={created}, updated={updated}")

        return (synced, created, updated)
        return (synced, created, updated)
        return (synced, created, updated)
        return (synced, created, updated)
