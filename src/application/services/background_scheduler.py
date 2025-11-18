"""
Background task scheduling infrastructure for the Neuroglia framework.

This module provides comprehensive background task scheduling capabilities using
APScheduler with Redis persistence, reactive streams integration, and support for
both scheduled (one-time) and recurrent background jobs.
"""

import asyncio
import contextvars
import datetime
import inspect
import logging
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from neuroglia.core import ModuleLoader, TypeFinder
from neuroglia.reactive import AsyncRx
from rx.subject.subject import Subject

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
    from neuroglia.hosting.abstractions import ApplicationBuilderBase, HostedService
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
_service_provider_context: contextvars.ContextVar = contextvars.ContextVar(
    "service_provider", default=None
)


class BackgroundTaskException(Exception):
    """Exception raised by background task operations."""


def backgroundjob(
    task_type: Optional[str] = None,
    interval: Optional[int] = None,
    scheduled_at: Optional[datetime.datetime] = None,
):
    """Marks a class as a background task that will be scheduled by the BackgroundTaskScheduler.

    Args:
        task_type: Type of task - "scheduled" for one-time or "recurrent" for recurring
        interval: Interval in seconds for recurrent tasks (only used if task_type="recurrent")
        scheduled_at: Datetime for scheduled tasks (only used if task_type="scheduled")
    """

    def decorator(cls):
        """Adds metadata to the class with the specified task type"""
        cls.__background_task_class_name__ = cls.__name__
        cls.__background_task_type__ = (
            task_type if task_type in ("scheduled", "recurrent") else None
        )
        if interval is not None:
            cls.__interval__ = interval
        if scheduled_at is not None:
            cls.__scheduled_at__ = scheduled_at
        return cls

    return decorator


class BackgroundJob(ABC):
    """Defines the fundamentals of a background job."""

    __background_task_type__: Optional[str] = None
    __task_id__: Optional[str] = None
    __task_name__: Optional[str] = None
    __task_type__: Optional[str] = None

    @abstractmethod
    def configure(self, *args, **kwargs):
        """Configure the background job with necessary dependencies and parameters."""


class ScheduledBackgroundJob(BackgroundJob, ABC):
    """Defines the fundamentals of a scheduled background job."""

    __scheduled_at__: Optional[datetime.datetime] = None

    @abstractmethod
    async def run_at(self, *args, **kwargs):
        """Execute the scheduled job at the specified time."""


class RecurrentBackgroundJob(BackgroundJob, ABC):
    """Defines the fundamentals of a recurrent background job."""

    __interval__: Optional[int] = None

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
    started_at: Optional[datetime.datetime] = None


class BackgroundTasksBus:
    """Defines the fundamentals of a service used to manage incoming and outgoing streams of background tasks."""

    def __init__(self):
        """Initialize the background tasks bus with a new input stream."""
        self.input_stream: Subject = Subject()

    def schedule_task(self, task_descriptor: TaskDescriptor):
        """Schedule a task by sending it through the input stream."""
        self.input_stream.on_next(task_descriptor)

    def dispose(self):
        """Dispose of the input stream and release resources."""
        if hasattr(self.input_stream, "dispose"):
            self.input_stream.dispose()


class BackgroundTaskSchedulerOptions:
    """Represents the configuration options for the background task scheduler."""

    def __init__(self, modules: Optional[list[str]] = None):
        """Initialize with an empty type mapping.

        Args:
            modules: List of module paths to scan for @backgroundjob decorators (e.g., ['application.jobs'])
        """
        self.type_maps: dict[str, typing.Type] = {}
        self.modules: list[str] = modules or [
            "application.services"
        ]  # Default for backward compatibility

    def register_task_type(self, name: str, task_type: typing.Type):
        """Register a task type with the scheduler."""
        self.type_maps[name] = task_type
        log.debug(f"Registered background task type '{name}': {task_type}")

    def get_task_type(self, name: str) -> Optional[typing.Type]:
        """Get a task type by name."""
        return self.type_maps.get(name)


