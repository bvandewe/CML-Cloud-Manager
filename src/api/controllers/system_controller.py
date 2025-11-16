import logging
from typing import Any, List

from classy_fastapi.decorators import get
from fastapi import Depends
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
        roles: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """List all APScheduler jobs and their status.

        Returns information about background scheduler jobs including:
        - Job ID and name
        - Next run time
        - Trigger type
        - Job status

        (**Requires admin or manager role.**)"""
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
        roles: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Get APScheduler status and statistics.

        (**Requires admin or manager role.**)"""
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
        roles: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Get worker monitoring service status.

        Returns information about the worker monitoring scheduler including:
        - Active monitoring jobs
        - Monitored workers count
        - Last update times

        (**Requires admin or manager role.**)"""
        try:
            from application.services import WorkerMonitoringScheduler

            monitoring_scheduler: WorkerMonitoringScheduler = (
                self.service_provider.get_required_service(WorkerMonitoringScheduler)
            )

            if monitoring_scheduler and monitoring_scheduler._scheduler:
                jobs = monitoring_scheduler._scheduler.get_jobs()
                return {
                    "status": "active",
                    "scheduler_running": monitoring_scheduler._scheduler.running,
                    "monitoring_job_count": len(jobs),
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
                    "monitoring_job_count": 0,
                    "jobs": [],
                }
        except Exception as e:
            logger.error(f"Failed to retrieve worker monitoring status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "scheduler_running": False,
                "monitoring_job_count": 0,
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

        # Check database
        try:
            from domain.repositories.cml_worker_repository import CMLWorkerRepository

            repo: CMLWorkerRepository = self.service_provider.get_required_service(
                CMLWorkerRepository
            )
            # Simple check - try to count documents
            await repo.collection.count_documents({}, limit=1)
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
            from application.services import WorkerMonitoringScheduler

            monitoring: WorkerMonitoringScheduler = (
                self.service_provider.get_required_service(WorkerMonitoringScheduler)
            )
            if monitoring and monitoring._scheduler and monitoring._scheduler.running:
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
        roles: str = Depends(require_roles("admin", "manager")),
    ) -> Any:
        """Get status of all metrics collectors.

        Returns information about:
        - Active collectors
        - Collection intervals
        - Last collection times
        - Error counts

        (**Requires admin or manager role.**)"""
        # Placeholder for metrics collectors
        # This would integrate with your actual metrics collection system
        return {
            "collectors": [
                {
                    "name": "worker_metrics_collector",
                    "status": "active",
                    "interval": "60s",
                    "last_collection": None,
                    "error_count": 0,
                },
                {
                    "name": "resource_utilization_collector",
                    "status": "active",
                    "interval": "300s",
                    "last_collection": None,
                    "error_count": 0,
                },
            ],
            "total_collectors": 2,
            "active_collectors": 2,
        }
