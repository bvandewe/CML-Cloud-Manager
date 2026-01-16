"""Diagnostics API controller exposing background job intervals and next run times."""

import logging

from classy_fastapi.decorators import get
from fastapi import Depends
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping import Mapper
from neuroglia.mediation import Mediator
from neuroglia.mvc import ControllerBase

from api.dependencies import get_current_user, require_roles
from application.services.background_scheduler import BackgroundTaskScheduler
from application.settings import app_settings

log = logging.getLogger(__name__)


class DiagnosticsController(ControllerBase):
    """Controller providing operational diagnostics for background jobs and intervals."""

    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
        super().__init__(service_provider, mapper, mediator)
        # Prefix override to serve under /api/diagnostics
        self.prefix = "diagnostics"

    @get("/intervals")
    async def get_intervals(self, user: dict = Depends(get_current_user)):
        """Return configured polling intervals and next run times for recurrent jobs.

        Authentication: session cookie or bearer token; RBAC optional (allow all authenticated users).
        """
        scheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
        jobs = scheduler.list_tasks() if scheduler else []
        job_summaries = []
        for job in jobs:
            try:
                job_summaries.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
                        "trigger": str(job.trigger),
                        "interval_seconds": job.kwargs.get("interval"),
                    }
                )
            except Exception:
                log.warning(f"Failed to summarize job {job.id}", exc_info=True)

        return {
            "settings": {
                "worker_metrics_poll_interval": app_settings.worker_metrics_poll_interval,
                "labs_refresh_interval": getattr(app_settings, "labs_refresh_interval", None),
                "auto_import_workers_interval": getattr(app_settings, "auto_import_workers_interval", None),
            },
            "jobs": job_summaries,
        }

    @get("/jobs")
    async def list_jobs(self, user: dict = Depends(require_roles("admin", "manager"))):
        """List raw APScheduler job details (RBAC protected)."""
        scheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
        jobs = scheduler.list_tasks() if scheduler else []
        detailed = []
        for job in jobs:
            detailed.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
                    "trigger": str(job.trigger),
                    "args": job.args,
                    "kwargs": job.kwargs,
                }
            )
        return {"jobs": detailed}
