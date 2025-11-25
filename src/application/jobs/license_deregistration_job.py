"""Background job for CML license deregistration."""

import logging
from datetime import UTC, datetime

from application.services.background_scheduler import ScheduledBackgroundJob, backgroundjob
from application.settings import app_settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClientFactory

log = logging.getLogger(__name__)


@backgroundjob(task_type="scheduled")
class LicenseDeregistrationJob(ScheduledBackgroundJob):
    """Background job to deregister CML license.

    Process:
    1. DELETE /licensing/deregistration (can take 10-60s)
    2. Update worker aggregate with final status
    3. Emit domain event (triggers SSE notification)
    """

    def __init__(
        self,
        worker_id: str,
        initiated_by: str | None = None,
    ):
        self.worker_id = worker_id
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
        log.info(f"🔧 Configuring LicenseDeregistrationJob for worker {self.worker_id}")
        self._service_provider = service_provider

    async def run_at(self, *args, **kwargs):
        """Entry point for scheduled execution - delegates to execute_async."""
        await self.execute_async(None)

    async def execute_async(self, context) -> None:
        """Execute license deregistration."""
        if not self._service_provider:
            log.error("Service provider not configured for LicenseDeregistrationJob")
            return

        scope = self._service_provider.create_scope()
        repository = scope.get_required_service(CMLWorkerRepository)
        cml_client_factory = scope.get_required_service(CMLApiClientFactory)

        try:
            # Get worker
            worker = await repository.get_by_id_async(self.worker_id)
            if not worker:
                log.error(f"Worker {self.worker_id} not found for license deregistration")
                return

            # Determine endpoint to use
            endpoint = worker.get_effective_endpoint(app_settings.use_private_ip_for_monitoring)

            # Check worker has reachable endpoint
            if not endpoint:
                log.error(f"Worker {self.worker_id} does not have reachable IP/endpoint")
                worker.fail_license_deregistration(
                    error_message="Worker does not have reachable IP/endpoint",
                    failed_at=datetime.now(UTC).isoformat(),
                )
                await repository.update_async(worker)
                return

            # Create CML API client using factory
            cml_client = cml_client_factory.create(base_url=endpoint)

            # Start deregistration
            log.info(f"🔓 Starting license deregistration for worker {self.worker_id}")

            started_at = datetime.now(UTC)

            # Emit started event
            worker.start_license_deregistration(
                started_at=started_at.isoformat(),
                initiated_by=self.initiated_by,
            )
            await repository.update_async(worker)

            # Call deregistration API (can take 10-60s)
            try:
                success, message = await cml_client.deregister_license()

                if success:
                    elapsed = (datetime.now(UTC) - started_at).total_seconds()
                    log.info(f"✅ License deregistration completed for worker {self.worker_id} in {elapsed:.1f}s")

                    # Mark deregistration as completed
                    worker.complete_license_deregistration(
                        message=message,
                        completed_at=datetime.now(UTC).isoformat(),
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

                    await repository.update_async(worker)
                else:
                    # Already deregistered or failed
                    log.error(f"❌ License deregistration failed for worker {self.worker_id}: {message}")
                    worker.fail_license_deregistration(
                        error_message=message,
                        failed_at=datetime.now(UTC).isoformat(),
                    )
                    await repository.update_async(worker)

            except Exception as e:
                log.error(f"License deregistration API call failed: {e}")
                worker.fail_license_deregistration(
                    error_message=str(e),
                    failed_at=datetime.now(UTC).isoformat(),
                )
                await repository.update_async(worker)

        except Exception as e:
            log.error(f"License deregistration job failed for worker {self.worker_id}: {e}", exc_info=True)
