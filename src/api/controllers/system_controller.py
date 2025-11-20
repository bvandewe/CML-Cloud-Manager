import logging
from typing import Any

from classy_fastapi.decorators import delete, get, post
from fastapi import Depends, HTTPException
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles

logger = logging.getLogger(__name__)


class SystemController(ControllerBase):
    """Controller for system internals and monitoring endpoints."""

    # Class-level prefix so decorators pick it up reliably
    prefix = "system"

    def __init__(self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator):
        ControllerBase.__init__(self, service_provider, mapper, mediator)

    @get(
        "/scheduler/jobs",
        response_model=list[dict],
        response_description="List of APScheduler jobs",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def list_scheduler_jobs(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)

            jobs: list[dict] = []
            if scheduler and scheduler._scheduler:
                for job in scheduler._scheduler.get_jobs():
                    command_name = (
                        job.kwargs.get("task_type_name", "N/A")
                        if hasattr(job, "kwargs") and job.kwargs
                        else job.name or "N/A"
                    )
                    jobs.append(
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
                            "trigger": str(job.trigger),
                            "command": command_name,
                            "pending": job.pending,
                        }
                    )
            return jobs
        except Exception as e:
            logger.error(f"Failed to retrieve scheduler jobs: {e}")
            return []

    @post(
        "/scheduler/jobs/{job_id}/trigger",
        response_model=dict,
        response_description="Job trigger result",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def trigger_scheduler_job(
        self,
        job_id: str,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin")),
    ) -> Any:
        """Trigger an existing scheduled job to run immediately.

        This endpoint allows administrators to manually trigger a background job
        without waiting for its scheduled time. The job will run immediately while
        maintaining its original schedule for future executions.

        (**Requires `admin` role!**)
        """
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
            if not scheduler or not scheduler._scheduler:
                raise HTTPException(status_code=503, detail="Scheduler not available")

            job = scheduler._scheduler.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

            # Trigger the job to run now
            await scheduler.trigger_job_now(job_id)

            logger.info(f"Job '{job_id}' triggered manually by admin")
            return {
                "success": True,
                "message": f"Job '{job_id}' ({job.name}) triggered successfully",
                "job_id": job_id,
                "job_name": job.name,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to trigger job '{job_id}': {e}")
            raise HTTPException(status_code=500, detail=f"Failed to trigger job: {str(e)}")

    @delete(
        "/scheduler/jobs/{job_id}",
        response_model=dict,
        response_description="Job deletion result",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def delete_scheduler_job(
        self,
        job_id: str,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin")),
    ) -> Any:
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
            if not scheduler or not scheduler._scheduler:
                raise HTTPException(status_code=503, detail="Scheduler not available")
            job = scheduler._scheduler.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
            scheduler._scheduler.remove_job(job_id)
            logger.info(f"Job '{job_id}' deleted successfully by user")
            return {
                "success": True,
                "message": f"Job '{job_id}' deleted successfully",
                "job_id": job_id,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete job '{job_id}': {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")

    @get(
        "/health",
        response_model=dict,
        response_description="System health status",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_system_health(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        """Return aggregated system health using `SystemHealthService`."""
        from application.services.system_health_service import SystemHealthService

        svc: SystemHealthService = self.service_provider.get_required_service(SystemHealthService)
        return await svc.get_system_health(self.mediator, self.service_provider)

    @get(
        "/scheduler/status",
        response_model=dict,
        response_description="APScheduler status",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_scheduler_status(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
            if scheduler and scheduler._scheduler:
                jobs = scheduler._scheduler.get_jobs()
                return {
                    "running": scheduler._scheduler.running,
                    "state": scheduler._scheduler.state,
                    "job_count": len(jobs),
                    "jobs": [
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
                        }
                        for job in jobs
                    ],
                }
            return {
                "running": False,
                "state": "NOT_INITIALIZED",
                "job_count": 0,
                "jobs": [],
            }
        except Exception as e:
            logger.error(f"Failed to retrieve scheduler status: {e}")
            return {
                "running": False,
                "state": "ERROR",
                "error": str(e),
                "job_count": 0,
                "jobs": [],
            }

    @get(
        "/monitoring/workers",
        response_model=dict,
        response_description="Worker monitoring status",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_worker_monitoring_status(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        try:
            try:
                from main import _monitoring_scheduler  # type: ignore

                monitoring_scheduler = _monitoring_scheduler
            except Exception:
                monitoring_scheduler = None
            if monitoring_scheduler and monitoring_scheduler._is_running:
                collectors = [
                    {
                        "worker_id": worker_id,
                        "job_id": job_id,
                        "status": "active",
                        "interval": f"{monitoring_scheduler._poll_interval}s",
                    }
                    for worker_id, job_id in monitoring_scheduler._active_jobs.items()
                ]
                return {
                    "collectors": collectors,
                    "total_collectors": len(collectors),
                    "active_collectors": len(collectors),
                    "poll_interval": monitoring_scheduler._poll_interval,
                }
            return {
                "collectors": [],
                "total_collectors": 0,
                "active_collectors": 0,
                "poll_interval": 0,
                "message": "Worker monitoring is not running",
            }
        except Exception as e:
            logger.error(f"Failed to retrieve metrics collectors status: {e}")
            return {
                "collectors": [],
                "total_collectors": 0,
                "active_collectors": 0,
                "poll_interval": 0,
                "error": str(e),
            }

    @get(
        "/metrics/collectors",
        response_model=dict,
        response_description="Metrics collectors status",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def get_metrics_collectors_status(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        """Get status of all metrics collectors.

        Returns information about:
        - Active collectors (one per worker)
        - Collection intervals
        - Worker details

        Note: There is one collector per CML Worker being monitored.

        (**Requires authenticated user.**)"""
        try:
            # Optional monitoring scheduler (may not be configured)
            try:
                from main import _monitoring_scheduler  # type: ignore

                monitoring_scheduler = _monitoring_scheduler
            except Exception:
                monitoring_scheduler = None

            if monitoring_scheduler and monitoring_scheduler._is_running:
                # Get active monitoring jobs - one collector per worker
                collectors = []

                for worker_id, job_id in monitoring_scheduler._active_jobs.items():
                    collectors.append(
                        {
                            "worker_id": worker_id,
                            "job_id": job_id,
                            "status": "active",
                            "interval": f"{monitoring_scheduler._poll_interval}s",
                        }
                    )

                return {
                    "collectors": collectors,
                    "total_collectors": len(collectors),
                    "active_collectors": len(collectors),
                    "poll_interval": monitoring_scheduler._poll_interval,
                }
            else:
                return {
                    "collectors": [],
                    "total_collectors": 0,
                    "active_collectors": 0,
                    "poll_interval": 0,
                    "message": "Worker monitoring is not running",
                }
        except Exception as e:
            logger.error(f"Failed to retrieve metrics collectors status: {e}")
            return {
                "collectors": [],
                "total_collectors": 0,
                "active_collectors": 0,
                "poll_interval": 0,
                "error": str(e),
            }
