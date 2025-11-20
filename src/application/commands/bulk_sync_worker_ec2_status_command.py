"""Bulk sync EC2 status for multiple workers command with handler."""

import asyncio
import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.repositories.cml_worker_repository import CMLWorkerRepository

from .command_handler_base import CommandHandlerBase
from .sync_worker_ec2_status_command import SyncWorkerEC2StatusCommand

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class BulkSyncResult:
    """Result of bulk sync operation."""

    synced: list[str]  # Worker IDs successfully synced
    failed: list[dict[str, str]]  # {"worker_id": str, "error": str}
    total_workers: int
    total_synced: int
    total_failed: int


@dataclass
class BulkSyncWorkerEC2StatusCommand(Command[OperationResult[BulkSyncResult]]):
    """Command to bulk sync EC2 status for multiple workers.

    This command synchronizes EC2 instance status for all specified workers
    (or all active workers if none specified) by executing SyncWorkerEC2StatusCommand
    for each worker concurrently with rate limiting.

    Args:
        worker_ids: Optional list of specific worker IDs to sync (syncs all active if None)
        max_concurrent: Maximum concurrent sync operations (default: 10)
    """

    worker_ids: list[str] | None = None
    max_concurrent: int = 10


class BulkSyncWorkerEC2StatusCommandHandler(
    CommandHandlerBase,
    CommandHandler[BulkSyncWorkerEC2StatusCommand, OperationResult[BulkSyncResult]],
):
    """Handle bulk EC2 status sync for multiple workers."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository

    async def handle_async(self, request: BulkSyncWorkerEC2StatusCommand) -> OperationResult[BulkSyncResult]:
        """Handle bulk EC2 status sync command.

        Args:
            request: Bulk sync command with optional worker IDs

        Returns:
            OperationResult with BulkSyncResult containing synced/failed counts
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "bulk_sync.type": "ec2_status",
                "bulk_sync.has_worker_filter": command.worker_ids is not None,
                "bulk_sync.max_concurrent": command.max_concurrent,
            }
        )

        try:
            with tracer.start_as_current_span("get_target_workers") as span:
                # Get target workers
                if command.worker_ids:
                    log.info(f"Syncing EC2 status for {len(command.worker_ids)} specified workers")
                    workers = []
                    for worker_id in command.worker_ids:
                        worker = await self.cml_worker_repository.get_by_id_async(worker_id)
                        if worker:
                            workers.append(worker)
                        else:
                            log.warning(f"Worker {worker_id} not found - skipping")
                else:
                    log.info("Syncing EC2 status for all active workers")
                    workers = await self.cml_worker_repository.get_active_workers_async()

                if not workers:
                    log.warning("No workers found to sync")
                    return self.ok(
                        BulkSyncResult(
                            synced=[],
                            failed=[],
                            total_workers=0,
                            total_synced=0,
                            total_failed=0,
                        )
                    )

                log.info(f"Found {len(workers)} workers to sync EC2 status")
                span.set_attribute("workers.count", len(workers))

            with tracer.start_as_current_span("sync_workers") as sync_span:
                synced_worker_ids = []
                failed_workers = []

                # Create semaphore for rate limiting
                semaphore = asyncio.Semaphore(command.max_concurrent)

                async def sync_single_worker(worker_id: str):
                    """Sync single worker with semaphore rate limiting."""
                    async with semaphore:
                        try:
                            with tracer.start_as_current_span("sync_worker_ec2_status") as worker_span:
                                worker_span.set_attribute("worker.id", worker_id)

                                # Execute sync command via mediator
                                result = await self.mediator.execute_async(
                                    SyncWorkerEC2StatusCommand(worker_id=worker_id)
                                )

                                if result.status == 200:
                                    log.debug(f"✅ EC2 status synced for worker {worker_id}")
                                    worker_span.set_attribute("sync.success", True)
                                    return {"worker_id": worker_id, "success": True}
                                else:
                                    error_msg = result.detail or "Unknown error"
                                    log.warning(f"⚠️ EC2 status sync failed for worker {worker_id}: {error_msg}")
                                    worker_span.set_attribute("sync.success", False)
                                    worker_span.set_attribute("sync.error", error_msg)
                                    return {
                                        "worker_id": worker_id,
                                        "success": False,
                                        "error": error_msg,
                                    }

                        except Exception as e:
                            log.error(
                                f"❌ Failed to sync EC2 status for worker {worker_id}: {e}",
                                exc_info=True,
                            )
                            return {
                                "worker_id": worker_id,
                                "success": False,
                                "error": str(e),
                            }

                # Process all workers concurrently
                results = await asyncio.gather(
                    *[sync_single_worker(w.id()) for w in workers],
                    return_exceptions=True,
                )

                # Separate successful and failed syncs
                for result in results:
                    if isinstance(result, Exception):
                        log.error(f"Worker sync exception: {result}")
                        failed_workers.append({"worker_id": "unknown", "error": str(result)})
                    elif isinstance(result, dict) and result.get("success"):
                        synced_worker_ids.append(result["worker_id"])
                    elif isinstance(result, dict):
                        failed_workers.append(
                            {
                                "worker_id": result["worker_id"],
                                "error": result.get("error", "Unknown error"),
                            }
                        )

                sync_span.set_attribute("workers.synced", len(synced_worker_ids))
                sync_span.set_attribute("workers.failed", len(failed_workers))

            bulk_result = BulkSyncResult(
                synced=synced_worker_ids,
                failed=failed_workers,
                total_workers=len(workers),
                total_synced=len(synced_worker_ids),
                total_failed=len(failed_workers),
            )

            log.info(
                f"🎉 Bulk EC2 status sync completed: {bulk_result.total_synced} synced, "
                f"{bulk_result.total_failed} failed out of {bulk_result.total_workers} workers"
            )

            return self.ok(bulk_result)

        except Exception as e:
            log.error(f"Unexpected error in bulk EC2 status sync: {e}", exc_info=True)
            return self.internal_server_error(f"Bulk sync failed: {str(e)}")
