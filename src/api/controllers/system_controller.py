import logging
from typing import Any, List

from classy_fastapi.decorators import delete, get
from fastapi import Depends, HTTPException
from neuroglia.dependency_injection import ServiceProviderBase
from neuroglia.mapping.mapper import Mapper
from neuroglia.mediation.mediator import Mediator
from neuroglia.mvc.controller_base import ControllerBase

from api.dependencies import get_current_user, require_roles

logger = logging.getLogger(__name__)


class SystemController(ControllerBase):
    """Controller for system internals and monitoring endpoints."""

    def __init__(
        self, service_provider: ServiceProviderBase, mapper: Mapper, mediator: Mediator
    ):
        """Initialize System Controller."""
        ControllerBase.__init__(self, service_provider, mapper, mediator)

    @get(
        "/scheduler/jobs",
        response_model=List[dict],
        response_description="List of APScheduler jobs",
        status_code=200,
        responses=ControllerBase.error_responses,
    )
    async def list_scheduler_jobs(
        self,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin", "manager", "user")),
    ) -> Any:
        """List all APScheduler jobs and their status.

        Returns information about background scheduler jobs including:
        - Job ID and name
        - Next run time
        - Trigger type
        - Job status

        (**Requires authenticated user.**)"""
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = (
                self.service_provider.get_required_service(BackgroundTaskScheduler)
            )

            jobs = []
            if scheduler and scheduler._scheduler:
                for job in scheduler._scheduler.get_jobs():
                    jobs.append(
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run_time": (
                                job.next_run_time.isoformat()
                                if job.next_run_time
                                else None
                            ),
                            "trigger": str(job.trigger),
                            "func": f"{job.func.__module__}.{job.func.__name__}",
                            "pending": job.pending,
                        }
                    )

            return jobs
        except Exception as e:
            logger.error(f"Failed to retrieve scheduler jobs: {e}")
            return []

    @delete(
        "/scheduler/jobs/{job_id}",
        response_model=dict,
        response_description="Job deletion result",
        status_code=200,
        responses={
            **ControllerBase.error_responses,
            404: {"description": "Job not found"},
        },
    )
    async def delete_scheduler_job(
        self,
        job_id: str,
        token: str = Depends(get_current_user),
        roles: str = Depends(require_roles("admin")),
    ) -> Any:
        """Delete a scheduled job by ID.

        This endpoint allows administrators to remove background jobs from the scheduler.
        The job will be immediately removed and will not run again.

        (**Requires admin role.**)"""
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = (
                self.service_provider.get_required_service(BackgroundTaskScheduler)
            )

            if not scheduler or not scheduler._scheduler:
                raise HTTPException(
                    status_code=503,
                    detail="Scheduler not available",
                )

            # Check if job exists
            job = scheduler._scheduler.get_job(job_id)
            if not job:
                raise HTTPException(
                    status_code=404,
                    detail=f"Job '{job_id}' not found",
                )

            # Remove the job
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
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete job: {str(e)}",
            )

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
        """Get APScheduler status and statistics.

        (**Requires authenticated user.**)"""
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = (
                self.service_provider.get_required_service(BackgroundTaskScheduler)
            )

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
                            "next_run_time": (
                                job.next_run_time.isoformat()
                                if job.next_run_time
                                else None
                            ),
                        }
                        for job in jobs
                    ],
                }
            else:
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
        """Get worker monitoring service status.

        Returns information about the background job scheduler including:
        - Active background jobs
        - Job count
        - Scheduler running state

        (**Requires authenticated user.**)"""
        try:
            from application.services.background_scheduler import (
                BackgroundTaskScheduler,
            )

            scheduler: BackgroundTaskScheduler = (
                self.service_provider.get_required_service(BackgroundTaskScheduler)
            )

            if scheduler and scheduler._scheduler:
                jobs = scheduler._scheduler.get_jobs()
                return {
                    "status": "active",
                    "scheduler_running": scheduler._scheduler.running,
                    "job_count": len(jobs),
                    "jobs": [
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run_time": (
                                job.next_run_time.isoformat()
                                if job.next_run_time
                                else None
                            ),
                        }
                        for job in jobs
                    ],
                }
            else:
                return {
                    "status": "inactive",
                    "scheduler_running": False,
                    "job_count": 0,
                    "jobs": [],
                }
        except Exception as e:
            logger.error(f"Failed to retrieve background job scheduler status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "scheduler_running": False,
                "job_count": 0,
                "jobs": [],
            }

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
    ) -> Any:
        """Get overall system health status.

        Returns health information about:
        - Database connectivity
        - Redis connectivity
        - Background schedulers
        - Event publishing

        (**Requires valid token.**)"""
        health_status = {
            "status": "healthy",
            "components": {},
        }

        # Check database via mediator (which uses scoped repositories)
        try:
            from application.queries.get_cml_workers_query import GetCMLWorkersQuery
            from integration.enums import AwsRegion

            # Try a simple query to verify database connectivity
            query = GetCMLWorkersQuery(aws_region=AwsRegion.US_EAST_1)
            _ = await self.mediator.execute_async(query)

            health_status["components"]["database"] = {
                "status": "healthy",
                "type": "mongodb",
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e),
            }
            health_status["status"] = "degraded"

        # Check background scheduler
        try:
            from application.services import BackgroundTaskScheduler

            scheduler: BackgroundTaskScheduler = (
                self.service_provider.get_required_service(BackgroundTaskScheduler)
            )
            if scheduler and scheduler._scheduler and scheduler._scheduler.running:
                health_status["components"]["background_scheduler"] = {
                    "status": "healthy",
                    "running": True,
                    "job_count": len(scheduler._scheduler.get_jobs()),
                }
            else:
                health_status["components"]["background_scheduler"] = {
                    "status": "unhealthy",
                    "running": False,
                }
                health_status["status"] = "degraded"
        except Exception as e:
            logger.error(f"Scheduler health check failed: {e}")
            health_status["components"]["background_scheduler"] = {
                "status": "error",
                "error": str(e),
            }
            health_status["status"] = "degraded"

        # Check worker monitoring
        try:
            # Import global monitoring scheduler reference
            from main import _monitoring_scheduler

            monitoring = _monitoring_scheduler
            if monitoring and monitoring._is_running:
                health_status["components"]["worker_monitoring"] = {
                    "status": "healthy",
                    "running": True,
                }
            else:
                health_status["components"]["worker_monitoring"] = {
                    "status": "warning",
                    "running": False,
                }
        except Exception as e:
            logger.error(f"Worker monitoring health check failed: {e}")
            health_status["components"]["worker_monitoring"] = {
                "status": "error",
                "error": str(e),
            }

        return health_status

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
            # Import global monitoring scheduler reference
            from main import _monitoring_scheduler

            monitoring_scheduler = _monitoring_scheduler

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
