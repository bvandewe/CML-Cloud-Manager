from __future__ import annotations

"""
Background task scheduling infrastructure for the Neuroglia framework.

This module provides comprehensive background task scheduling capabilities using
APScheduler with Redis persistence and support for both scheduled (one-time)
and recurrent background jobs.
"""

import contextvars
import datetime
import inspect
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from neuroglia.core import ModuleLoader, TypeFinder

from application.settings import app_settings

# Import APScheduler components

try:
    from apscheduler.jobstores.redis import RedisJobStore
except ImportError:
    RedisJobStore = None

try:
    from apscheduler.jobstores.mongodb import MongoDBJobStore
except ImportError:
    MongoDBJobStore = None

try:
    from apscheduler.executors.asyncio import AsyncIOExecutor
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    # APScheduler is an optional dependency
    AsyncIOExecutor = None
    AsyncIOScheduler = None

if TYPE_CHECKING:
    from neuroglia.hosting.abstractions import HostedService
    from neuroglia.hosting.web import WebApplicationBuilder
else:
    # Avoid circular imports
    try:
        from neuroglia.hosting.abstractions import ApplicationBuilderBase, HostedService
    except ImportError:
        ApplicationBuilderBase = None
        HostedService = None

log = logging.getLogger(__name__)

# Context variable for service provider in background jobs
# This is thread-safe and async-safe, unlike global variables
_service_provider_context: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "service_provider", default=None
)

# Global scheduler instance for access in job wrappers
_global_scheduler_instance: Optional["BackgroundTaskScheduler"] = None


class BackgroundTaskException(Exception):
    """Exception raised by background task operations."""


def backgroundjob(
    task_type: str | None = None,
    interval: int | None = None,
    scheduled_at: datetime.datetime | None = None,
):
    """Marks a class as a background task for the BackgroundTaskScheduler.

    Args:
        task_type: "scheduled" for one-time or "recurrent" for recurring
        interval: Interval in seconds (recurrent only)
        scheduled_at: Datetime for one-time jobs
    """

    def decorator(cls):
        cls.__background_task_class_name__ = cls.__name__
        cls.__background_task_type__ = task_type if task_type in ("scheduled", "recurrent") else None
        if interval is not None:
            cls.__interval__ = interval
        # If interval is not provided but task_type is recurrent, try to get it from app_settings dynamically
        elif task_type == "recurrent" and not hasattr(cls, "__interval__"):
            # This handles cases where interval is passed as a variable (like app_settings.foo)
            # but the decorator receives the value at import time.
            # If the value was None/0 at import time, we might need to re-evaluate or warn.
            pass

        if scheduled_at is not None:
            cls.__scheduled_at__ = scheduled_at
        return cls

    return decorator


class BackgroundJob(ABC):
    """Defines the fundamentals of a background job."""

    __background_task_type__: str | None = None
    __task_id__: str | None = None
    __task_name__: str | None = None
    __task_type__: str | None = None

    @abstractmethod
    def configure(self, *args, **kwargs):
        """Configure the background job with necessary dependencies and parameters."""


class ScheduledBackgroundJob(BackgroundJob, ABC):
    """Defines the fundamentals of a scheduled background job."""

    __scheduled_at__: datetime.datetime | None = None

    @abstractmethod
    async def run_at(self, *args, **kwargs):
        """Execute the scheduled job at the specified time."""


class RecurrentBackgroundJob(BackgroundJob, ABC):
    """Defines the fundamentals of a recurrent background job."""

    __interval__: int | None = None

    @abstractmethod
    async def run_every(self, *args, **kwargs):
        """Execute the recurrent job at each interval."""


@dataclass
class TaskDescriptor:
    """Represents the description of a task that will be passed through the bus."""

    id: str
    name: str
    data: dict


@dataclass
class ScheduledTaskDescriptor(TaskDescriptor):
    """Represents a serialized description of a scheduled task."""

    scheduled_at: datetime.datetime


@dataclass
class RecurrentTaskDescriptor(TaskDescriptor):
    """Represents a serialized description of a recurrent task."""

    interval: int
    started_at: datetime.datetime | None = None


