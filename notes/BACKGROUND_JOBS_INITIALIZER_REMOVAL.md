# BackgroundJobsInitializer Removal - Architectural Simplification

**Date**: 2025-01-18
**Status**: ✅ Complete

## Summary

Removed `BackgroundJobsInitializer` HostedService in favor of simpler, declarative job configuration. Jobs now self-configure their intervals and dependencies through class attributes and `configure()` methods.

## Motivation

The original implementation had an unnecessary abstraction layer:

1. **BackgroundJobsInitializer** - manually scheduled jobs with intervals from settings
2. **BackgroundTaskScheduler** - already discovers and registers `@backgroundjob` classes
3. **Job classes** - already have `configure()` methods for dependencies

This created duplicate responsibilities and complexity. The BackgroundTaskScheduler already handles:

- Job discovery via `@backgroundjob` decorator
- Job registration with APScheduler
- Dependency injection via `configure()` method
- Job execution via wrapper functions

## Changes Made

### 1. Removed BackgroundJobsInitializer (133 lines → deleted)

**Previous responsibility**:

```python
class BackgroundJobsInitializer(HostedService):
    async def start_async(self, cancellation_token: CancellationToken = None):
        # Create database indexes
        await lab_record_repository.ensure_indexes_async()

        # Schedule WorkerMetricsCollectionJob with configurable interval
        await self._scheduler.schedule_async(
            RecurrentTaskDescriptor(
                name="WorkerMetricsCollectionJob",
                interval=worker_metrics_poll_interval,
                # ...
            )
        )

        # Schedule LabsRefreshJob with fixed 30min interval
        await self._scheduler.schedule_async(
            RecurrentTaskDescriptor(
                name="LabsRefreshJob",
                interval=1800,
                # ...
            )
        )
```

**Replaced with**:

- Jobs declare their own intervals as class attributes
- Database index creation moved to `LabsRefreshJob.configure()`
- BackgroundTaskScheduler auto-discovers jobs on startup

### 2. Updated Job Classes to Self-Configure

#### WorkerMetricsCollectionJob

```python
# BEFORE: Interval passed from BackgroundJobsInitializer
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    __interval__ = 300  # Hardcoded default
```

```python
# AFTER: Interval read from settings at module import time
from application.settings import app_settings

class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    __interval__ = app_settings.worker_metrics_poll_interval  # Configurable via env var
```

**Configuration**: Set `WORKER_METRICS_POLL_INTERVAL=300` (default: 300s/5min)

#### LabsRefreshJob

```python
class LabsRefreshJob(RecurrentBackgroundJob):
    __interval__ = 1800  # 30 minutes in seconds

    def configure(self, service_provider=None, **kwargs):
        # ... existing dependency injection ...

        # NEW: Ensure database indexes are created on first run
        if service_provider:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._ensure_indexes_async(service_provider))
                else:
                    loop.run_until_complete(self._ensure_indexes_async(service_provider))
            except Exception as e:
                logger.warning(f"Could not create indexes during configure: {e}")

    async def _ensure_indexes_async(self, service_provider):
        """Ensure database indexes exist (idempotent operation)."""
        scope = service_provider.create_scope()
        try:
            lab_record_repo = scope.get_required_service(LabRecordRepository)
            await lab_record_repo.ensure_indexes_async()
            logger.info("✅ Lab record indexes ensured")
        finally:
            scope.dispose()
```

### 3. Updated SystemController

Removed reference to `_background_jobs_initializer` global variable:

```python
# BEFORE
from main import _background_jobs_initializer
scheduler = _background_jobs_initializer._scheduler._scheduler

# AFTER
from application.services.background_scheduler import BackgroundTaskScheduler
scheduler: BackgroundTaskScheduler = self.service_provider.get_required_service(BackgroundTaskScheduler)
```

### 4. Simplified main.py

```python
# BEFORE
from application.services.background_jobs_initializer import BackgroundJobsInitializer

if app_settings.worker_monitoring_enabled:
    BackgroundJobsInitializer.configure(
        builder,
        worker_metrics_poll_interval=app_settings.worker_metrics_poll_interval,
        labs_refresh_interval=1800,
    )

# AFTER
from application.services.background_scheduler import BackgroundTaskScheduler

BackgroundTaskScheduler.configure(
    builder,
    modules=["application.jobs"],  # Auto-discovers @backgroundjob classes
)

if app_settings.worker_monitoring_enabled:
    log.info("✅ Worker monitoring enabled - jobs will be scheduled on startup")
```

## Architecture Flow

### Startup Sequence

1. **Application Start** (`main.py::create_app()`)
   - `BackgroundTaskScheduler.configure()` called with `modules=["application.jobs"]`
   - Scheduler scans modules for `@backgroundjob` decorated classes
   - Registers `WorkerMetricsCollectionJob` (interval from settings)
   - Registers `LabsRefreshJob` (interval from class attribute)

2. **HostedService Lifecycle** (Neuroglia framework)
   - `BackgroundTaskScheduler.start_async()` invoked by framework
   - APScheduler starts with configured jobs
   - Jobs begin executing at their specified intervals

3. **Job Execution** (per interval)
   - APScheduler triggers `recurrent_job_wrapper()`
   - Wrapper deserializes job from stored task data
   - Wrapper calls `job.configure(service_provider=...)` to inject dependencies
   - Job's `configure()` creates indexes (LabsRefreshJob) or injects AWS client (WorkerMetricsCollectionJob)
   - Wrapper calls `await job.run_every(**kwargs)`
   - Job executes business logic

