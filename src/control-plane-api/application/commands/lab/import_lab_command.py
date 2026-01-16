"""Import Lab Command - uploads and imports lab topology from YAML."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from neuroglia.core.operation_result import OperationResult
from neuroglia.mediation import Command, CommandHandler, Mediator

from application.services.background_scheduler import BackgroundTaskScheduler
from application.settings import Settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClientFactory

log = logging.getLogger(__name__)


@dataclass
class ImportLabCommand(Command[OperationResult[dict]]):
    """Command to import a lab topology from YAML.

    Attributes:
        worker_id: Worker ID to import the lab to
        yaml_content: Lab topology in CML2 YAML format
        title: Optional title for the imported lab (overrides YAML title)
    """

    worker_id: str
    yaml_content: str
    title: str | None = None


class ImportLabCommandHandler(CommandHandler[ImportLabCommand, OperationResult[dict]]):
    """Handler for ImportLabCommand - imports lab YAML to CML worker."""

    def __init__(
        self,
        mediator: Mediator,
        worker_repository: CMLWorkerRepository,
        cml_api_client_factory: CMLApiClientFactory,
        background_task_scheduler: BackgroundTaskScheduler,
        settings: Settings,
    ):
        """Initialize handler with repository dependencies.

        Args:
            mediator: Mediator for triggering other commands
            worker_repository: Repository for accessing CML worker data
            cml_api_client_factory: Factory for creating CML API clients
            background_task_scheduler: Scheduler for checking background jobs
            settings: Application settings
        """
        self._mediator = mediator
        self._worker_repository = worker_repository
        self._cml_client_factory = cml_api_client_factory
        self._scheduler = background_task_scheduler
        self._settings = settings

    async def handle_async(self, request: ImportLabCommand) -> OperationResult[dict]:
        """Import lab topology to CML worker.

        Args:
            request: Command containing worker_id, yaml_content, and optional title

        Returns:
            OperationResult containing lab_id and title or error
        """
        log.info(f"Importing lab to worker {request.worker_id}")

        # Get worker to access CML endpoint
        worker = await self._worker_repository.get_by_id_async(request.worker_id)
        if not worker:
            return self.not_found("Worker", f"Worker {request.worker_id} not found")

        # Validate worker has CML endpoint
        if not worker.state.https_endpoint:
            return self.bad_request("Worker does not have HTTPS endpoint configured")

        # Validate YAML content
        if not request.yaml_content or not request.yaml_content.strip():
            return self.bad_request("YAML content is required")

        try:
            # Determine endpoint to use (public or private based on settings)
            endpoint = worker.get_effective_endpoint(self._settings.use_private_ip_for_monitoring)
            if endpoint != worker.state.https_endpoint:
                log.debug(f"Using private IP endpoint for lab import: {endpoint}")

            # Create CML API client using factory
            cml_client = self._cml_client_factory.create(base_url=endpoint)

            # Import lab YAML
            result = await cml_client.import_lab(request.yaml_content, request.title)

            lab_id = result.get("id")
            log.info(f"Successfully imported lab {lab_id} to worker {request.worker_id}")

            # Trigger immediate lab refresh to update UI (with debounce check)
            await self._trigger_lab_refresh(request.worker_id)

            return self.ok(
                {
                    "lab_id": lab_id,
                    "title": request.title or result.get("title", "Imported Lab"),
                    "message": "Lab imported successfully",
                }
            )

        except Exception as e:
            log.error(f"Failed to import lab to worker {request.worker_id}: {e}")
            return self.internal_server_error(f"Failed to import lab: {str(e)}")

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
                    f"Skipping lab refresh after import for worker {worker_id} - "
                    f"background job scheduled in {time_until_job:.1f}s"
                )
                return

        # Trigger immediate refresh
        log.info(f"Triggering lab refresh after import for worker {worker_id}")
        try:
            await self._mediator.execute_async(RefreshWorkerLabsCommand(worker_id=worker_id))
        except Exception as e:
            log.warning(f"Failed to trigger lab refresh for worker {worker_id}: {e}")
            # Don't fail the import operation if refresh fails