class BackgroundTaskSchedulerOptions:
    """Represents the configuration options for the background task scheduler."""

    def __init__(self, modules: list[str] | None = None):
        """Initialize with an empty type mapping.

        Args:
            modules: List of module paths to scan for @backgroundjob decorators (e.g., ['application.jobs'])
        """
        self.type_maps: dict[str, type] = {}
        self.modules: list[str] = modules or ["application.services"]  # Default for backward compatibility

    def register_task_type(self, name: str, task_type: type) -> None:
        """Register a task type with the scheduler."""
        self.type_maps[name] = task_type
        log.debug(f"Registered background task type '{name}': {task_type}")

    def get_task_type(self, name: str) -> type | None:
        """Get a task type by name."""
        return self.type_maps.get(name)


async def scheduled_job_wrapper(
    task_type_name: str,
    task_id: str,
    task_data: Dict[str, Any],
    scheduled_at: datetime.datetime,
    **kwargs: Any,
) -> Any:
    """Wrapper function for scheduled (one-time) jobs.

    This wrapper reconstructs the task from minimal serialized data.
    Tasks must implement their own dependency reconstruction in configure()
    without relying on unpicklable service providers.

    Args:
        task_type_name: Name of the task type to instantiate
        task_id: Unique ID for this task instance
        task_data: Serialized task data (minimal attributes only)
        scheduled_at: When the task was scheduled to run
        **kwargs: Additional keyword arguments passed to the task
    """
    try:
        # Reconstruct task directly - no service provider needed
        # Each worker will execute this independently

        # Create a temporary options instance to access registered task types
        # Get service provider from global scheduler instance (works across threads)
        service_provider = None
        if _global_scheduler_instance:
            service_provider = _global_scheduler_instance._service_provider
        elif _service_provider_context.get():
            service_provider = _service_provider_context.get()

        if service_provider:
            try:
                scheduler_options = service_provider.get_service(BackgroundTaskSchedulerOptions)
                modules = (
                    scheduler_options.modules if scheduler_options else ["application.services", "application.jobs"]
                )
            except:
                modules = ["application.services", "application.jobs"]
        else:
            modules = ["application.services", "application.jobs"]

        options = BackgroundTaskSchedulerOptions(modules=modules)

        # Re-scan for registered tasks (they're registered via @backgroundjob decorator)
        import inspect

        from neuroglia.core import ModuleLoader, TypeFinder

        for module_name in modules:
            try:
                module = ModuleLoader.load(module_name)
                background_tasks = TypeFinder.get_types(
                    module,
                    lambda cls: inspect.isclass(cls) and hasattr(cls, "__background_task_class_name__"),
                )

                for background_task in background_tasks:
                    task_name = background_task.__background_task_class_name__
                    options.register_task_type(task_name, background_task)
            except Exception as e:
                log.debug(f"Could not scan module '{module_name}' in scheduled_job_wrapper: {e}")
                continue

        task_type = options.get_task_type(task_type_name)
        if not task_type:
            raise BackgroundTaskException(f"Task type '{task_type_name}' not registered")

        # Create new instance without calling __init__
        task: ScheduledBackgroundJob = object.__new__(task_type)

        # Restore task state
        task.__dict__.update(task_data)
        task.__task_id__ = task_id
        task.__task_name__ = task_type_name
        task.__task_type__ = "ScheduledTaskDescriptor"
        task.__scheduled_at__ = scheduled_at

        # Let the task configure its own dependencies
        # Get service provider from global scheduler instance (works across threads)
        service_provider = None
        if _global_scheduler_instance:
            service_provider = _global_scheduler_instance._service_provider
        elif _service_provider_context.get():
            service_provider = _service_provider_context.get()
        if hasattr(task, "configure"):
            task.configure(service_provider=service_provider)

        log.debug(f"Executing scheduled job: {task.__task_name__} (ID: {task.__task_id__})")
        return await task.run_at(**kwargs)
    except Exception as ex:
        log.error(f"Error executing scheduled job {task_type_name}: {ex}", exc_info=True)
        raise