### Job Registration Flow

```
```

@backgroundjob decorator
  → Class marked with **background_task_class_name**
  → Interval/scheduled_at set as class attributes from decorator params
  → BackgroundTaskScheduler.configure() scans modules
  → find_background_tasks(module) discovers class
  → options.register_task_type(name, class)
  → builder.services.add_transient(class, class)
  → BackgroundTaskScheduler.start_async()
  → For each RecurrentBackgroundJob:
      → Read **interval** class attribute (set by decorator)
      → scheduler.add_job(recurrent_job_wrapper, interval=**interval**)

```

## Benefits

1. **Simpler Architecture**: Removed 133 lines of unnecessary abstraction
2. **Self-Contained Jobs**: Each job declares its interval in the decorator
3. **Configuration Flexibility**: Intervals configurable via environment variables
4. **Clearer Separation**: BackgroundTaskScheduler handles scheduling, jobs handle business logic
5. **Explicit Configuration**: Decorator parameters make intervals visible at a glance
6. **Testability**: Jobs can be instantiated and tested independently
7. **Maintainability**: One place to look for job configuration (the job class itself)

## Migration Guide

### For New Jobs

1. Create class extending `RecurrentBackgroundJob` or `ScheduledBackgroundJob`
2. Add `@backgroundjob()` decorator with `task_type` and `interval`/`scheduled_at`
3. Implement `configure(service_provider, **kwargs)` for dependency injection
4. Implement `run_every(**kwargs)` or `run_at(**kwargs)` for business logic

Example:
```python
from application.services.background_scheduler import RecurrentBackgroundJob, backgroundjob
from application.settings import app_settings

@backgroundjob(task_type="recurrent", interval=600)  # 10 minutes
class MyCustomJob(RecurrentBackgroundJob):

    def configure(self, service_provider=None, **kwargs):
        if service_provider:
            self.repository = service_provider.get_required_service(MyRepository)

    async def run_every(self, *args, **kwargs):
        # Business logic here
        pass
```

### For Configurable Intervals

Use settings at module level in decorator:

```python
from application.settings import app_settings

@backgroundjob(task_type="recurrent", interval=app_settings.my_custom_interval)
class MyJob(RecurrentBackgroundJob):
    pass  # interval is read from env: MY_CUSTOM_INTERVAL
```

Add to `application/settings.py`:

```python
class Settings(ApplicationSettings):
    my_custom_interval: int = 600  # Default: 10 minutes
```

```

## Benefits

1. **Simpler Architecture**: Removed 133 lines of unnecessary abstraction
2. **Self-Contained Jobs**: Each job declares its own interval and dependencies
3. **Configuration Flexibility**: Intervals configurable via environment variables
4. **Clearer Separation**: BackgroundTaskScheduler handles scheduling, jobs handle business logic
5. **Testability**: Jobs can be instantiated and tested independently
6. **Maintainability**: One place to look for job configuration (the job class itself)

## Migration Guide

### For New Jobs

1. Create class extending `RecurrentBackgroundJob` or `ScheduledBackgroundJob`
2. Add `@backgroundjob(task_type="recurrent")` decorator
3. Set `__interval__` class attribute (in seconds)
4. Implement `configure(service_provider, **kwargs)` for dependency injection
5. Implement `run_every(**kwargs)` or `run_at(**kwargs)` for business logic

Example:

```python
from application.services.background_scheduler import RecurrentBackgroundJob, backgroundjob
from application.settings import app_settings

@backgroundjob(task_type="recurrent")
class MyCustomJob(RecurrentBackgroundJob):
    __interval__ = 600  # 10 minutes or read from settings: app_settings.my_job_interval

    def configure(self, service_provider=None, **kwargs):
        if service_provider:
            self.repository = service_provider.get_required_service(MyRepository)

    async def run_every(self, *args, **kwargs):
        # Business logic here
        pass
```

### For Configurable Intervals

Import settings at module level:

```python
from application.settings import app_settings

@backgroundjob(task_type="recurrent")
class MyJob(RecurrentBackgroundJob):
    __interval__ = app_settings.my_custom_interval  # Read from env: MY_CUSTOM_INTERVAL
```

Add to `application/settings.py`:

```python
class Settings(ApplicationSettings):
    my_custom_interval: int = 600  # Default: 10 minutes
```

## Testing

Jobs can now be tested independently:

```python
def test_worker_metrics_collection_job():
    job = WorkerMetricsCollectionJob(aws_ec2_client=mock_client)
    job.configure(service_provider=mock_provider)
    await job.run_every()
    # Assert expectations
```

No need to mock BackgroundJobsInitializer or worry about scheduling logic.

## Related Files

- ✅ Deleted: `src/application/services/background_jobs_initializer.py`
- ✅ Updated: `src/application/jobs/worker_metrics_collection_job.py` (interval from settings)
- ✅ Updated: `src/application/jobs/labs_refresh_job.py` (index creation, fixed interval)
- ✅ Updated: `src/main.py` (removed BackgroundJobsInitializer.configure())
- ✅ Updated: `src/api/controllers/system_controller.py` (use BackgroundTaskScheduler singleton)

## References

- Original issue: Duplicate initialization logs (3x)
- Root cause: Unnecessary HostedService registration layer
- Solution: Jobs self-configure via class attributes and configure() method
- Pattern: Declarative over imperative configuration