async def scheduled_job_wrapper(
    task_type_name: str,
    task_id: str,
    task_data: dict,
    scheduled_at: datetime.datetime,
    **kwargs,
):
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
        # Try to get modules from service provider, fallback to common paths
        service_provider = _service_provider_context.get()
        if service_provider:
            try:
                scheduler_options = service_provider.get_service(
                    BackgroundTaskSchedulerOptions
                )
                modules = (
                    scheduler_options.modules
                    if scheduler_options
                    else ["application.services", "application.jobs"]
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
                    lambda cls: inspect.isclass(cls)
                    and hasattr(cls, "__background_task_class_name__"),
                )

                for background_task in background_tasks:
                    task_name = background_task.__background_task_class_name__
                    options.register_task_type(task_name, background_task)
            except Exception as e:
                log.debug(
                    f"Could not scan module '{module_name}' in scheduled_job_wrapper: {e}"
                )
                continue

        task_type = options.get_task_type(task_type_name)
        if not task_type:
            raise BackgroundTaskException(
                f"Task type '{task_type_name}' not registered"
            )

        # Create new instance without calling __init__
        task: ScheduledBackgroundJob = object.__new__(task_type)

        # Restore task state
        task.__dict__.update(task_data)
        task.__task_id__ = task_id
        task.__task_name__ = task_type_name
        task.__task_type__ = "ScheduledTaskDescriptor"
        task.__scheduled_at__ = scheduled_at

        # Let the task configure its own dependencies
        # Get service provider from context variable (thread-safe, async-safe)
        service_provider = _service_provider_context.get()
        if hasattr(task, "configure"):
            task.configure(service_provider=service_provider)

        log.debug(
            f"Executing scheduled job: {task.__task_name__} (ID: {task.__task_id__})"
        )
        return await task.run_at(**kwargs)
    except Exception as ex:
        log.error(
            f"Error executing scheduled job {task_type_name}: {ex}", exc_info=True
        )
        raise