async def recurrent_job_wrapper(
    task_type_name: Optional[str],
    task_id: str,
    task_data: Dict[str, Any],
    interval: int,
    **kwargs: Any,
) -> Any:
    """Wrapper function for recurrent jobs.

    Args:
        task_type_name: Name of the task type to instantiate
        task_id: Unique ID for this task instance
        task_data: Serialized task data (minimal attributes only)
        interval: Interval in seconds between executions
        **kwargs: Additional keyword arguments passed to the task
    """
    try:
        # Reconstruct task directly - no service provider needed
        # Each worker will execute this independently

        # Resolve task type without rescanning modules: use scheduler options map directly
        options = _global_scheduler_instance._options if _global_scheduler_instance else None
        if options is None:
            raise BackgroundTaskException("Scheduler options unavailable in recurrent_job_wrapper")

        original_name = task_type_name

        # 1. Direct name provided
        task_type = options.get_task_type(task_type_name) if task_type_name else None

        # 2. Fallback to serialized class name
        if not task_type:
            serialized_name = task_data.get("background_task_class_name")
            if isinstance(serialized_name, str) and serialized_name:
                task_type = options.get_task_type(serialized_name)
                if task_type:
                    task_type_name = serialized_name

        # 3. Match by registered class metadata
        if not task_type:
            serialized_name = task_data.get("background_task_class_name")
            if isinstance(serialized_name, str) and serialized_name:
                for registered_name, registered_cls in options.type_maps.items():
                    if getattr(registered_cls, "__background_task_class_name__", None) == serialized_name:
                        task_type = registered_cls
                        task_type_name = registered_name
                        break

        # 4. Derive from job id prefix (jobs are created as <Name>-<uuid>)
        if not task_type and isinstance(task_id, str) and "-" in task_id:
            prefix = task_id.split("-", 1)[0]
            if prefix in options.type_maps:
                task_type = options.get_task_type(prefix)
                task_type_name = prefix

        # 5. Final attempt: scan for any class whose __name__ matches prefix
        if not task_type and isinstance(task_id, str) and "-" in task_id:
            prefix = task_id.split("-", 1)[0]
            for registered_cls in options.type_maps.values():
                if registered_cls.__name__ == prefix:
                    task_type = registered_cls
                    task_type_name = prefix
                    break

        if not task_type:
            log.warning(
                f"Skipping recurrent job execution; could not resolve task type (original_name={original_name}, job_id={task_id}, serialized={task_data.get('background_task_class_name')})"
            )
            return  # Gracefully skip instead of raising exception

        # Create new instance without calling __init__
        task: RecurrentBackgroundJob = object.__new__(task_type)

        # Restore task state
        task.__dict__.update(task_data)
        task.__task_id__ = task_id
        task.__task_name__ = task_type_name
        task.__task_type__ = "RecurrentTaskDescriptor"
        task.__interval__ = interval

        # Let the task configure its own dependencies using global scheduler instance
        service_provider = None
        if _global_scheduler_instance:
            service_provider = _global_scheduler_instance._service_provider
        elif _service_provider_context.get():
            service_provider = _service_provider_context.get()
        if hasattr(task, "configure"):
            task.configure(service_provider=service_provider)

        log.debug(f"Executing recurrent job: {task.__task_name__} (ID: {task.__task_id__})")
        return await task.run_every(**kwargs)
    except Exception as ex:
        log.error(f"Error executing recurrent job {task_type_name}: {ex}", exc_info=True)
        raise


