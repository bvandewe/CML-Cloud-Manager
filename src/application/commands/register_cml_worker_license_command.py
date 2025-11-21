"""Register CML Worker license command and handler."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from neuroglia.core import OperationResult
from neuroglia.mediation.mediator import Command, CommandHandler

from application.services.background_scheduler import BackgroundTaskScheduler
from domain.repositories.cml_worker_repository import CMLWorkerRepository

log = logging.getLogger(__name__)


@dataclass
class RegisterCMLWorkerLicenseCommand(Command[OperationResult[dict]]):
    """Command to register a CML Worker license.

    This command schedules a background job to handle the actual registration
    and polling process, returning immediately to the caller.
    """

    worker_id: str
    license_token: str
    reregister: bool = False
    initiated_by: str | None = None


class RegisterCMLWorkerLicenseCommandHandler(CommandHandler[RegisterCMLWorkerLicenseCommand, OperationResult[dict]]):
    """Handler for RegisterCMLWorkerLicenseCommand."""

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        scheduler: BackgroundTaskScheduler,
    ):
        self._repository = worker_repository
        self._scheduler = scheduler

    async def handle_async(
        self,
        request: RegisterCMLWorkerLicenseCommand,
    ) -> OperationResult[dict]:
        """Handle license registration command.

        Steps:
        1. Validate worker exists and is running
        2. Schedule background job for registration + polling
        3. Return 202 Accepted immediately
        4. Background job will emit SSE events on completion
        """
        # Validate worker exists
        worker = await self._repository.get_by_id_async(request.worker_id)
        if not worker:
            return self.not_found("Worker", f"Worker {request.worker_id} not found")

        # Check worker is running
        if worker.state.status not in ["running", "ready"]:
            return self.bad_request(f"Worker must be running to register license (current: {worker.state.status})")

        # Schedule background job
        from application.jobs.license_registration_job import LicenseRegistrationJob

        job_id = f"license_reg_{request.worker_id}_{int(datetime.now(UTC).timestamp())}"

        try:
            # Create and configure job
            job = LicenseRegistrationJob(
                worker_id=request.worker_id,
                license_token=request.license_token,
                reregister=request.reregister,
            )
            job.__task_id__ = job_id
            job.__task_name__ = "LicenseRegistrationJob"
            job.__background_task_type__ = "scheduled"
            job.__scheduled_at__ = datetime.now(UTC)

            # Enqueue via scheduler
            await self._scheduler.enqueue_task_async(job)

            log.info(f"📝 Scheduled license registration job for worker {request.worker_id} " f"(job_id: {job_id})")

            return self.accepted(
                {
                    "message": "License registration initiated",
                    "worker_id": request.worker_id,
                    "job_id": job_id,
                    "status": "pending",
                    "note": "Monitor SSE events for completion status",
                }
            )

        except Exception as e:
            log.error(f"Failed to schedule license registration job: {e}")
            return self.internal_server_error(f"Failed to schedule registration: {e}")
