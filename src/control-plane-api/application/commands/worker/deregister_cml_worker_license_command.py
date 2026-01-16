"""Deregister CML Worker license command and handler."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from neuroglia.core import OperationResult
from neuroglia.mediation.mediator import Command, CommandHandler

from application.services.background_scheduler import BackgroundTaskScheduler
from domain.repositories.cml_worker_repository import CMLWorkerRepository

log = logging.getLogger(__name__)


@dataclass
class DeregisterCMLWorkerLicenseCommand(Command[OperationResult[dict]]):
    """Command to deregister a CML Worker license.

    Schedules a background job for async deregistration, similar to registration.
    """

    worker_id: str
    initiated_by: str | None = None


class DeregisterCMLWorkerLicenseCommandHandler(
    CommandHandler[DeregisterCMLWorkerLicenseCommand, OperationResult[dict]]
):
    """Handler for DeregisterCMLWorkerLicenseCommand."""

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        scheduler: BackgroundTaskScheduler,
    ):
        self._repository = worker_repository
        self._scheduler = scheduler

    async def handle_async(
        self,
        request: DeregisterCMLWorkerLicenseCommand,
    ) -> OperationResult[dict]:
        """Handle license deregistration command by scheduling background job.

        Returns immediately after scheduling the job. Actual deregistration
        happens asynchronously with SSE events for progress updates.
        """
        # Get worker
        worker = await self._repository.get_by_id_async(request.worker_id)
        if not worker:
            return self.not_found("Worker", f"Worker {request.worker_id} not found")

        # Schedule background job
        # Import here to avoid circular import at module load time
        from application.jobs.license_deregistration_job import LicenseDeregistrationJob

        job_id = f"license_dereg_{request.worker_id}_{int(datetime.now(UTC).timestamp())}"

        try:
            # Create and configure job
            job = LicenseDeregistrationJob(
                worker_id=request.worker_id,
                initiated_by=request.initiated_by,
            )
            job.__task_id__ = job_id
            job.__task_name__ = "LicenseDeregistrationJob"
            job.__background_task_type__ = "scheduled"
            job.__scheduled_at__ = datetime.now(UTC)

            # Enqueue via scheduler
            await self._scheduler.enqueue_task_async(job)

            log.info(f"📝 Scheduled license deregistration job for worker {request.worker_id} (job_id: {job_id})")

            return self.accepted(
                {
                    "message": "License deregistration initiated",
                    "worker_id": request.worker_id,
                    "job_id": job_id,
                    "status": "pending",
                    "note": "Monitor SSE events for completion status",
                }
            )

        except Exception as e:
            log.error(f"Failed to schedule deregistration job for worker {request.worker_id}: {e}")
            return self.internal_server_error(f"Failed to schedule deregistration: {e}")