async def recurrent_job_wrapper(
    task_type_name: str,
    task_id: str,
    task_data: dict,
    interval: int,
    **kwargs,
):
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

        # Create a temporary options instance to access registered task types
        # Try to get modules from service provider, fallback to common paths
        service_provider = _service_provider_context.get()
        if service_provider:
            try:
                scheduler_options = service_provider.get_service(
                    BackgroundTaskSchedulerOptions
                )
                modules = (
                    scheduler_options.modules
                    if scheduler_options
                    else ["application.services", "application.jobs"]
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
                    lambda cls: inspect.isclass(cls)
                    and hasattr(cls, "__background_task_class_name__"),
                )

                for background_task in background_tasks:
                    task_name = background_task.__background_task_class_name__
                    options.register_task_type(task_name, background_task)
            except Exception as e:
                log.debug(
                    f"Could not scan module '{module_name}' in recurrent_job_wrapper: {e}"
                )
                continue

        task_type = options.get_task_type(task_type_name)
        if not task_type:
            raise BackgroundTaskException(
                f"Task type '{task_type_name}' not registered"
            )

        # Create new instance without calling __init__
        task: RecurrentBackgroundJob = object.__new__(task_type)

        # Restore task state
        task.__dict__.update(task_data)
        task.__task_id__ = task_id
        task.__task_name__ = task_type_name
        task.__task_type__ = "RecurrentTaskDescriptor"
        task.__interval__ = interval

        # Let the task configure its own dependencies
        # Get service provider from context variable (thread-safe, async-safe)
        service_provider = _service_provider_context.get()
        if hasattr(task, "configure"):
            task.configure(service_provider=service_provider)

        log.debug(
            f"Executing recurrent job: {task.__task_name__} (ID: {task.__task_id__})"
        )
        return await task.run_every(**kwargs)
    except Exception as ex:
        log.error(
            f"Error executing recurrent job {task_type_name}: {ex}", exc_info=True
        )
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
        background_task_bus: BackgroundTasksBus,
        scheduler: Optional[AsyncIOScheduler] = None,
        service_provider=None,
    ):
        """Initialize the background task scheduler.

        Args:
            options: Configuration options for task type registration
            background_task_bus: Bus for receiving task requests
            scheduler: APScheduler instance (will create one if not provided)
            service_provider: Service provider for dependency injection during deserialization
        """
        if AsyncIOScheduler is None:
            raise BackgroundTaskException(
                "APScheduler is required for background task scheduling. "
                "Install it with: pip install apscheduler[redis] or pip install apscheduler[mongodb]"
            )

        self._options = options
        self._background_task_bus = background_task_bus
        self._service_provider = service_provider
        self._started = False

        if scheduler:
            self._scheduler = scheduler
        elif AsyncIOExecutor is not None:
            self._scheduler = AsyncIOScheduler(executors={"default": AsyncIOExecutor()})
        else:
            raise BackgroundTaskException("APScheduler dependencies not available")

    async def start_async(self):
        """Start the background task scheduler."""
        if self._started:
            log.warning("Background task scheduler is already started")
            return

        log.info("Starting background task scheduler")
        try:
            # Set service provider in context variable (thread-safe, async-safe)
            _service_provider_context.set(self._service_provider)

            self._scheduler.start()

            # Subscribe to the task bus for incoming job requests
            def handle_task_request(task_desc):
                asyncio.create_task(self._on_job_request_async(task_desc))

            AsyncRx.subscribe(
                self._background_task_bus.input_stream, handle_task_request
            )

            self._started = True
            log.info("Background task scheduler started successfully")

        except Exception as ex:
            log.error(f"Failed to start background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to start scheduler: {ex}")

    async def stop_async(self):
        """Stop the background task scheduler."""
        if not self._started:
            log.warning("Background task scheduler is not started")
            return

        log.info("Stopping background task scheduler")
        try:
            # Prevent blocking on shutdown
            self._scheduler.shutdown(wait=False)

            # Wait for currently running jobs to finish (with timeout)
            running_jobs = self._scheduler.get_jobs()
            if running_jobs:
                log.info(f"Waiting for {len(running_jobs)} running jobs to complete")

            # Dispose of the task bus
            self._background_task_bus.dispose()
            self._started = False
            log.info("Background task scheduler stopped successfully")

        except Exception as ex:
            log.error(f"Error stopping background task scheduler: {ex}")
            raise BackgroundTaskException(f"Failed to stop scheduler: {ex}")

    async def _on_job_request_async(self, task_descriptor: TaskDescriptor):
        """Handle incoming job requests from the task bus."""
        try:
            # Find the Python type of the task
            task_type = self._options.get_task_type(task_descriptor.name)
            if task_type is None:
                log.warning(
                    f"Ignored incoming job request: the specified type '{task_descriptor.name}' "
                    f"is not supported. Did you forget to put the '@backgroundjob' decorator on the class?"
                )
                return

            # Deserialize and enqueue the task
            task = self.deserialize_task(task_type, task_descriptor)
            await self.enqueue_task_async(task)

        except Exception as ex:
            log.error(
                f"Error processing job request for '{task_descriptor.name}': {ex}"
            )

    def deserialize_task(
        self, task_type: typing.Type, task_descriptor: TaskDescriptor
    ) -> BackgroundJob:
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
            if (
                isinstance(task_descriptor, ScheduledTaskDescriptor)
                and task.__background_task_type__ == "scheduled"
            ):
                task.__scheduled_at__ = task_descriptor.scheduled_at  # type: ignore
                task.__task_type__ = "ScheduledTaskDescriptor"

            if (
                isinstance(task_descriptor, RecurrentTaskDescriptor)
                and task.__background_task_type__ == "recurrent"
            ):
                task.__interval__ = task_descriptor.interval  # type: ignore
                task.__task_type__ = "RecurrentTaskDescriptor"

            # DON'T call configure() here - it will inject unpicklable dependencies!
            # Configuration happens in the job wrappers after APScheduler deserializes the job.
            # This allows us to keep task_data minimal and serializable.

            return task

        except Exception as ex:
            log.error(f"Error deserializing task of type '{task_type.__name__}': {ex}")
            raise BackgroundTaskException(f"Failed to deserialize task: {ex}")

    async def enqueue_task_async(self, task: BackgroundJob):
        """Enqueue a task to be scheduled by the background task scheduler.

        This method extracts minimal serializable data from the task and passes it to
        APScheduler. The task object itself is NOT pickled - only the minimal data needed
        to reconstruct it is serialized.
        """
        try:
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

            log.debug(
                f"Serializable task_data for {task.__task_name__}: {list(task_data.keys())}"
            )

            if isinstance(task, ScheduledBackgroundJob):
                log.debug(
                    f"Scheduling one-time job: {task.__task_name__} at {task.__scheduled_at__}"
                )

                self._scheduler.add_job(
                    scheduled_job_wrapper,
                    trigger="date",
                    run_date=task.__scheduled_at__,
                    id=task.__task_id__,
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
                log.debug(
                    f"Scheduling recurrent job: {task.__task_name__} every {task.__interval__} seconds"
                )

                self._scheduler.add_job(
                    recurrent_job_wrapper,
                    trigger="interval",
                    seconds=task.__interval__,
                    id=task.__task_id__,
                    kwargs={
                        "task_type_name": task.__task_name__,
                        "task_id": task.__task_id__,
                        "task_data": task_data,
                        "interval": task.__interval__,
                        # Don't pass service_provider - it's unpicklable!
                        # Wrappers will get it from _global_scheduler instance
                    },
                    misfire_grace_time=None,
                    replace_existing=True,
                )
            else:
                raise BackgroundTaskException(f"Unknown task type: {type(task)}")

            log.info(
                f"Successfully enqueued task: {task.__task_name__} (ID: {task.__task_id__})"
            )

        except Exception as ex:
            log.error(f"Error enqueuing task '{task.__task_name__}': {ex}")
            raise BackgroundTaskException(f"Failed to enqueue task: {ex}")

    def list_tasks(self) -> list:
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

    def get_job(self, task_id: str):
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

    def get_task_info(self, task_id: str) -> Optional[dict]:
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

    @staticmethod
    def configure(builder, modules: list[str]):
        """Register and configure background task services in the application builder."""
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
                        lambda cls: inspect.isclass(cls)
                        and hasattr(cls, "__background_task_class_name__"),
                    )

                    for background_task in background_tasks:
                        background_task_name = (
                            background_task.__background_task_class_name__
                        )
                        background_task_type = background_task.__background_task_type__

                        options.register_task_type(
                            background_task_name, background_task
                        )
                        builder.services.add_transient(background_task, background_task)

                        log.info(
                            f"Registered background task '{background_task_name}' of type '{background_task_type}'"
                        )

                except Exception as ex:
                    log.error(
                        f"Error scanning module '{module_name}' for background tasks: {ex}"
                    )
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
                        log.warning(
                            "Redis job store requested but Redis dependencies not available"
                        )

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
                            jobstores["default"] = MongoDBJobStore(
                                host=mongo_uri,
                                database=job_store_config.get("mongo_db"),
                                collection=job_store_config.get("mongo_collection"),
                            )
                            log.info(
                                "Configured MongoDB job store for background tasks (URI)"
                            )
                        else:
                            # Individual parameters
                            mongo_host = job_store_config.get("mongo_host", "localhost")
                            mongo_port = job_store_config.get("mongo_port", 27017)
                            mongo_db = job_store_config.get("mongo_db")
                            mongo_collection = job_store_config.get("mongo_collection")

                            jobstores["default"] = MongoDBJobStore(
                                host=mongo_host,
                                port=mongo_port,
                                database=mongo_db,
                                collection=mongo_collection,
                            )
                            log.info(
                                "Configured MongoDB job store for background tasks (individual params)"
                            )
                    else:
                        log.warning(
                            "MongoDB job store requested but MongoDB dependencies not available"
                        )

                # Check for incomplete configurations
                elif any(
                    key.startswith(("redis_", "mongo_"))
                    for key in job_store_config.keys()
                ):
                    log.warning(
                        "Incomplete job store configuration found - check Redis or MongoDB settings"
                    )

                else:
                    log.info(
                        "No job store configuration found, using in-memory job store"
                    )
            else:
                log.info("No settings found, using in-memory job store")

            # Register services
            builder.services.add_singleton(AsyncIOExecutor, AsyncIOExecutor)
            builder.services.add_singleton(
                AsyncIOScheduler,
                implementation_factory=lambda provider: AsyncIOScheduler(
                    executors={"default": provider.get_service(AsyncIOExecutor)},
                    jobstores=jobstores,
                ),
            )
            builder.services.add_singleton(BackgroundTasksBus, BackgroundTasksBus)
            builder.services.add_singleton(
                BackgroundTaskSchedulerOptions, singleton=options
            )

            # Register as both HostedService and BackgroundTaskScheduler
            builder.services.add_singleton(
                BackgroundTaskScheduler,
                implementation_factory=lambda provider: BackgroundTaskScheduler(
                    provider.get_required_service(BackgroundTaskSchedulerOptions),
                    provider.get_required_service(BackgroundTasksBus),
                    provider.get_required_service(AsyncIOScheduler),
                    service_provider=provider,  # Pass service provider for DI during deserialization
                ),
            )
            builder.services.add_singleton(
                HostedService,
                implementation_factory=lambda provider: provider.get_service(
                    BackgroundTaskScheduler
                ),
            )
            log.info("Background task scheduler services registered successfully")

            return builder

        except Exception as ex:
            log.error(f"Error configuring background task scheduler: {ex}")
            raise BackgroundTaskException(
                f"Failed to configure background task scheduler: {ex}"
            )
