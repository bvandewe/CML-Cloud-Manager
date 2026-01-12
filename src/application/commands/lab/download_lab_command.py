"""Download Lab YAML Command - retrieves lab topology in YAML format."""

import logging
from dataclasses import dataclass

from neuroglia.core.operation_result import OperationResult
from neuroglia.mediation import Command, CommandHandler

from application.settings import Settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClientFactory

log = logging.getLogger(__name__)


@dataclass
class DownloadLabCommand(Command[OperationResult[str]]):
    """Command to download a lab's topology as YAML."""

    worker_id: str
    lab_id: str


class DownloadLabCommandHandler(CommandHandler[DownloadLabCommand, OperationResult[str]]):
    """Handler for DownloadLabCommand - retrieves lab YAML from CML API."""

    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        cml_api_client_factory: CMLApiClientFactory,
        settings: Settings,
    ):
        """Initialize handler with repository dependencies.

        Args:
            worker_repository: Repository for accessing CML worker data
            cml_api_client_factory: Factory for creating CML API clients
            settings: Application settings
        """
        self._worker_repository = worker_repository
        self._cml_client_factory = cml_api_client_factory
        self._settings = settings

    async def handle_async(self, request: DownloadLabCommand, cancellation_token=None) -> OperationResult[str]:
        """Download lab topology as YAML.

        Args:
            request: Command containing worker_id and lab_id
            cancellation_token: Optional cancellation token

        Returns:
            OperationResult containing YAML string or error
        """
        log.info(f"Downloading lab {request.lab_id} from worker {request.worker_id}")

        # Get worker to access CML credentials
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
                log.debug(f"Using private IP endpoint for lab download: {endpoint}")

            # Create CML API client using factory
            cml_client = self._cml_client_factory.create(base_url=endpoint)

            # Download lab YAML
            yaml_content = await cml_client.download_lab(request.lab_id)

            log.info(f"Successfully downloaded lab {request.lab_id} ({len(yaml_content)} bytes)")
            return self.ok(yaml_content)

        except Exception as e:
            log.error(f"Failed to download lab {request.lab_id}: {e}")
            return self.internal_server_error(f"Failed to download lab: {str(e)}")
