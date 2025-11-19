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
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from application.services.sse_event_relay import SSEEventRelay
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
        sse_relay: SSEEventRelay,
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
        self._sse_relay = sse_relay

    @tracer.start_as_current_span("refresh_worker_labs_command_handler")
    async def handle_async(
        self, request: RefreshWorkerLabsCommand
    ) -> OperationResult[dict]:
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

            # 4. Broadcast event to SSE clients for real-time UI updates
            try:
                await self._sse_relay.broadcast_event(
                    event_type="worker.labs.updated",
                    data={
                        "worker_id": command.worker_id,
                        "labs_synced": synced,
                        "labs_created": created,
                        "labs_updated": updated,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                # Don't fail the command if SSE broadcast fails
                log.warning(
                    f"Failed to broadcast SSE event for labs refresh on worker {command.worker_id}: {e}"
                )

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
        https_endpoint = worker.state.https_endpoint

        log.debug(f"Refreshing labs for worker {worker_id} at {https_endpoint}")

        # Create CML API client for this worker using factory
        cml_client = self._cml_client_factory.create(base_url=https_endpoint)

        # Fetch lab IDs from CML
        try:
            lab_ids = await cml_client.get_labs()
        except Exception as e:
            log.error(
                f"Failed to fetch labs from worker {worker_id}: {e}", exc_info=True
            )
            return (0, 0, 0)

        if not lab_ids:
            log.debug(f"No labs found for worker {worker_id}")
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
                    log.warning(f"Failed to fetch details for lab {lab_id}")
                    continue

                # Check if lab record exists
                existing_record = await self._lab_record_repository.get_by_lab_id_async(
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
                    await self._lab_record_repository.update_async(existing_record)
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
                    await self._lab_record_repository.add_async(new_record)
                    created += 1

                synced += 1

            except Exception as e:
                log.error(
                    f"Failed to sync lab {lab_id} for worker {worker_id}: {e}",
                    exc_info=True,
                )
                # Continue with next lab
                continue

        log.info(
            f"Worker {worker_id}: synced={synced}, created={created}, updated={updated}"
        )

        return (synced, created, updated)
