# APScheduler Refactoring - Implementation Summary & Recommendations

## ✅ Completed Refactoring

### 1. **WorkerMetricsCollectionJob** (New File)

**File:** `src/application/services/worker_metrics_collection_job.py`

**Changes:**

- Created new `@backgroundjob(task_type="recurrent")` decorated class
- Extends `RecurrentBackgroundJob` from background_scheduler
- Implements `run_every()` method that APScheduler invokes at intervals
- Removed manual asyncio task management
- Keeps observer pattern for emitting metrics events

**Key Pattern:**

```python
@backgroundjob(task_type="recurrent")
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    async def run_every(self, *args, **kwargs) -> None:
        # Collect metrics
        # Emit to observers
        pass
```

### 2. **WorkerNotificationHandler** (Refactored)

**File:** `src/application/services/worker_notification_handler.py`

**Changes:**

- ❌ Removed: `on_worker_created_async()`, `on_worker_imported_async()`, etc.
- ❌ Removed: `_send_notification_async()` method for external webhooks
- ❌ Removed: `set_scheduler()` bidirectional reference
- ✅ Added: `__call__()` method as observer callback
- ✅ Added: `_parse_utilization()` helper for metric parsing
- ✅ Added: `_handle_threshold_violation()` for extensibility

**Architecture Change:**

- **Before:** Active notification sender (push)
- **After:** Reactive event observer (pull)
- Receives metrics events from WorkerMetricsCollectionJob
- Processes events synchronously in callback

**Key Pattern:**

```python
class WorkerNotificationHandler:
    def __call__(self, metrics_data: Dict[str, Any]) -> None:
        # Process metrics event
        # Check thresholds
        # Log/forward as needed
```

### 3. **WorkerMonitoringScheduler** (Refactored)

**File:** `src/application/services/worker_monitoring_scheduler.py`

**Changes:**

- ❌ Removed: `_collectors: Dict[str, WorkerMetricsCollector]` registry
- ❌ Removed: `_on_metrics_received()` async routing method
- ✅ Added: `_active_jobs: Dict[str, str]` (worker_id -> job_id mapping)
- ✅ Added: `BackgroundTasksBus` dependency injection
- ✅ Changed: Use `RecurrentTaskDescriptor` to schedule jobs
- ✅ Changed: Subscribe notification handler directly to jobs

**Architecture Change:**

- **Before:** Manual collector registry + asyncio task management
- **After:** APScheduler job management via BackgroundTasksBus
- Jobs are scheduled with `task_descriptor` and tracked by ID

**Key Pattern:**

```python
# Create job instance
job = WorkerMetricsCollectionJob(...)
job.subscribe(self._notification_handler)

# Schedule via BackgroundTasksBus
task_descriptor = RecurrentTaskDescriptor(
    id=job_id,
    name="WorkerMetricsCollectionJob",
    data=job.__dict__,
    interval=self._poll_interval,
)
self._background_task_bus.schedule_task(task_descriptor)
```

---

## 🔧 Recommendations for Background Scheduler

### Issue 1: Missing `stop_task()` Implementation

**Problem:**
The `BackgroundTaskScheduler` has a `stop_task(task_id)` method, but `WorkerMonitoringScheduler.stop_monitoring_worker_async()` currently just removes from tracking without actually stopping the APScheduler job.

**Recommendation:**

```python
# In WorkerMonitoringScheduler, add scheduler reference:
def __init__(
    self,
    ...,
    background_task_scheduler: BackgroundTaskScheduler,  # Add this
):
    self._background_task_scheduler = background_task_scheduler

# Then in stop_monitoring_worker_async():
async def stop_monitoring_worker_async(self, worker_id: str) -> None:
    job_id = self._active_jobs.get(worker_id)
    if job_id:
        # Actually stop the job
        self._background_task_scheduler.stop_task(job_id)
        del self._active_jobs[worker_id]
```

### Issue 2: Job Serialization and Deserialization

**Current Implementation:**

```python
task_descriptor = RecurrentTaskDescriptor(
    id=job_id,
    name="WorkerMetricsCollectionJob",
    data=job.__dict__,  # Serializes all job attributes
    interval=self._poll_interval,
)
```

**Potential Problem:**

- `job.__dict__` includes non-serializable objects like `aws_ec2_client`, `worker_repository`
- When BackgroundTaskScheduler deserializes with `object.__new__()`, these dependencies won't be restored

**Recommendation:**
Consider one of these approaches:

**Option A: Store Only Identifiers**

```python
data = {
    "worker_id": job.worker_id,
    # Dependencies will be re-injected on deserialization
}
```

**Option B: Enhanced Dependency Injection in BackgroundTaskScheduler**
Add a DI container reference to BackgroundTaskScheduler so it can re-inject dependencies when deserializing jobs:

```python
def deserialize_task(self, task_type, task_descriptor):
    task = object.__new__(task_type)

    # Restore simple attributes
    task.__dict__.update(task_descriptor.data)

    # Re-inject dependencies from DI container
    if hasattr(task, '__dependencies__'):
        for dep_name, dep_type in task.__dependencies__.items():
            setattr(task, dep_name, self._service_provider.get_service(dep_type))

    return task
```

### Issue 3: Observer Pattern with Serialization

**Current Pattern:**

```python
job = WorkerMetricsCollectionJob(...)
job.subscribe(self._notification_handler)  # Observer is subscribed
```

