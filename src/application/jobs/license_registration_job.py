"""Background job for CML license registration and status polling."""

import asyncio
import logging
from datetime import UTC, datetime

from application.services.background_scheduler import ScheduledBackgroundJob, backgroundjob
from application.settings import app_settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClient

log = logging.getLogger(__name__)


@backgroundjob(task_type="scheduled")
class LicenseRegistrationJob(ScheduledBackgroundJob):
    """Background job to register CML license and poll for completion.

    Process:
    1. POST /licensing/registration (returns 204 immediately)
    2. Poll GET /licensing every 5s for up to 90s
    3. Update worker aggregate with final status
    4. Emit domain event (triggers SSE notification)
    """

    def __init__(
        self,
        worker_id: str,
        license_token: str,
        reregister: bool = False,
        initiated_by: str | None = None,
    ):
        self.worker_id = worker_id
        self.license_token = license_token
        self.reregister = reregister
        self.initiated_by = initiated_by
        self._service_provider = None  # Will be set during configure()

    def __getstate__(self):
        """Custom pickle serialization - exclude unpicklable objects."""
        state = self.__dict__.copy()
        state["_service_provider"] = None
        return state

    def __setstate__(self, state):
        """Custom pickle deserialization - restore state."""
        self.__dict__.update(state)

    def configure(self, service_provider=None, **kwargs):
        """Configure the background job with dependencies.

        This is called by the BackgroundTaskScheduler during job deserialization.

        Args:
            service_provider: Service provider for dependency injection
            **kwargs: Additional configuration parameters
        """
        log.info(f"🔧 Configuring LicenseRegistrationJob for worker {self.worker_id}")
        self._service_provider = service_provider

    async def run_at(self, *args, **kwargs):
        """Entry point for scheduled execution - delegates to execute_async."""
        await self.execute_async(None)

    async def execute_async(self, context) -> None:
        """Execute license registration and polling."""
        if not self._service_provider:
            log.error("Service provider not configured for LicenseRegistrationJob")
            return

        scope = self._service_provider.create_scope()
        repository = scope.get_required_service(CMLWorkerRepository)

        try:
            # Get worker
            worker = await repository.get_by_id_async(self.worker_id)
            if not worker:
                log.error(f"Worker {self.worker_id} not found for license registration")
                return

            # Check worker has CML host
            if not worker.state.public_ip:
                log.error(f"Worker {self.worker_id} does not have public IP (not reachable)")
                return

            # Create CML API client
            cml_client = CMLApiClient(
                base_url=f"https://{worker.state.public_ip}",
                username=app_settings.cml_worker_api_username,
                password=app_settings.cml_worker_api_password,
                verify_ssl=app_settings.cml_worker_api_verify_ssl,
                timeout=30.0,
            )

            # Start registration
            log.info(f"🔐 Starting license registration for worker {self.worker_id} " f"(reregister={self.reregister})")

            started_at = datetime.now(UTC)

            # Emit started event
            worker.start_license_registration(
                started_at=started_at.isoformat(),
                initiated_by=self.initiated_by,
            )
            await repository.update_async(worker)

            # Call registration API
            try:
                await cml_client.register_license(self.license_token, self.reregister)
            except Exception as e:
                log.error(f"License registration API call failed: {e}")
                worker.fail_license_registration(
                    error_message=str(e),
                    failed_at=datetime.now(UTC).isoformat(),
                )
                await repository.update_async(worker)
                return

            # Poll for completion (max 90 seconds, poll every 5 seconds)
            max_attempts = 18  # 18 * 5s = 90s
            poll_interval = 5.0

            for attempt in range(max_attempts):
                await asyncio.sleep(poll_interval)

                try:
                    license_info = await cml_client.get_licensing()
                    if not license_info:
                        log.warning(f"Could not fetch licensing info (attempt {attempt + 1}/{max_attempts})")
                        continue

                    reg_status = license_info.registration_status

                    log.debug(
                        f"License registration status for worker {self.worker_id}: "
                        f"{reg_status} (attempt {attempt + 1}/{max_attempts})"
                    )

                    # Check for completion
                    if reg_status == "COMPLETED":
                        elapsed = (datetime.now(UTC) - started_at).total_seconds()
                        log.info(f"✅ License registration completed for worker {self.worker_id} " f"in {elapsed:.1f}s")

                        worker.complete_license_registration(
                            registration_status=reg_status,
                            smart_account=license_info.smart_account,
                            virtual_account=license_info.virtual_account,
                            completed_at=datetime.now(UTC).isoformat(),
                        )
                        await repository.update_async(worker)
                        return

                    # Check for failure
                    elif reg_status in ["FAILED", "EXPIRED", "RETRY_FAILED"]:
                        log.error(f"❌ License registration failed for worker {self.worker_id}: " f"{reg_status}")

                        worker.fail_license_registration(
                            error_message=f"Registration failed with status: {reg_status}",
                            failed_at=datetime.now(UTC).isoformat(),
                        )
                        await repository.update_async(worker)
                        return

                    # Still in progress (PENDING, IN_PROGRESS, etc.)
                    # Continue polling

                except Exception as e:
                    log.warning(f"Error polling license status (attempt {attempt + 1}): {e}")
                    continue

            # Timeout - registration took too long
            log.error(
                f"⏱️ License registration timeout for worker {self.worker_id} "
                f"(exceeded {max_attempts * poll_interval}s)"
            )

            worker.fail_license_registration(
                error_message=f"Registration timeout (exceeded {max_attempts * poll_interval}s)",
                failed_at=datetime.now(UTC).isoformat(),
            )
            await repository.update_async(worker)

        except Exception as e:
            log.error(f"License registration job failed for worker {self.worker_id}: {e}")
            log.error(f"License registration job failed for worker {self.worker_id}: {e}")
