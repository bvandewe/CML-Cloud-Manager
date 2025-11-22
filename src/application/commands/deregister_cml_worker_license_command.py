"""Deregister CML Worker license command and handler."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from neuroglia.core import OperationResult
from neuroglia.mediation.mediator import Command, CommandHandler

from application.settings import app_settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClient

log = logging.getLogger(__name__)


@dataclass
class DeregisterCMLWorkerLicenseCommand(Command[OperationResult[dict]]):
    """Command to deregister a CML Worker license.

    Deregistration is typically faster than registration (< 10s),
    so we handle it synchronously instead of background job.
    """

    worker_id: str
    initiated_by: str | None = None


class DeregisterCMLWorkerLicenseCommandHandler(
    CommandHandler[DeregisterCMLWorkerLicenseCommand, OperationResult[dict]]
):
    """Handler for DeregisterCMLWorkerLicenseCommand."""

    def __init__(self, worker_repository: CMLWorkerRepository):
        self._repository = worker_repository

    async def handle_async(
        self,
        request: DeregisterCMLWorkerLicenseCommand,
    ) -> OperationResult[dict]:
        """Handle license deregistration command.

        Deregistration is typically fast (<10s), so we do it synchronously.
        """
        # Get worker
        worker = await self._repository.get_by_id_async(request.worker_id)
        if not worker:
            return self.not_found("Worker", f"Worker {request.worker_id} not found")

        # Check worker is accessible
        if not worker.state.public_ip:
            return self.bad_request("Worker does not have public IP (not reachable)")

        # Create CML API client
        cml_client = CMLApiClient(
            base_url=f"https://{worker.state.public_ip}",
            username=app_settings.cml_worker_api_username,
            password=app_settings.cml_worker_api_password,
            verify_ssl=app_settings.cml_worker_api_verify_ssl,
            timeout=60.0,
        )

        try:
            # Call deregister API (can take 10-60s)
            success, message = await cml_client.deregister_license()

            if success:
                # Update worker with deregistration event
                # The @dispatch handler will clear cml_license_info and update cml_system_health
                worker.deregister_license(
                    deregistered_at=datetime.now(UTC).isoformat(),
                    initiated_by=request.initiated_by,
                )

                # Fetch full system state to persist license info and health
                try:
                    sys_stats = await cml_client.get_system_stats()
                    sys_health = await cml_client.get_system_health()
                    sys_info = await cml_client.get_system_information()
                    license_info = await cml_client.get_licensing()

                    if sys_stats and sys_health and sys_info and license_info:
                        worker.update_cml_metrics(
                            cml_version=sys_info.version,
                            system_info=sys_stats.__dict__,
                            system_health=sys_health.__dict__,
                            license_info=license_info.raw_data,
                            ready=sys_info.ready,
                            uptime_seconds=worker.state.metrics.uptime_seconds,
                            labs_count=worker.state.metrics.labs_count,
                            synced_at=datetime.now(UTC),
                            change_threshold_percent=0.0,  # Force update
                        )
                except Exception as e:
                    log.warning(f"Failed to fetch post-deregistration metrics: {e}")

                await self._repository.update_async(worker)

                log.info(f"✅ Successfully deregistered license for worker {request.worker_id}")

                return self.ok(
                    {
                        "message": message,
                        "worker_id": request.worker_id,
                        "deregistered_at": datetime.now(UTC).isoformat(),
                    }
                )
            else:
                # Already deregistered or failed
                return self.bad_request(message)

        except Exception as e:
            log.error(f"Failed to deregister license for worker {request.worker_id}: {e}")
            return self.internal_server_error(f"Deregistration failed: {e}")
