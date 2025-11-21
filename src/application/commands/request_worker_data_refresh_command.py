"""Request Worker Data Refresh command with handler.

This command implements asynchronous on-demand worker data refresh by scheduling
a background job rather than performing synchronous execution. It checks throttling
and imminent global jobs before scheduling, then emits SSE events to notify the UI
of the scheduling decision.

Refreshes all worker data: EC2 metadata, CloudWatch metrics, CML data, and labs.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from application.jobs.on_demand_worker_data_refresh_job import OnDemandWorkerDataRefreshJob
from application.services.background_scheduler import BackgroundTaskScheduler
from application.settings import app_settings
from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from infrastructure.services.worker_refresh_throttle import WorkerRefreshThrottle

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class RequestWorkerDataRefreshCommand(Command[OperationResult[dict]]):
    """Command to request asynchronous worker data refresh.

    This command validates worker state, checks throttling constraints, and schedules
    a one-time background job if acceptable. Returns immediately with scheduling decision.

    The background job refreshes EC2 status, CloudWatch metrics, CML data, and labs.

    SSE events emitted:
    - worker.refresh.requested: Job scheduled successfully
    - worker.refresh.skipped: Request rejected (with reason)

    Returns dict with scheduling outcome.
    """

    worker_id: str
    region: str


class RequestWorkerDataRefreshCommandHandler(
    CommandHandlerBase,
    CommandHandler[RequestWorkerDataRefreshCommand, OperationResult[dict]],
):
    """Handle async worker data refresh requests (metadata, metrics, and labs)."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        refresh_throttle: WorkerRefreshThrottle,
        background_task_scheduler: BackgroundTaskScheduler,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self._worker_repository = cml_worker_repository
        self._refresh_throttle = refresh_throttle
        self._scheduler = background_task_scheduler

    async def handle_async(self, request: RequestWorkerDataRefreshCommand) -> OperationResult[dict]:
        """Handle async data refresh request by scheduling job or rejecting with reason.

        Args:
            request: Refresh request with worker ID and region

        Returns:
            OperationResult with scheduling decision dict
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "request_worker_refresh",
                "refresh.mode": "on_demand",
            }
        )

        try:
            # 1. Validate worker existence
            worker = await self._worker_repository.get_by_id_async(command.worker_id)
            if not worker:
                error_msg = f"Worker {command.worker_id} not found"
                log.warning(error_msg)
                return self.bad_request(error_msg)

            # 2. Check worker status (only running workers should be refreshed)
            if worker.state.status != CMLWorkerStatus.RUNNING:
                reason = f"not_running (status: {worker.state.status.value})"

                # Emit domain event (event handler will broadcast SSE)
                worker.skip_data_refresh(
                    reason=reason,
                    skipped_at=datetime.now(timezone.utc).isoformat(),
                )
                await self._worker_repository.update_async(worker)

                log.info(f"Refresh skipped for worker {command.worker_id} - {reason}")

                return self.ok(
                    {
                        "scheduled": False,
                        "reason": reason,
                        "worker_status": worker.state.status.value,
                    }
                )

            # 3. Check throttling
            if not self._refresh_throttle.can_refresh(command.worker_id):
                retry_after = self._refresh_throttle.get_time_until_next_refresh(command.worker_id)
                retry_after_int = int(retry_after) if retry_after is not None else 0
                reason = "rate_limited"

                # Emit domain event (event handler will broadcast SSE)
                worker.skip_data_refresh(
                    reason=reason,
                    skipped_at=datetime.now(timezone.utc).isoformat(),
                )
                await self._worker_repository.update_async(worker)

                log.info(f"Refresh throttled for worker {command.worker_id} - " f"retry after {retry_after:.1f}s")

                return self.ok(
                    {
                        "scheduled": False,
                        "reason": reason,
                        "retry_after_seconds": retry_after_int,
                    }
                )

            # 4. Check imminent global background job
            global_job = self._scheduler.get_job("WorkerMetricsCollectionJob")
            if global_job and global_job.next_run_time:
                now_utc = datetime.now(timezone.utc)
                next_run_utc = global_job.next_run_time.replace(tzinfo=timezone.utc)
                time_until_job = (next_run_utc - now_utc).total_seconds()

                if 0 < time_until_job <= app_settings.worker_refresh_check_upcoming_job_threshold:
                    reason = "background_job_imminent"

                    # Emit domain event (event handler will broadcast SSE)
                    worker.skip_data_refresh(
                        reason=reason,
                        skipped_at=datetime.now(timezone.utc).isoformat(),
                    )
                    await self._worker_repository.update_async(worker)

                    log.info(
                        f"Refresh skipped for worker {command.worker_id} - " f"background job in {time_until_job:.1f}s"
                    )

                    return self.ok(
                        {
                            "scheduled": False,
                            "reason": reason,
                            "seconds_until_background_job": time_until_job,
                        }
                    )

            # 5. Schedule on-demand refresh job
            job_id = f"on_demand_refresh_{command.worker_id}"

            # Check if job already scheduled
            existing_job = self._scheduler.get_job(job_id)
            if existing_job and existing_job.next_run_time:
                now_utc = datetime.now(timezone.utc)
                next_run_utc = existing_job.next_run_time.replace(tzinfo=timezone.utc)
                time_until = (next_run_utc - now_utc).total_seconds()

                # If job pending within next 30s, treat as already scheduled
                if 0 < time_until <= 30:
                    reason = "already_scheduled"

                    # Emit domain event (event handler will broadcast SSE)
                    worker.skip_data_refresh(
                        reason=reason,
                        skipped_at=datetime.now(timezone.utc).isoformat(),
                    )
                    await self._worker_repository.update_async(worker)

                    log.info(
                        f"Refresh already scheduled for worker {command.worker_id} - " f"pending in {time_until:.1f}s"
                    )

                    return self.ok(
                        {
                            "scheduled": False,
                            "reason": reason,
                            "existing_job_in_seconds": time_until,
                        }
                    )

            # Create and schedule job
            job = OnDemandWorkerDataRefreshJob(worker_id=command.worker_id)
            job.__task_id__ = job_id
            job.__task_name__ = "OnDemandWorkerDataRefreshJob"
            job.__background_task_type__ = "scheduled"
            # Schedule slightly in the future to avoid edge-case immediate misfire
            job.__scheduled_at__ = datetime.now(timezone.utc) + timedelta(seconds=1)

            # Enqueue via scheduler
            await self._scheduler.enqueue_task_async(job)

            # Note: Throttle recording happens in RefreshWorkerMetricsCommand when job executes
            # This prevents recording throttle before the actual refresh happens

            # Emit domain event (event handler will broadcast SSE)
            worker.request_data_refresh(
                requested_at=datetime.now(timezone.utc).isoformat(),
                requested_by="user",  # TODO: Get from auth context
            )
            await self._worker_repository.update_async(worker)

            log.info(f"✅ On-demand refresh scheduled for worker {command.worker_id} " f"(job_id: {job_id})")

            return self.ok(
                {
                    "scheduled": True,
                    "job_id": job_id,
                    "eta_seconds": 1,
                }
            )

        except Exception as e:
            error_msg = f"Failed to schedule refresh for worker {command.worker_id}: {str(e)}"
            log.exception(error_msg)
            return self.internal_server_error(error_msg)