**Problem:**
When the job is serialized to Redis (for distributed execution), the observer list (`_observers`) includes the notification handler instance, which won't serialize properly.

**Recommendation:**

**Option A: Re-subscribe After Deserialization**
Add a post-deserialization hook in BackgroundTaskScheduler:

```python
async def enqueue_task_async(self, task: BackgroundJob):
    # Re-subscribe observers after deserialization
    if hasattr(task, '_resubscribe_observers'):
        task._resubscribe_observers()

    # Then schedule the job
    self._scheduler.add_job(...)
```

**Option B: Use Event Bus Instead of Direct Observers**
Replace the observer pattern with a proper event bus:

```python
# In WorkerMetricsCollectionJob.run_every():
# Instead of:
for observer in self._observers:
    observer(metrics_data)

# Use:
await self._event_bus.publish("worker.metrics.collected", metrics_data)

# In WorkerNotificationHandler:
# Subscribe to event bus during initialization
event_bus.subscribe("worker.metrics.collected", self)
```

### Issue 4: Redis Job Store Configuration

**Current Implementation:**
The BackgroundTaskScheduler supports Redis job store, but requires configuration in settings:

```python
job_store_config = {
    "redis_host": "localhost",
    "redis_port": 6379,
    "redis_db": 0,
}
```

**Recommendation:**
Add to your `settings.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Background Task Scheduler Settings
    background_job_store: Dict[str, Any] = {
        "redis_host": "redis",  # Docker service name
        "redis_port": 6379,
        "redis_db": 1,  # Use separate DB from cache
    }
```

### Issue 5: Job Store Persistence

**Observation:**
With Redis job store, jobs persist across application restarts. This means:

- ✅ Jobs survive application crashes
- ⚠️ Jobs may execute on different application instances
- ⚠️ Need to handle job state consistency

**Recommendation:**
Add job state validation in `WorkerMetricsCollectionJob.run_every()`:

```python
async def run_every(self, *args, **kwargs) -> None:
    # 1. Validate worker still exists and is active
    worker = await self.worker_repository.get_by_id_async(self.worker_id)
    if not worker or worker.state.status == CMLWorkerStatus.TERMINATED:
        logger.warning(f"Worker {self.worker_id} no longer active, stopping job")
        # Signal to scheduler that this job should be removed
        raise JobTerminationException(f"Worker {self.worker_id} terminated")
        return

    # 2. Continue with metrics collection
    ...
```

---

## 📋 Next Steps for main.py Integration

### Current Configuration Needs Update

**File:** `src/main.py`, `configure_worker_monitoring()` function

**Required Changes:**

1. **Register BackgroundTaskScheduler** before WorkerMonitoringScheduler:

```python
from application.services import BackgroundTaskScheduler

# In application startup or builder configuration:
BackgroundTaskScheduler.configure(
    builder=app.state.services,  # Or your builder instance
    modules=["application.services"]  # Scan for @backgroundjob classes
)
```

2. **Update WorkerMonitoringScheduler Constructor:**

```python
# Get BackgroundTasksBus from DI
background_task_bus = app.state.services.get_required_service(BackgroundTasksBus)

scheduler = WorkerMonitoringScheduler(
    worker_repository=worker_repository,
    aws_client=aws_client,
    notification_handler=notification_handler,
    background_task_bus=background_task_bus,  # NEW
    poll_interval=app_settings.worker_metrics_poll_interval,
)
```

3. **Update Lifecycle Hooks:**
The BackgroundTaskScheduler is registered as a `HostedService`, so it will start/stop automatically. You only need to manage WorkerMonitoringScheduler:

```python
@app.on_event("startup")
async def start_monitoring() -> None:
    if _monitoring_scheduler:
        # BackgroundTaskScheduler already started by HostedService
        # Just discover and schedule worker monitoring jobs
        await _monitoring_scheduler.start_async()

@app.on_event("shutdown")
async def stop_monitoring() -> None:
    if _monitoring_scheduler:
        # Stop monitoring jobs
        await _monitoring_scheduler.stop_async()
        # BackgroundTaskScheduler will stop automatically
```

---

## 🧪 Testing Recommendations

1. **Unit Tests:**
   - Test `WorkerMetricsCollectionJob.run_every()` with mocked dependencies
   - Test `WorkerNotificationHandler.__call__()` with sample metrics
   - Test `WorkerMonitoringScheduler` job lifecycle (start/stop)

2. **Integration Tests:**
   - Verify APScheduler jobs are created with correct intervals
   - Verify notification handler receives metrics events
   - Verify jobs stop when workers are deleted

3. **Distributed Tests:**
   - Test job persistence across application restarts (with Redis)
   - Test concurrent job execution on multiple instances
   - Test job failover when instance crashes

---

## 🎯 Summary

✅ **Completed:**

- WorkerMetricsCollectionJob with @backgroundjob decorator
- WorkerNotificationHandler as reactive observer
- WorkerMonitoringScheduler with APScheduler integration
- Proper separation of concerns (job vs scheduler vs handler)

⚠️ **Recommendations:**

1. Add job stop implementation in scheduler
2. Handle dependency injection for deserialized jobs
3. Consider event bus instead of direct observers for better serialization
4. Add Redis job store configuration
5. Add job state validation for terminated workers
6. Update main.py configuration (next step)

🚀 **Benefits:**

- Distributed job management with Redis persistence
- Automatic job rescheduling after failures
- Better separation of concerns
- Scalable across multiple application instances
- Eliminates manual asyncio task management