class BackgroundTaskScheduler(HostedService):
    """
    Distributed task scheduler for background job processing.

    Provides reliable task scheduling with persistence, retry logic,
    and distributed execution capabilities.

    For detailed information about background task scheduling, see:
    https://bvandewe.github.io/pyneuro/features/background-task-scheduling/
    """

    def __init__(
        self,
        options: BackgroundTaskSchedulerOptions,
        scheduler: Optional[Any] = None,
        service_provider: Optional[Any] = None,
    ):
        """Initialize the background task scheduler.

        Args:
            options: Configuration options for task type registration
            scheduler: APScheduler instance (will create one if not provided)
            service_provider: Service provider for dependency injection during deserialization
        """
        # Enforce APScheduler dependency presence early (simplifies type assumptions)
        if AsyncIOExecutor is None or AsyncIOScheduler is None:
            raise BackgroundTaskException(
                "APScheduler AsyncIO components are required. Install with: pip install apscheduler"
            )

        # Attribute declarations (improve static analysis clarity)
        self._options: BackgroundTaskSchedulerOptions = options
        self._service_provider: Optional[Any] = service_provider
        self._started: bool = False
        self._scheduler: Any  # AsyncIOScheduler instance set below

        # Set global instance for job wrapper access
        global _global_scheduler_instance
        _global_scheduler_instance = self

        assert AsyncIOExecutor is not None
        assert AsyncIOScheduler is not None
        # Use local aliases to satisfy static analysis (avoid optional None type complaints)
        executor_cls = AsyncIOExecutor
        scheduler_cls = AsyncIOScheduler
        if scheduler is not None:
            # Best-effort cast (external code may inject subclass / configured instance)
            self._scheduler = scheduler  # type: ignore[assignment]
        else:
            self._scheduler = scheduler_cls(executors={"default": executor_cls()})

    async def start_async(self) -> None:
        """Start the background task scheduler."""
        if self._started:
            log.warning("Background task scheduler is already started")
            return

        if not app_settings.worker_monitoring_enabled:
            log.info("Starting background task scheduler in PAUSED mode (producer only)")
            # Start scheduler paused so it can accept jobs but won't run them
            self._scheduler.start(paused=True)
            self._started = True
            return

        log.info("Starting background task scheduler")
        try:
            # Set service provider in context variable (thread-safe, async-safe)
            _service_provider_context.set(self._service_provider)
            self._scheduler.start()

            # Directly schedule recurrent background jobs (simplified - no duplicate/invalid cleanup)
            for task_name, task_class in self._options.type_maps.items():
                if getattr(task_class, "__background_task_type__", None) == "recurrent":
                    try:
                        if not self._service_provider:
                            log.warning(f"Service provider unavailable while scheduling '{task_name}'")
                            continue
                        scope = self._service_provider.create_scope()
                        try:
                            instance = scope.get_required_service(task_class)
                            # Ensure interval present
                            if not getattr(instance, "__interval__", None):
                                log.warning(f"Recurrent job '{task_name}' missing interval; skipping")
                                continue
                            await self.enqueue_task_async(instance)
                            log.info(f"✅ Scheduled recurrent job: {task_name}")
                        finally:
                            scope.dispose()
                    except Exception as ex:
                        log.error(f"Failed scheduling recurrent job '{task_name}': {ex}")

            self._started = True
            log.info("Background task scheduler started successfully")

            # Dump all jobs for diagnostics after start
            try:
                jobs = self._scheduler.get_jobs()
                if jobs:
                    log.debug("📋 Scheduled jobs snapshot (%d):", len(jobs))
                    for j in jobs:
                        log.debug(
                            "   id=%s name=%s next_run=%s trigger=%s kwargs=%s",
                            j.id,
                            getattr(j, "name", None),
                            getattr(j, "next_run_time", None),
                            str(getattr(j, "trigger", None)),
                            getattr(j, "kwargs", None),
                        )
                else:
                    log.debug("📋 No jobs present after scheduler start")
            except Exception as ex:
                log.warning(f"Failed dumping jobs snapshot: {ex}")

        except Exception as ex:
            log.error(f"Failed to start background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to start scheduler: {ex}")

    # Removed legacy cleanup and reschedule helper methods for simplicity after Redis reset.

    async def trigger_job_now(self, job_id: str) -> None:
        """Trigger an existing scheduled job to run immediately.

        Args:
            job_id: The ID of the job to trigger

        Raises:
            BackgroundTaskException: If job not found or execution fails
        """
        if not self._started:
            raise BackgroundTaskException("Scheduler is not running")

        try:
            job = self._scheduler.get_job(job_id)
            if not job:
                raise BackgroundTaskException(f"Job '{job_id}' not found")

            log.info(f"Manually triggering job '{job_id}' ({job.name})")

            # Modify the job to run immediately
            job.modify(next_run_time=datetime.datetime.now())

            log.info(f"Job '{job_id}' triggered successfully")

        except BackgroundTaskException:
            raise
        except Exception as ex:
            log.error(f"Error triggering job '{job_id}': {ex}")
            raise BackgroundTaskException(f"Failed to trigger job: {ex}")

    async def stop_async(self) -> None:
        """Stop the background task scheduler."""
        if not self._started:
            log.warning("Background task scheduler is not running")
            return

        log.info("Stopping background task scheduler")
        try:
            # Prevent blocking on shutdown
            self._scheduler.shutdown(wait=False)

            # Wait for currently running jobs to finish (with timeout)
            running_jobs = self._scheduler.get_jobs()
            if running_jobs:
                log.info(f"Waiting for {len(running_jobs)} running jobs to complete")

            self._started = False
            log.info("Background task scheduler stopped successfully")

        except Exception as ex:
            log.error(f"Error stopping background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to stop scheduler: {ex}")

    def deserialize_task(self, task_type: type, task_descriptor: TaskDescriptor) -> BackgroundJob:
        """Deserialize a task descriptor into its Python type.

        For tasks that require dependency injection, calls the configure() method
        with the service provider to allow dependency resolution.
        """
        try:
            # Create new instance without calling __init__
            task: BackgroundJob = object.__new__(task_type)

            # Restore the task's state from the descriptor
            task.__dict__.update(task_descriptor.data)
            task.__task_id__ = task_descriptor.id
            task.__task_name__ = task_descriptor.name
            task.__task_type__ = None

            # Set type-specific attributes
            if isinstance(task_descriptor, ScheduledTaskDescriptor) and task.__background_task_type__ == "scheduled":
                task.__scheduled_at__ = task_descriptor.scheduled_at  # type: ignore
                task.__task_type__ = "ScheduledTaskDescriptor"

            if isinstance(task_descriptor, RecurrentTaskDescriptor) and task.__background_task_type__ == "recurrent":
                task.__interval__ = task_descriptor.interval  # type: ignore
                task.__task_type__ = "RecurrentTaskDescriptor"

            # DON'T call configure() here - it will inject unpicklable dependencies!
            # Configuration happens in the job wrappers after APScheduler deserializes the job.
            # This allows us to keep task_data minimal and serializable.

            return task

        except Exception as ex:
            log.error(f"Error deserializing task of type '{task_type.__name__}': {ex}")
            raise BackgroundTaskException(f"Failed to deserialize task: {ex}")

    async def enqueue_task_async(self, task: BackgroundJob) -> None:
        """Enqueue a task to be scheduled by the background task scheduler.

        This method extracts minimal serializable data from the task and passes it to
        APScheduler. The task object itself is NOT pickled - only the minimal data needed
        to reconstruct it is serialized.
        """
        try:
            # Ensure stable name/id prior to serialization
            if not getattr(task, "__task_name__", None):
                background_name = getattr(task.__class__, "__background_task_class_name__", None)
                task.__task_name__ = (
                    background_name if isinstance(background_name, str) and background_name else task.__class__.__name__
                )
            if not getattr(task, "__task_id__", None):
                task.__task_id__ = f"{task.__task_name__}-{uuid.uuid4().hex}"

            # Extract only serializable data (exclude private attributes, methods, and complex objects)
            # Only include primitive types (str, int, float, bool, dict, list) and datetime
            task_data = {}
            for k, v in task.__dict__.items():
                if k.startswith("_"):
                    continue
                # Only include serializable primitive types
                if isinstance(
                    v,
                    (str, int, float, bool, type(None), dict, list, datetime.datetime),
                ):
                    task_data[k] = v
                else:
                    # Log what we're skipping for debugging
                    log.debug(
                        f"Skipping non-serializable attribute '{k}' of type {type(v).__name__} in task {task.__task_name__}"
                    )
                # Skip complex objects like aws_ec2_client, worker_repository, etc.

            # Persist class name explicitly for reconstruction if task_type_name lost
            background_name = getattr(task.__class__, "__background_task_class_name__", None)
            if isinstance(background_name, str) and background_name:
                task_data["background_task_class_name"] = background_name
            log.debug(f"Serializable task_data for {task.__task_name__}: {list(task_data.keys())}")

            if isinstance(task, ScheduledBackgroundJob):
                log.debug(f"Scheduling one-time job: {task.__task_name__} at {task.__scheduled_at__}")

                self._scheduler.add_job(
                    scheduled_job_wrapper,
                    trigger="date",
                    run_date=task.__scheduled_at__,
                    id=task.__task_id__,
                    name=task.__task_name__,  # Ensure logs show actual job name instead of wrapper
                    kwargs={
                        "task_type_name": task.__task_name__,
                        "task_id": task.__task_id__,
                        "task_data": task_data,
                        "scheduled_at": task.__scheduled_at__,
                        # Don't pass service_provider - it's unpicklable!
                        # Wrappers will get it from _global_scheduler instance
                    },
                    misfire_grace_time=None,
                    replace_existing=True,
                )

            elif isinstance(task, RecurrentBackgroundJob):
                # Assign stable global ID for recurrent jobs (single instance semantics)
                if not getattr(task, "__task_id__", None) or not str(task.__task_id__).endswith("-global"):
                    task.__task_id__ = f"{task.__task_name__}-global"
                # Guard: ensure interval is positive before scheduling
                interval_val = getattr(task, "__interval__", None)
                if not isinstance(interval_val, int) or interval_val <= 0:
                    log.warning(
                        f"Skipping scheduling recurrent job '{task.__task_name__}' - invalid interval '{interval_val}'"
                    )
                    return
                log.debug(
                    f"Scheduling recurrent job: {task.__task_name__} every {interval_val} seconds (id={task.__task_id__})"
                )

                self._scheduler.add_job(
                    recurrent_job_wrapper,
                    trigger="interval",
                    seconds=interval_val,
                    id=task.__task_id__,
                    name=task.__task_name__,  # Ensure logs show actual job name instead of wrapper
                    kwargs={
                        "task_type_name": task.__task_name__,
                        "task_id": task.__task_id__,
                        "task_data": task_data,
                        "interval": interval_val,
                        # Don't pass service_provider - it's unpicklable!
                        # Wrappers will get it from _global_scheduler instance
                    },
                    misfire_grace_time=None,
                    replace_existing=True,  # Overwrite any prior instance sharing the global ID
                )
            else:
                raise BackgroundTaskException(f"Unknown task type: {type(task)}")

            log.info(f"Successfully enqueued task: {task.__task_name__} (ID: {task.__task_id__})")

        except Exception as ex:
            log.error(f"Error enqueuing task '{task.__task_name__}': {ex}")
            raise BackgroundTaskException(f"Failed to enqueue task: {ex}")

    def list_tasks(self) -> List[Any]:
        """List all scheduled tasks."""
        try:
            return self._scheduler.get_jobs()
        except Exception as ex:
            log.error(f"Error listing tasks: {ex}")
            return []

    def stop_task(self, task_id: str) -> bool:
        """Stop a scheduled task by ID."""
        try:
            self._scheduler.remove_job(task_id)
            log.info(f"Successfully stopped task: {task_id}")
            return True
        except Exception as ex:
            log.error(f"Error stopping task '{task_id}': {ex}")
            return False

    def get_job(self, task_id: str) -> Optional[Any]:
        """Get a job by ID from the scheduler.

        Args:
            task_id: The ID of the job to retrieve

        Returns:
            The APScheduler job object if found, None otherwise
        """
        try:
            return self._scheduler.get_job(task_id)
        except Exception as ex:
            log.debug(f"Error getting job '{task_id}': {ex}")
            return None

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific task."""
        try:
            job = self._scheduler.get_job(task_id)
            if job:
                return {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                    "args": job.args,
                    "kwargs": job.kwargs,
                }
            return None
        except Exception as ex:
            log.error(f"Error getting task info for '{task_id}': {ex}")
            return None

    def get_jobs(self) -> List[Any]:
        """Get all scheduled jobs."""
        return self._scheduler.get_jobs()

    def get_job_count(self) -> int:
        """Get the number of scheduled jobs."""
        return len(self.get_jobs())

    @staticmethod
    def configure(builder: "WebApplicationBuilder", modules: list[str]) -> None:
        """Register and configure background task services in the application builder.

        Args:
            builder: Application builder instance
            modules: List of module names to scan for background tasks
        """
        try:
            if AsyncIOScheduler is None:
                raise BackgroundTaskException(
                    "APScheduler is required for background task scheduling. "
                    "Install it with: pip install apscheduler[redis] or pip install apscheduler[mongodb]"
                )

            # Create scheduler options and discover tasks
            options = BackgroundTaskSchedulerOptions(modules=modules)

            # Scan modules for background tasks
            for module_name in modules:
                try:
                    module = ModuleLoader.load(module_name)
                    background_tasks = TypeFinder.get_types(
                        module,
                        lambda cls: inspect.isclass(cls) and hasattr(cls, "__background_task_class_name__"),
                    )

                    for background_task in background_tasks:
                        background_task_name = background_task.__background_task_class_name__
                        background_task_type = background_task.__background_task_type__

                        options.register_task_type(background_task_name, background_task)
                        builder.services.add_transient(background_task, background_task)

                        log.info(
                            f"Registered background task '{background_task_name}' of type '{background_task_type}'"
                        )

                except Exception as ex:
                    log.error(f"Error scanning module '{module_name}' for background tasks: {ex}")
                    continue

            # Configure job stores if settings are available
            jobstores = {}
            if hasattr(builder, "settings"):
                job_store_config = getattr(builder.settings, "background_job_store", {})

                # Check for Redis configuration
                redis_keys = ["redis_host", "redis_port", "redis_db"]
                if all(key in job_store_config for key in redis_keys):
                    if RedisJobStore is not None:
                        jobstores["default"] = RedisJobStore(
                            db=job_store_config["redis_db"],
                            jobs_key="apscheduler.jobs",
                            run_times_key="apscheduler.run_times",
                            host=job_store_config["redis_host"],
                            port=job_store_config["redis_port"],
                        )
                        log.info(
                            f"Configured Redis job store for background tasks (host={job_store_config['redis_host']}, db={job_store_config['redis_db']})"
                        )
                    else:
                        log.warning("Redis job store requested but Redis dependencies not available")

                mongo_uri_keys = ["mongo_uri", "mongo_db", "mongo_collection"]
                mongo_individual_keys = [
                    "mongo_host",
                    "mongo_port",
                    "mongo_db",
                    "mongo_collection",
                ]
                # Check for MongoDB configuration
                if all(key in job_store_config for key in mongo_uri_keys) or all(
                    key in job_store_config for key in mongo_individual_keys
                ):
                    if MongoDBJobStore is not None:
                        # Support both URI and individual parameter configuration
                        if "mongo_uri" in job_store_config:
                            mongo_uri = job_store_config.get("mongo_uri")
                            mongo_db = job_store_config.get("mongo_db") or "apscheduler"
                            mongo_collection = job_store_config.get("mongo_collection") or "jobs"
                            jobstores["default"] = MongoDBJobStore(
                                host=mongo_uri,
                                database=mongo_db,
                                collection=mongo_collection,
                            )
                            log.info("Configured MongoDB job store for background tasks (URI)")
                        else:
                            # Individual parameters
                            mongo_host = job_store_config.get("mongo_host", "localhost")
                            mongo_port = job_store_config.get("mongo_port", 27017)
                            mongo_db = job_store_config.get("mongo_db") or "apscheduler"
                            mongo_collection = job_store_config.get("mongo_collection") or "jobs"

                            jobstores["default"] = MongoDBJobStore(
                                host=mongo_host,
                                port=mongo_port,
                                database=mongo_db,
                                collection=mongo_collection,
                            )
                            log.info("Configured MongoDB job store for background tasks (individual params)")
                    else:
                        log.warning("MongoDB job store requested but MongoDB dependencies not available")

                # Check for incomplete configurations
                elif any(key.startswith(("redis_", "mongo_")) for key in job_store_config.keys()):
                    # Check if we have enough Redis config to proceed despite missing keys (e.g. defaults)
                    redis_essential = ["redis_host"]
                    if all(key in job_store_config for key in redis_essential):
                        # We have host, port defaults to 6379, db defaults to 0 if missing.
                        # This is likely a valid config that just relies on defaults.
                        pass
                    else:
                        log.warning("Incomplete job store configuration found - check Redis or MongoDB settings")

                else:
                    log.info("No job store configuration found, using in-memory job store")
            else:
                log.info("No settings found, using in-memory job store")

            # Register services
            # Executor & Scheduler types are guaranteed (checked above); cast to satisfy type expectations
            assert AsyncIOExecutor is not None
            assert AsyncIOScheduler is not None
            executor_cls = AsyncIOExecutor  # type: ignore[assignment]
            scheduler_cls = AsyncIOScheduler  # type: ignore[assignment]
            builder.services.add_singleton(executor_cls, executor_cls)  # type: ignore[arg-type]
            builder.services.add_singleton(
                scheduler_cls,
                implementation_factory=lambda provider: scheduler_cls(
                    executors={"default": provider.get_service(executor_cls)},  # type: ignore[arg-type]
                    jobstores=jobstores,
                ),
            )
            builder.services.add_singleton(BackgroundTaskSchedulerOptions, singleton=options)

            # Register as both HostedService and BackgroundTaskScheduler
            builder.services.add_singleton(
                BackgroundTaskScheduler,
                implementation_factory=lambda provider: BackgroundTaskScheduler(
                    provider.get_required_service(BackgroundTaskSchedulerOptions),
                    provider.get_required_service(scheduler_cls),
                    service_provider=provider,
                ),
            )
            builder.services.add_singleton(
                HostedService,
                implementation_factory=lambda provider: provider.get_service(BackgroundTaskScheduler),
            )
            log.info("✅ Background task scheduler services registered successfully")

        except Exception as ex:
            log.error(f"Error configuring background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to configure background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to configure background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to configure background task scheduler: {ex}")
