"""Delete Lab Command - deletes a lab from a CML worker."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core.operation_result import OperationResult
from neuroglia.mediation import Command, CommandHandler, Mediator

from application.services.background_scheduler import BackgroundTaskScheduler
from application.settings import Settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from domain.repositories.lab_record_repository import LabRecordRepository
from integration.services.cml_api_client import CMLApiClientFactory

log = logging.getLogger(__name__)


@dataclass
class DeleteLabCommand(Command[OperationResult[dict]]):
    """Command to delete a lab from a CML worker.

    Attributes:
        worker_id: Worker ID hosting the lab
        lab_id: Lab identifier to delete
    """

    worker_id: str
    lab_id: str


class DeleteLabCommandHandler(CommandHandler[DeleteLabCommand, OperationResult[dict]]):
    """Handler for DeleteLabCommand - deletes lab from CML worker."""

    def __init__(
        self,
        mediator: Mediator,
        worker_repository: CMLWorkerRepository,
        lab_record_repository: LabRecordRepository,
        cml_api_client_factory: CMLApiClientFactory,
        background_task_scheduler: BackgroundTaskScheduler,
        settings: Settings,
    ):
        """Initialize handler with repository dependencies.

        Args:
            mediator: Mediator for triggering other commands
            worker_repository: Repository for accessing CML worker data
            lab_record_repository: Repository for accessing lab records
            cml_api_client_factory: Factory for creating CML API clients
            background_task_scheduler: Scheduler for checking background jobs
            settings: Application settings
        """
        self._mediator = mediator
        self._worker_repository = worker_repository
        self._lab_record_repository = lab_record_repository
        self._cml_client_factory = cml_api_client_factory
        self._scheduler = background_task_scheduler
        self._settings = settings

    async def handle_async(self, request: DeleteLabCommand, cancellation_token=None) -> OperationResult[dict]:
        """Delete lab from CML worker.

        Args:
            request: Command containing worker_id and lab_id
            cancellation_token: Optional cancellation token

        Returns:
            OperationResult with success status or error
        """
        log.info(f"Deleting lab {request.lab_id} from worker {request.worker_id}")

        # Get worker to access CML endpoint
        worker = await self._worker_repository.get_by_id_async(request.worker_id)
        if not worker:
            return self.not_found("Worker", f"Worker {request.worker_id} not found")

        # Validate worker has CML endpoint
        if not worker.state.https_endpoint:
            return self.bad_request("Worker does not have HTTPS endpoint configured")

        try:
            # Determine endpoint to use (public or private based on settings)
            endpoint = worker.get_effective_endpoint(self._settings.use_private_ip_for_monitoring)
            if endpoint != worker.state.https_endpoint:
                log.debug(f"Using private IP endpoint for lab deletion: {endpoint}")

            # Create CML API client using factory
            cml_client = self._cml_client_factory.create(base_url=endpoint)

            # Delete lab from CML API
            await cml_client.delete_lab(request.lab_id)
            log.info(f"Lab {request.lab_id} deleted from CML on worker {request.worker_id}")

            # Delete local LabRecord from database for immediate UI consistency
            # Use direct MongoDB deletion instead of aggregate remove_async
            deleted = await self._lab_record_repository.remove_by_lab_id_async(request.worker_id, request.lab_id)
            if deleted:
                log.info(f"Lab record {request.lab_id} removed from database")
            else:
                log.warning(f"Lab record {request.lab_id} not found in database (may not have been synced yet)")

            log.info(f"Successfully deleted lab {request.lab_id} from worker {request.worker_id}")

            # Trigger immediate lab refresh to update UI (with debounce check)
            await self._trigger_lab_refresh(request.worker_id)

            return self.ok({"lab_id": request.lab_id, "message": "Lab deleted successfully"})

        except Exception as e:
            log.error(f"Failed to delete lab {request.lab_id} from worker {request.worker_id}: {e}")
            return self.internal_server_error(f"Failed to delete lab: {str(e)}")

    async def _trigger_lab_refresh(self, worker_id: str) -> None:
        """Trigger immediate lab refresh unless background job is imminent.

        Args:
            worker_id: ID of worker to refresh labs for
        """
        from .refresh_worker_labs_command import RefreshWorkerLabsCommand

        # Check if global LabsRefreshJob is scheduled within threshold
        labs_job = self._scheduler.get_job("LabsRefreshJob")
        if labs_job and labs_job.next_run_time:
            now_utc = datetime.now(timezone.utc)
            next_run_utc = labs_job.next_run_time.replace(tzinfo=timezone.utc)
            time_until_job = (next_run_utc - now_utc).total_seconds()

            if 0 < time_until_job <= self._settings.worker_refresh_check_upcoming_job_threshold:
                log.info(
                    f"Skipping lab refresh after delete for worker {worker_id} - "
                    f"background job scheduled in {time_until_job:.1f}s"
                )
                return

        # Trigger immediate refresh
        log.info(f"Triggering lab refresh after delete for worker {worker_id}")
        try:
            await self._mediator.execute_async(RefreshWorkerLabsCommand(worker_id=worker_id))
        except Exception as e:
            log.warning(f"Failed to trigger lab refresh for worker {worker_id}: {e}")
            # Don't fail the delete operation if refresh fails
