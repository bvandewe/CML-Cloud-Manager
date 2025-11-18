# Worker Monitoring & Background Jobs Architecture Review

**Review Date**: 2025-11-18
**Reviewer**: Senior Software Architect
**Scope**: Worker monitoring, background job scheduling, command triggers, SSE real-time updates
**Context**: Post-simplification refactoring (removed WorkerMonitoringScheduler, unified to global jobs)

---

## Executive Summary

**Overall Assessment**: ⚠️ **NEEDS IMPROVEMENT** - The architecture has been simplified but contains significant design flaws, redundancies, and unnecessary complexity. For a system managing <100 workers, the current implementation is over-engineered in some areas and under-engineered in others.

**Key Issues Identified**:

1. **Dual metrics collection paths** (background job + command) with overlapping responsibilities
2. **Inefficient SSE event broadcasting** mechanism with no filtering or optimization
3. **Over-engineered background job framework** for simple recurring tasks
4. **Global state anti-pattern** in APScheduler wrapper
5. **Missing batch operations** for database updates
6. **Unclear separation** between on-demand refresh and scheduled monitoring

**Recommendation**: Major refactoring required. Target ~60% code reduction while improving clarity and performance.

---

## Component Analysis

### 1. WorkerMetricsCollectionJob (application/jobs/worker_metrics_collection_job.py)

**Purpose**: Scheduled background job that polls AWS for all active workers every 5 minutes.

**Current Implementation**:

```python
@backgroundjob(task_type="recurrent")
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    async def run_every(self, *args, **kwargs) -> None:
        workers = await worker_repository.get_active_workers_async()
        for worker in workers:
            await self._process_worker_metrics(worker, worker_repository, span)
```

**Issues**:

#### 🔴 Critical: Duplicate Logic with RefreshWorkerMetricsCommand

- **Problem**: 90% code overlap between `_process_worker_metrics()` and `RefreshWorkerMetricsCommandHandler.handle_async()`
- **Impact**: Maintenance nightmare, inconsistent behavior, double the test burden
- **Evidence**: Both implement:
  - EC2 status checks
  - CloudWatch metrics collection
  - Status mapping logic
  - Telemetry updates
  - Error handling

**Root Cause**: Command was created first for on-demand refresh, then job was added without refactoring shared logic.

#### 🟡 Medium: Sequential Processing with No Concurrency

```python
for worker in workers:
    await self._process_worker_metrics(worker, ...)  # Sequential!
```

- **Problem**: With 50 workers, each taking 2 seconds = 100 seconds total
- **Expected**: Concurrent processing with `asyncio.gather()` limited by semaphore
- **Impact**: Slow metrics refresh, stale data in UI

#### 🟡 Medium: N+1 Database Updates

```python
for worker in workers:
    # ... update worker state
    await worker_repository.update_async(worker)  # One DB write per worker!
```

- **Problem**: 100 workers = 100 database round-trips
- **Expected**: Batch updates via `update_many_async()` or bulk write operations
- **Impact**: Database connection pool exhaustion, increased latency

#### 🟢 Good: Simplified to Single Global Job

- **Previous**: One job per worker (over-engineered)
- **Current**: Single job processing all workers (correct for <100 workers)
- **Rationale**: Aligns with LabsRefreshJob pattern, natural batching opportunity

**Code Quality**: 4/10

- Poor separation of concerns
- Excessive duplicate code
- Missing concurrency patterns
- No batch optimization

---

### 2. RefreshWorkerMetricsCommand (application/commands/refresh_worker_metrics_command.py)

**Purpose**: On-demand command to refresh a single worker's metrics (triggered manually or via API).

**Current Implementation**:

```python
class RefreshWorkerMetricsCommandHandler(CommandHandlerBase, CommandHandler[...]):
    async def handle_async(self, request: RefreshWorkerMetricsCommand):
        worker = await self.cml_worker_repository.get_by_id_async(request.worker_id)

        # 1. Query AWS EC2 instance status
        status_checks = self.aws_ec2_client.get_instance_status_checks(...)
        worker.update_ec2_metrics(...)

        # 2. Get instance details (IPs, type, AMI)
        instance_details = self.aws_ec2_client.get_instance_details(...)
        worker.update_ec2_instance_details(...)

        # 3. Query CloudWatch metrics (if running)
        if new_status == CMLWorkerStatus.RUNNING:
            metrics = self.aws_ec2_client.get_instance_resources_utilization(...)
            worker.update_cloudwatch_metrics(...)

        # 4. Health check CML service (if running + endpoint)
        if new_status == CMLWorkerStatus.RUNNING and worker.state.https_endpoint:
            system_health = await health_check_client.get_system_health()
            worker.update_service_status(...)

        # 5. Query CML labs (if service available)
        if worker.state.service_status == CMLServiceStatus.AVAILABLE:
            labs = await cml_client.get_labs_async()
            worker.update_cml_labs(...)

        # 6. Persist to repository
        await self.cml_worker_repository.update_async(worker)

        # 7. Broadcast SSE event
        await self._sse_relay.broadcast_event("worker.metrics.updated", ...)
```

**Issues**:

#### 🔴 Critical: Command Doing Too Much (SRP Violation)

- **Problem**: Single command handles 5 different data sources (EC2, CloudWatch, CML API health, CML API labs, AMI details)
- **Impact**: 684 lines in one file, impossible to test independently, tight coupling
- **Violation**: Single Responsibility Principle - a command should do ONE thing

**Evidence of Complexity**:

- 6 distinct API calls (AWS EC2, CloudWatch, CML health, CML labs, AMI lookup, instance details)
- 5 different update methods on worker aggregate
- Complex conditional logic (if running, if has endpoint, if service available)
- Error handling for each API call

#### 🔴 Critical: Manual SSE Broadcasting Anti-Pattern

```python
await self._sse_relay.broadcast_event("worker.metrics.updated", {
    "worker_id": worker.id(),
    "cpu_utilization": metrics_summary.get("cpu_utilization"),
    # ... 20+ fields manually mapped
})
```

- **Problem**: Command handler directly broadcasting events (breaks Neuroglia's CloudEvent pattern)
- **Expected**: Domain events automatically trigger SSE broadcasts via event handlers
- **Impact**: Events can be missed, inconsistent event schema, duplicate code

**Neuroglia Pattern Violated**:

```python
# Should be:
worker.update_telemetry(...)  # Emits TelemetryUpdatedDomainEvent
await repository.update_async(worker)  # Publishes CloudEvent
# Event handler automatically broadcasts SSE ✓

# Instead doing:
worker.update_telemetry(...)
await repository.update_async(worker)
await self._sse_relay.broadcast_event(...)  # Manual SSE broadcast ✗
```

#### 🟡 Medium: Obsolete Dependency Injection

```python
def __init__(
    self,
    monitoring_scheduler: "WorkerMonitoringScheduler | None" = None,  # Dead code!
):
```

- **Problem**: `WorkerMonitoringScheduler` was deleted but references remain
- **Impact**: Confusing code, misleading documentation, dead imports

**Code Quality**: 3/10

- Violates Single Responsibility Principle
- 684 lines (should be ~100-150 max)
- Bypasses event-driven architecture
- Complex error handling spread across multiple API calls

---

### 3. BackgroundJobsInitializer (application/services/background_jobs_initializer.py)

**Purpose**: HostedService that schedules recurring jobs and runs initial data loads on startup.

**Current Implementation**:

```python
class BackgroundJobsInitializer(HostedService):
    async def start_async(self):
        # 1. Create database indexes
        await lab_record_repository.ensure_indexes_async()

        # 2. Schedule WorkerMetricsCollectionJob (every 5 min)
        background_task_bus.schedule_task(worker_metrics_task)

        # 3. Schedule LabsRefreshJob (every 30 min)
        background_task_bus.schedule_task(labs_refresh_task)

        # 4. Run initial labs refresh
        initial_job = LabsRefreshJob()
        initial_job._service_provider = scope
        await initial_job.run_every()

        # 5. Run initial worker metrics collection
        initial_metrics_job = WorkerMetricsCollectionJob()
        initial_metrics_job._service_provider = scope
        await initial_metrics_job.run_every()
```

**Issues**:

#### 🟡 Medium: Awkward Job Instantiation Pattern

```python
initial_job = LabsRefreshJob()
initial_job._service_provider = scope  # Setting private attribute!
cast(Any, initial_job).configure()     # Type checker defeat!
await initial_job.run_every()
```

- **Problem**: Manual dependency injection bypassing the framework
- **Expected**: Use Mediator pattern or factory method
- **Impact**: Fragile code, breaks encapsulation, defeats type safety

#### 🟢 Good: Proper HostedService Usage

- Correctly implements Neuroglia's HostedService pattern
- Automatic lifecycle management
- Clean DI registration with factory

#### 🟢 Good: Initial Data Load

- Preloads data on startup (good UX)
- Runs synchronously during startup (appropriate for small datasets)

**Better Alternative**:

```python
# Instead of manual instantiation, use commands:
await self.mediator.execute_async(RefreshAllWorkersMetricsCommand())
await self.mediator.execute_async(RefreshAllLabsCommand())
```

**Code Quality**: 6/10

- Correct use of HostedService
- Awkward job instantiation
- Mixed concerns (index creation + job scheduling + initial load)

---

### 4. BackgroundTaskScheduler (application/services/background_scheduler.py)

**Purpose**: APScheduler wrapper with Neuroglia integration, reactive streams, and job persistence.

**Current Implementation**: 781 lines providing:

- Job registration via `@backgroundjob` decorator
- Scheduled and recurrent job support
- Redis/MongoDB persistence
- Reactive streams (Rx.Subject) for job requests
- Custom serialization (pickle-free for service providers)

**Issues**:

#### 🔴 Critical: Global State Anti-Pattern

```python
# Module-level global variable
_global_service_provider = None

async def start_async(self):
    global _global_service_provider
    _global_service_provider = self._service_provider  # Sets global!

async def recurrent_job_wrapper(...):
    task.configure(service_provider=_global_service_provider)  # Uses global!
```

- **Problem**: Global mutable state breaks testability, causes race conditions in tests, violates DI principles
- **Expected**: Pass service provider through job context or use contextvar
- **Impact**: Tests must run serially, cannot run multiple app instances in same process

#### 🟡 Medium: Over-Engineered for Requirements

**Features Not Needed for <100 Workers**:

- Redis/MongoDB persistence (memory store sufficient)
- Reactive streams with Rx.Subject (simple asyncio.Queue would work)
- Custom serialization framework (just use dataclasses)
- BackgroundTasksBus abstraction (direct scheduler access simpler)

**Code Complexity**:

- 781 lines for what should be ~200 lines
- Multiple abstraction layers (Job → TaskDescriptor → APScheduler Job)
- Complex serialization logic (custom `__getstate__`/`__setstate__`)

#### 🟡 Medium: Leaky Abstraction

```python
# Job must know about APScheduler's serialization:
def __getstate__(self):
    state = self.__dict__.copy()
    state["aws_ec2_client"] = None  # Don't serialize client
    state["_service_provider"] = None  # Don't serialize provider
    return state
```

- **Problem**: Domain jobs polluted with infrastructure concerns
- **Expected**: Serialization handled transparently by framework

**Simpler Alternative** (for <100 workers):

```python
class SimpleRecurringJob:
    """Just schedule a coroutine to run periodically."""
    def __init__(self, interval: int, coro_func, *args, **kwargs):
        self.interval = interval
        self.coro_func = coro_func
        self.args = args
        self.kwargs = kwargs
        self._task = None

    async def start(self):
        async def runner():
            while True:
                await self.coro_func(*self.args, **self.kwargs)
                await asyncio.sleep(self.interval)
        self._task = asyncio.create_task(runner())

    async def stop(self):
        if self._task:
            self._task.cancel()

# Usage:
jobs = [
    SimpleRecurringJob(300, collect_worker_metrics, service_provider),
    SimpleRecurringJob(1800, refresh_labs, service_provider),
]
```

**When APScheduler Makes Sense**:

- Job persistence across restarts required
- Complex scheduling (cron expressions, calendars)
- Distributed job execution
- >1000 jobs with different schedules

**Current Needs**: 2-3 simple recurring jobs with fixed intervals.

**Code Quality**: 4/10

- Global state anti-pattern
- Over-engineered for requirements
- Leaky abstractions
- Poor testability

---

### 5. SSEEventRelay (application/services/sse_event_relay.py)

**Purpose**: Broadcast real-time events to connected web clients via Server-Sent Events.

**Current Implementation**:

```python
class SSEEventRelay:
    def __init__(self):
        self._clients: Dict[str, asyncio.Queue] = {}

    async def broadcast_event(self, event_type: str, data: dict, source: str):
        event_message = {
            "type": event_type,
            "source": source,
            "time": datetime.utcnow().isoformat() + "Z",
            "data": data,
        }
        async with self._lock:
            client_queues = list(self._clients.values())

        for queue in client_queues:
            try:
                await asyncio.wait_for(queue.put(event_message), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning("SSE client queue full, event dropped")
```

**Issues**:

#### 🔴 Critical: No Event Filtering or Subscription Management

- **Problem**: ALL events broadcast to ALL clients regardless of interest
- **Impact**:
  - Client A viewing worker 1 receives updates for workers 2-100
  - Wasted bandwidth (99% of events irrelevant)
  - Frontend must filter (inefficient)

**Example Waste**:

```
100 workers × 5 min poll = 20 events/min
10 connected clients = 200 events/min total
Each client interested in 1 worker = 180 wasted events/min (90% waste)
```

**Expected Pattern**:

```python
class SSEEventRelay:
    def __init__(self):
        self._subscriptions: Dict[str, Set[str]] = {}  # client_id -> {worker_ids}

    async def subscribe(self, client_id: str, filters: dict):
        """Subscribe client to specific workers, event types, etc."""
        self._subscriptions[client_id] = filters.get("worker_ids", set())

    async def broadcast_event(self, event_type: str, data: dict):
        """Only send to subscribed clients."""
        worker_id = data.get("worker_id")
        for client_id, queue in self._clients.items():
            filters = self._subscriptions.get(client_id, set())
            if not filters or worker_id in filters:
                await queue.put(...)
```

#### 🟡 Medium: Inefficient Lock Usage

```python
async with self._lock:
    client_queues = list(self._clients.values())  # Copy under lock

for queue in client_queues:  # Then iterate outside lock
    await asyncio.wait_for(queue.put(event_message), timeout=0.1)
```

- **Problem**: Copying dict values under lock not necessary (dict iteration is atomic in Python)
- **Better**: Use `asyncio.Lock` only for add/remove, not for broadcast

#### 🟢 Good: Simple Queue-Based Fan-Out

- Correctly uses one queue per client
- Handles slow consumers with timeout
- Clean connection/disconnection lifecycle

**Code Quality**: 5/10

- No filtering (critical for scaling)
- Inefficient lock usage
- Missing subscription management
- Otherwise clean implementation

---

### 6. Domain Event Handlers (application/events/domain/cml_worker_events.py)

**Purpose**: React to worker domain events and broadcast SSE updates.

**Current Implementation**:

```python
class CMLWorkerTelemetryUpdatedDomainEventHandler(
    DomainEventHandler[CMLWorkerTelemetryUpdatedDomainEvent]
):
    def __init__(self, sse_relay: SSEEventRelay, monitoring_scheduler: ...):
        self._sse_relay = sse_relay
        self._monitoring_scheduler = monitoring_scheduler  # Dead reference!

    async def handle_async(self, notification: ...):
        await self._sse_relay.broadcast_event(
            event_type="worker.telemetry.updated",
            data={...}
        )
```

**Issues**:

#### 🟡 Medium: Dead Code - WorkerMonitoringScheduler References

```python
self._monitoring_scheduler: "WorkerMonitoringScheduler | None" = None
```

- **Problem**: `WorkerMonitoringScheduler` was deleted but references remain
- **Found in**:
  - `CMLWorkerTerminatedDomainEventHandler.__init__`
  - `CMLWorkerTelemetryUpdatedDomainEventHandler.__init__`
- **Impact**: Confusing code, dead imports, misleading type hints

#### 🟢 Good: Clean Event → SSE Translation

- Correctly implements Neuroglia's DomainEventHandler pattern
- Each event type has dedicated handler
- Decoupled from command handlers

**Code Quality**: 7/10

- Clean event handling pattern
- Dead code to remove
- Otherwise well-structured

---

### 7. EventsController (api/controllers/events_controller.py)

**Purpose**: SSE HTTP endpoint (`GET /api/events/stream`) for frontend clients.

**Current Implementation**:

```python
class EventsController(ControllerBase):
    async def _event_generator(self, request: Request, user_info: dict):
        client_id, event_queue = await self._sse_relay.register_client()

        # Stream events with heartbeat
        while True:
            if await request.is_disconnected():
                break

            try:
                event_message = await asyncio.wait_for(
                    event_queue.get(), timeout=heartbeat_interval
                )
                yield f"event: {event_type}\ndata: {json.dumps(event_message)}\n\n"
            except asyncio.TimeoutError:
                yield f"event: heartbeat\ndata: ...\n\n"

    @get_route("/stream")
    async def stream_events(self, request: Request, user_info: dict):
        return StreamingResponse(
            self._event_generator(request, user_info),
            media_type="text/event-stream",
        )
```

**Issues**:

#### 🟢 Good: Correct SSE Implementation

- Proper SSE format (`event: type\ndata: json\n\n`)
- Heartbeat to detect dead connections
- Graceful disconnect handling
- CORS headers set correctly

#### 🟡 Medium: No Query Parameters for Filtering

```python
# Current:
GET /api/events/stream  # Receives ALL events

# Expected:
GET /api/events/stream?worker_ids=abc,def&event_types=metrics,status
```

- **Problem**: Cannot subscribe to specific workers or event types
- **Impact**: Client receives all events, must filter client-side

**Code Quality**: 8/10

- Correct SSE implementation
- Missing subscription filtering
- Clean error handling

---

## Data Flow Analysis

### Current Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Triggers (API/UI)                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │ RefreshWorkerMetricsCommand │  (On-demand, single worker)
              └─────────────┬───────────────┘
                            │
                            ├─► Query AWS EC2 Status
                            ├─► Query AWS CloudWatch Metrics
                            ├─► Query CML API Health
                            ├─► Query CML API Labs
                            ├─► Update Worker Aggregate
                            ├─► Persist to MongoDB
                            └─► Broadcast SSE Event (manual)
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BackgroundJobsInitializer                      │
│                       (on app startup)                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
  Schedule Jobs      Run Initial Load    Create Indexes
          │                 │
          │                 └─► WorkerMetricsCollectionJob.run_every()
          │                 └─► LabsRefreshJob.run_every()
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│              BackgroundTaskScheduler (APScheduler)               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  WorkerMetricsCollectionJob (every 5 min)              │    │
│  │    ├─► Get all active workers                          │    │
│  │    └─► For each worker:                                │    │
│  │        ├─► Query AWS EC2 Status                        │    │
│  │        ├─► Query AWS CloudWatch Metrics                │    │
│  │        ├─► Update Worker State                         │    │
│  │        └─► Persist to MongoDB (N writes!)              │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  LabsRefreshJob (every 30 min)                         │    │
│  │    ├─► Get all workers with CML service available      │    │
│  │    └─► For each worker:                                │    │
│  │        ├─► Query CML API for labs                      │    │
│  │        └─► Update LabRecord collection                 │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │   Domain Event Emitted     │
              │  (TelemetryUpdatedEvent,   │
              │   StatusChangedEvent, etc) │
              └─────────────┬──────────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │  CloudEventMiddleware      │
              │  (publishes to event bus)  │
              └─────────────┬──────────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │   Domain Event Handlers    │
              │  (CMLWorkerEventsHandlers) │
              └─────────────┬──────────────┘
                            │
                            └─► SSEEventRelay.broadcast_event()
                                        │
                                        ▼
              ┌────────────────────────────────┐
              │   Connected SSE Clients        │
              │  (EventsController /stream)    │
              │   ├─► Client A (all events)    │
              │   ├─► Client B (all events)    │
              │   └─► Client C (all events)    │
              └────────────────────────────────┘
                            │
                            ▼
              ┌────────────────────────────────┐
              │   Frontend (Browser)           │
              │   ├─► Filter relevant events   │
              │   ├─► Update UI components     │
              │   └─► Cache worker state       │
              └────────────────────────────────┘
```

### Issues Highlighted in Flow

1. **Duplicate Code Path**: `RefreshWorkerMetricsCommand` and `WorkerMetricsCollectionJob._process_worker_metrics()` do the same thing
2. **N+1 Database Problem**: Background job updates workers one at a time
3. **Broadcast Storm**: All events sent to all clients (no filtering)
4. **Manual SSE in Command**: Bypasses event-driven architecture

---

## Performance Impact Analysis

### Current System with 100 Workers

**Metrics Collection Cycle (every 5 minutes)**:

```
100 workers × 2 sec each (sequential) = 200 seconds total
100 workers × 1 DB write each = 100 DB round-trips
100 workers × 1 SSE event each = 1000 SSE messages (10 clients)

Actual wall time: ~200 seconds (sequential processing)
Database load: 100 writes/5min = 0.33 writes/sec (acceptable)
SSE bandwidth: 1000 events/5min = 3.33 events/sec (wasteful)
```

**With Concurrent Processing**:

```
100 workers ÷ 10 concurrent = 10 batches
10 batches × 2 sec each = 20 seconds total (10x faster!)
Batch DB updates: 1 bulk write = 1 DB round-trip (100x less!)
```

**SSE Broadcast Storm Example**:

```
10 connected clients × 100 worker events = 1000 messages
If each client viewing 1 worker:
  Relevant: 10 messages (1%)
  Wasted: 990 messages (99%)
```

---

## Recommendations

### Priority 1: Critical Fixes (Must Do)

#### 1.1 Eliminate Duplicate Metrics Collection Logic

**Problem**: 90% code overlap between command and job.

**Solution**: Extract shared logic to service class.

```python
# NEW: application/services/worker_metrics_service.py
class WorkerMetricsService:
    """Centralized service for collecting worker metrics from AWS."""

    def __init__(self, aws_ec2_client: AwsEc2Client):
        self._aws_client = aws_ec2_client

    async def refresh_worker_metrics(
        self,
        worker: CMLWorker,
        include_cml_api: bool = False
    ) -> MetricsResult:
        """Collect metrics for a single worker.

        Args:
            worker: Worker entity to update
            include_cml_api: Whether to query CML API (slower)

        Returns:
            MetricsResult with collected data
        """
        # 1. Query AWS EC2
        status = self._aws_client.get_instance_status_checks(...)
        worker.update_ec2_metrics(...)

        # 2. Query CloudWatch (if running)
        if worker.state.status == CMLWorkerStatus.RUNNING:
            metrics = self._aws_client.get_instance_resources_utilization(...)
            worker.update_cloudwatch_metrics(...)

        # 3. Query CML API (optional)
        if include_cml_api and worker.state.https_endpoint:
            health = await self._query_cml_health(worker)
            worker.update_service_status(health)

        return MetricsResult(worker=worker, updated_fields=[...])

# Usage in command:
class RefreshWorkerMetricsCommandHandler:
    async def handle_async(self, request: RefreshWorkerMetricsCommand):
        worker = await self.repository.get_by_id_async(request.worker_id)
        result = await self.metrics_service.refresh_worker_metrics(
            worker, include_cml_api=True  # Full refresh for on-demand
        )
        await self.repository.update_async(worker)
        # Domain events automatically trigger SSE broadcasts ✓
        return OperationResult.success(result.to_dict())

# Usage in background job:
class WorkerMetricsCollectionJob:
    async def run_every(self):
        workers = await self.repository.get_active_workers_async()

        # Concurrent processing with semaphore
        semaphore = asyncio.Semaphore(10)
        async def process_worker(worker):
            async with semaphore:
                result = await self.metrics_service.refresh_worker_metrics(
                    worker, include_cml_api=False  # Skip CML API for background
                )
                return worker

        # Gather all updates
        updated_workers = await asyncio.gather(
            *[process_worker(w) for w in workers],
            return_exceptions=True
        )

        # Batch database update
        valid_workers = [w for w in updated_workers if not isinstance(w, Exception)]
        await self.repository.update_many_async(valid_workers)
```

**Impact**:

- ✅ Eliminate 300+ lines of duplicate code
- ✅ Single source of truth for metrics logic
- ✅ Easier testing (mock service instead of AWS client)
- ✅ Clear separation: service = logic, command/job = orchestration

---

#### 1.2 Add Concurrent Processing to Background Job

**Problem**: Sequential processing takes 200 seconds for 100 workers.

**Solution**: Use `asyncio.gather()` with semaphore.

```python
class WorkerMetricsCollectionJob:
    async def run_every(self):
        workers = await self.repository.get_active_workers_async()

        # Limit concurrent AWS API calls (avoid rate limiting)
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent

        async def process_with_semaphore(worker):
            async with semaphore:
                return await self._process_worker_metrics(worker)

        # Process all workers concurrently
        results = await asyncio.gather(
            *[process_with_semaphore(w) for w in workers],
            return_exceptions=True  # Don't fail entire batch on one error
        )

        # Filter out errors
        updated_workers = [r for r in results if not isinstance(r, Exception)]

        # Batch update
        await self.repository.update_many_async(updated_workers)
```

**Impact**:

- ✅ 10x faster (200s → 20s for 100 workers)
- ✅ Fresher data in UI
- ✅ Better resource utilization

---

#### 1.3 Implement SSE Event Filtering

**Problem**: All events broadcast to all clients (99% waste).

**Solution**: Add subscription management to SSEEventRelay.

```python
class SSEEventRelay:
    def __init__(self):
        self._clients: Dict[str, ClientSubscription] = {}

    async def register_client(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple[str, asyncio.Queue]:
        """Register client with optional filters.

        Args:
            filters: {
                "worker_ids": ["abc", "def"],  # Only these workers
                "event_types": ["metrics", "status"],  # Only these types
            }
        """
        client_id = str(uuid4())
        subscription = ClientSubscription(
            queue=asyncio.Queue(),
            filters=filters or {}
        )
        async with self._lock:
            self._clients[client_id] = subscription
        return client_id, subscription.queue

    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast to subscribed clients only."""
        worker_id = data.get("worker_id")

        async with self._lock:
            subscriptions = list(self._clients.values())

        for subscription in subscriptions:
            # Check filters
            if not self._matches_filters(event_type, worker_id, subscription.filters):
                continue

            try:
                await asyncio.wait_for(
                    subscription.queue.put({
                        "type": event_type,
                        "data": data,
                        "time": datetime.utcnow().isoformat() + "Z",
                    }),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                logger.warning(f"Client queue full, event dropped")

    def _matches_filters(
        self,
        event_type: str,
        worker_id: Optional[str],
        filters: dict
    ) -> bool:
        """Check if event matches client filters."""
        # No filters = subscribe to all
        if not filters:
            return True

        # Check worker_id filter
        worker_filter = filters.get("worker_ids", [])
        if worker_filter and worker_id not in worker_filter:
            return False

        # Check event_type filter
        type_filter = filters.get("event_types", [])
        if type_filter:
            # Extract base type (e.g., "worker.metrics.updated" → "metrics")
            base_type = event_type.split(".")[1] if "." in event_type else event_type
            if base_type not in type_filter:
                return False

        return True

# Update controller to accept filters:
class EventsController:
    @get_route("/stream")
    async def stream_events(
        self,
        request: Request,
        user_info: dict = Depends(get_current_user),
        worker_ids: Optional[str] = None,  # Query param: ?worker_ids=abc,def
        event_types: Optional[str] = None,  # Query param: ?event_types=metrics,status
    ):
        filters = {}
        if worker_ids:
            filters["worker_ids"] = worker_ids.split(",")
        if event_types:
            filters["event_types"] = event_types.split(",")

        client_id, event_queue = await self._sse_relay.register_client(filters)
        # ... rest of implementation
```

**Impact**:

- ✅ 99% reduction in unnecessary SSE messages
- ✅ Lower bandwidth consumption
- ✅ Better client performance (no client-side filtering)
- ✅ Scalable to 1000+ workers

---

#### 1.4 Remove Global State from BackgroundTaskScheduler

**Problem**: `_global_service_provider` breaks testability.

**Solution**: Use `contextvars` or pass via job kwargs.

```python
# Option A: Use contextvars (recommended)
from contextvars import ContextVar

_service_provider_ctx: ContextVar[ServiceProviderBase] = ContextVar(
    'service_provider', default=None
)

class BackgroundTaskScheduler:
    async def start_async(self):
        # Set context var (thread-safe, async-safe)
        _service_provider_ctx.set(self._service_provider)
        self._scheduler.start()

async def recurrent_job_wrapper(...):
    # Get from context
    service_provider = _service_provider_ctx.get()
    if hasattr(task, "configure"):
        task.configure(service_provider=service_provider)

# Option B: Pass via kwargs (simpler)
class BackgroundTaskScheduler:
    async def enqueue_task_async(self, task: BackgroundJob):
        self._scheduler.add_job(
            recurrent_job_wrapper,
            kwargs={
                "task_type_name": task.__task_name__,
                "task_data": task_data,
                "service_provider_id": id(self._service_provider),  # Store ID
            }
        )

# Store in instance variable instead of global
class BackgroundTaskScheduler:
    _instances: Dict[int, 'BackgroundTaskScheduler'] = {}  # Class variable

    def __init__(self, ...):
        self._instance_id = id(self)
        BackgroundTaskScheduler._instances[self._instance_id] = self

async def recurrent_job_wrapper(service_provider_id: int, ...):
    scheduler = BackgroundTaskScheduler._instances.get(service_provider_id)
    if scheduler:
        task.configure(service_provider=scheduler._service_provider)
```

**Impact**:

- ✅ Tests can run in parallel
- ✅ Multiple app instances in same process
- ✅ Proper dependency injection

---

### Priority 2: Simplifications (Should Do)

#### 2.1 Replace APScheduler with Simple AsyncIO Tasks

**Problem**: 781 lines of APScheduler wrapper for 2 recurring jobs.

**Solution**: Use asyncio.create_task() with simple loop.

```python
# NEW: application/services/simple_scheduler.py (50 lines vs 781!)
class SimpleRecurringScheduler(HostedService):
    """Simple recurring task scheduler using asyncio.

    Suitable for small-scale deployments (<100 workers) with
    fixed-interval recurring tasks.
    """

    def __init__(self, service_provider: ServiceProviderBase):
        self._service_provider = service_provider
        self._tasks: List[asyncio.Task] = []
        self._jobs: List[RecurringJob] = []

    def add_job(
        self,
        job_func: Callable,
        interval_seconds: int,
        job_id: str,
        **kwargs
    ):
        """Add a recurring job."""
        job = RecurringJob(
            job_id=job_id,
            job_func=job_func,
            interval=interval_seconds,
            kwargs=kwargs
        )
        self._jobs.append(job)

    async def start_async(self):
        """Start all registered jobs."""
        for job in self._jobs:
            task = asyncio.create_task(self._run_job_loop(job))
            self._tasks.append(task)
        logger.info(f"Started {len(self._jobs)} recurring jobs")

    async def stop_async(self):
        """Stop all jobs."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Stopped all recurring jobs")

    async def _run_job_loop(self, job: RecurringJob):
        """Run a job in a loop with fixed interval."""
        while True:
            try:
                logger.debug(f"Running job: {job.job_id}")
                await job.job_func(**job.kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in job {job.job_id}: {e}", exc_info=True)

            await asyncio.sleep(job.interval)

@dataclass
class RecurringJob:
    job_id: str
    job_func: Callable
    interval: int
    kwargs: dict

# Usage in BackgroundJobsInitializer:
class BackgroundJobsInitializer(HostedService):
    async def start_async(self):
        scheduler = SimpleRecurringScheduler(self._service_provider)

        # Add jobs
        scheduler.add_job(
            job_func=self._collect_worker_metrics,
            interval_seconds=300,
            job_id="worker-metrics",
        )
        scheduler.add_job(
            job_func=self._refresh_labs,
            interval_seconds=1800,
            job_id="labs-refresh",
        )

        await scheduler.start_async()

    async def _collect_worker_metrics(self):
        """Simple function - no complex job classes needed."""
        scope = self._service_provider.create_scope()
        try:
            repository = scope.get_required_service(CMLWorkerRepository)
            metrics_service = scope.get_required_service(WorkerMetricsService)

            workers = await repository.get_active_workers_async()
            # ... process workers
        finally:
            scope.dispose()
```

**When to Use Each**:

| Requirement | Simple Scheduler | APScheduler |
|------------|------------------|-------------|
| Fixed intervals (5 min, 30 min) | ✅ Perfect | ⚠️ Overkill |
| Cron expressions (daily at 3am) | ❌ | ✅ |
| Job persistence (survive restarts) | ❌ | ✅ |
| <10 recurring jobs | ✅ Perfect | ⚠️ Overkill |
| >100 jobs with varying schedules | ❌ | ✅ |
| Distributed execution | ❌ | ✅ |

**Impact**:

- ✅ Eliminate 700+ lines of complex code
- ✅ Easier to understand and debug
- ✅ Faster startup (no APScheduler init)
- ✅ No global state issues

---

#### 2.2 Split RefreshWorkerMetricsCommand into Focused Commands

**Problem**: 684-line command doing 5 different things.

**Solution**: Create separate commands for each concern.

```python
# NEW: application/commands/sync_worker_ec2_status_command.py (100 lines)
class SyncWorkerEC2StatusCommand(Command[OperationResult]):
    """Sync worker status with AWS EC2 instance state."""
    worker_id: str

class SyncWorkerEC2StatusCommandHandler(CommandHandlerBase, ...):
    async def handle_async(self, request):
        # Only EC2 logic - ~100 lines
        worker = await self.repository.get_by_id_async(request.worker_id)
        status_checks = self.aws_client.get_instance_status_checks(...)
        worker.update_ec2_metrics(...)
        await self.repository.update_async(worker)
        return OperationResult.success()

# NEW: application/commands/collect_worker_cloudwatch_metrics_command.py (80 lines)
class CollectWorkerCloudWatchMetricsCommand(Command[OperationResult]):
    """Collect CloudWatch metrics for a running worker."""
    worker_id: str

class CollectWorkerCloudWatchMetricsCommandHandler(...):
    async def handle_async(self, request):
        # Only CloudWatch logic - ~80 lines
        worker = await self.repository.get_by_id_async(request.worker_id)
        if worker.state.status != CMLWorkerStatus.RUNNING:
            return OperationResult.bad_request("Worker not running")

        metrics = self.aws_client.get_instance_resources_utilization(...)
        worker.update_cloudwatch_metrics(...)
        await self.repository.update_async(worker)
        return OperationResult.success(metrics)

# NEW: application/commands/sync_worker_cml_labs_command.py (120 lines)
class SyncWorkerCMLLabsCommand(Command[OperationResult]):
    """Sync CML labs from worker's CML API."""
    worker_id: str

class SyncWorkerCMLLabsCommandHandler(...):
    async def handle_async(self, request):
        # Only CML API logic - ~120 lines
        worker = await self.repository.get_by_id_async(request.worker_id)
        cml_client = CMLApiClient(base_url=worker.state.https_endpoint, ...)
        labs = await cml_client.get_labs_async()
        worker.update_cml_labs(labs)
        await self.repository.update_async(worker)
        return OperationResult.success(labs)

# MODIFIED: application/commands/refresh_worker_metrics_command.py (50 lines!)
class RefreshWorkerMetricsCommand(Command[OperationResult]):
    """Orchestrate full worker metrics refresh (all sources)."""
    worker_id: str
    include_cml_api: bool = True

class RefreshWorkerMetricsCommandHandler(...):
    async def handle_async(self, request):
        """Orchestrate multiple focused commands."""
        results = []

        # 1. Sync EC2 status
        result = await self.mediator.execute_async(
            SyncWorkerEC2StatusCommand(worker_id=request.worker_id)
        )
        results.append(result)

        # 2. Collect CloudWatch metrics (if running)
        result = await self.mediator.execute_async(
            CollectWorkerCloudWatchMetricsCommand(worker_id=request.worker_id)
        )
        results.append(result)

        # 3. Sync CML labs (optional)
        if request.include_cml_api:
            result = await self.mediator.execute_async(
                SyncWorkerCMLLabsCommand(worker_id=request.worker_id)
            )
            results.append(result)

        # Aggregate results
        return OperationResult.success({
            "worker_id": request.worker_id,
            "sources_synced": len([r for r in results if r.is_success]),
            "errors": [r.error for r in results if not r.is_success],
        })
```

**Benefits**:

- ✅ Each command <150 lines (SRP compliance)
- ✅ Independent testing per data source
- ✅ Reusable commands (background job can call specific ones)
- ✅ Clear API (consumers choose what to refresh)

**Backward Compatibility**:
Keep `RefreshWorkerMetricsCommand` as orchestrator - existing API calls work unchanged.

---

#### 2.3 Remove Dead Code (WorkerMonitoringScheduler References)

**Problem**: References to deleted `WorkerMonitoringScheduler` remain.

**Files to Update**:

```python
# application/events/domain/cml_worker_events.py
class CMLWorkerTerminatedDomainEventHandler:
    def __init__(
        self,
        sse_relay: SSEEventRelay,
        monitoring_scheduler: ... = None,  # ← DELETE THIS
    ):
        self._monitoring_scheduler = monitoring_scheduler  # ← DELETE THIS

# application/commands/refresh_worker_metrics_command.py
class RefreshWorkerMetricsCommandHandler:
    def __init__(
        self,
        ...,
        monitoring_scheduler: ... = None,  # ← DELETE THIS
    ):
        self._monitoring_scheduler = monitoring_scheduler  # ← DELETE THIS
```

**Impact**:

- ✅ Cleaner code
- ✅ No misleading type hints
- ✅ Easier to understand

---

### Priority 3: Future Improvements (Nice to Have)

#### 3.1 Add Repository Batch Operations

```python
# domain/repositories/cml_worker_repository.py
class CMLWorkerRepository(ABC):
    @abstractmethod
    async def update_many_async(
        self,
        workers: List[CMLWorker]
    ) -> int:
        """Update multiple workers in a single database operation.

        Returns:
            Number of workers updated
        """
        pass

# integration/repositories/motor_cml_worker_repository.py
class MongoCMLWorkerRepository(CMLWorkerRepository):
    async def update_many_async(self, workers: List[CMLWorker]) -> int:
        """Bulk update workers using MongoDB bulk_write."""
        if not workers:
            return 0

        operations = []
        for worker in workers:
            serialized = self._serializer.serialize(worker.state)
            operations.append(
                UpdateOne(
                    {"_id": worker.id()},
                    {"$set": serialized},
                )
            )

        result = await self._collection.bulk_write(operations, ordered=False)
        return result.modified_count
```

**Impact**:

- ✅ 100x fewer database round-trips
- ✅ Faster background job execution
- ✅ Lower database load

---

#### 3.2 Add OpenTelemetry Tracing to Background Jobs

```python
class WorkerMetricsCollectionJob:
    @tracer.start_as_current_span("worker_metrics_collection_job")
    async def run_every(self):
        span = trace.get_current_span()
        span.set_attribute("worker_count", len(workers))

        # ... job logic

        span.set_attribute("duration_seconds", elapsed)
        span.set_attribute("workers_updated", updated_count)
        span.set_attribute("errors_count", error_count)
```

**Impact**:

- ✅ Visibility into job performance
- ✅ Detect slow workers
- ✅ Track error rates

---

#### 3.3 Add Health Checks for Background Jobs

```python
# application/services/background_jobs_health.py
class BackgroundJobsHealthCheck:
    """Health check for monitoring job execution."""

    def __init__(self, scheduler: BackgroundTaskScheduler):
        self._scheduler = scheduler
        self._last_execution: Dict[str, datetime] = {}

    def record_execution(self, job_id: str):
        """Record successful job execution."""
        self._last_execution[job_id] = datetime.now(timezone.utc)

    async def check_health(self) -> HealthCheckResult:
        """Check if jobs are executing on schedule."""
        now = datetime.now(timezone.utc)
        unhealthy_jobs = []

        for job_id, last_run in self._last_execution.items():
            time_since_last = (now - last_run).total_seconds()

            # Job should run every 5 minutes (300s) + 60s grace period
            if time_since_last > 360:
                unhealthy_jobs.append({
                    "job_id": job_id,
                    "last_run": last_run.isoformat(),
                    "seconds_overdue": time_since_last - 300,
                })

        if unhealthy_jobs:
            return HealthCheckResult(
                status="unhealthy",
                message=f"{len(unhealthy_jobs)} jobs overdue",
                details=unhealthy_jobs,
            )

        return HealthCheckResult(status="healthy")
```

---

## Recommended Refactoring Roadmap

### Phase 1: Critical Fixes (1-2 days)

**Goal**: Eliminate duplicates, add concurrency, fix SSE filtering

1. ✅ Create `WorkerMetricsService` class (extract shared logic)
2. ✅ Update `RefreshWorkerMetricsCommand` to use service
3. ✅ Update `WorkerMetricsCollectionJob` to use service
4. ✅ Add concurrent processing with `asyncio.gather()`
5. ✅ Add `update_many_async()` to repository
6. ✅ Implement SSE event filtering
7. ✅ Remove WorkerMonitoringScheduler dead code
8. ✅ Fix global state in BackgroundTaskScheduler (use contextvars)

**Expected Impact**:

- ~400 lines removed (duplicate code)
- 10x faster background jobs
- 90% reduction in SSE bandwidth

---

### Phase 2: Simplifications (2-3 days)

**Goal**: Replace APScheduler, split command

9. ✅ Implement `SimpleRecurringScheduler` (50 lines)
10. ✅ Migrate jobs to SimpleRecurringScheduler
11. ✅ Delete BackgroundTaskScheduler (remove 781 lines)
12. ✅ Split RefreshWorkerMetricsCommand into focused commands:
    - `SyncWorkerEC2StatusCommand`
    - `CollectWorkerCloudWatchMetricsCommand`
    - `SyncWorkerCMLLabsCommand`
13. ✅ Update RefreshWorkerMetricsCommand to orchestrate sub-commands

**Expected Impact**:

- ~700 lines removed (APScheduler wrapper)
- ~400 lines removed (command split)
- Clearer separation of concerns

---

### Phase 3: Polish (1 day)

**Goal**: Add observability, health checks

14. ✅ Add OpenTelemetry spans to background jobs
15. ✅ Implement BackgroundJobsHealthCheck
16. ✅ Add job execution metrics
17. ✅ Update documentation

**Expected Impact**:

- Better visibility
- Proactive monitoring

---

## Code Quality Summary

| Component | Current Lines | Issues | Recommended Lines | Quality Score |
|-----------|--------------|--------|-------------------|---------------|
| WorkerMetricsCollectionJob | 350 | Duplicate logic, no concurrency, N+1 DB | 150 | 4/10 |
| RefreshWorkerMetricsCommand | 684 | Too complex, SRP violation, manual SSE | 50 (+ 3×100) | 3/10 |
| BackgroundJobsInitializer | 171 | Awkward instantiation | 120 | 6/10 |
| BackgroundTaskScheduler | 781 | Over-engineered, global state | 50 (simple) | 4/10 |
| SSEEventRelay | 119 | No filtering | 180 (with filters) | 5/10 |
| EventsController | 150 | No query params | 170 (with filters) | 8/10 |
| Domain Event Handlers | 200 | Dead code | 150 | 7/10 |
| **TOTAL** | **2,455** | Multiple critical issues | **1,020** | **~5/10** |

**Overall Reduction**: 2,455 → 1,020 lines (**58% reduction**)

---

## Neuroglia Framework Alignment

### What's Done Well ✅

1. **HostedService Pattern**: Correctly used for BackgroundJobsInitializer
2. **Domain Events**: Properly emitted from aggregates
3. **CloudEventMiddleware**: Automatic event publishing
4. **DomainEventHandlers**: Clean event → SSE translation
5. **Repository Pattern**: Clean abstraction with Motor implementation
6. **Command/Query Separation**: CQRS boundaries mostly respected

### What Needs Improvement ⚠️

1. **Event-Driven Architecture**: Command handler manually broadcasting SSE (should be automatic via domain events)
2. **Service Layer**: Missing - shared logic duplicated in command/job
3. **Batch Operations**: Not using Neuroglia's bulk repository patterns
4. **Reactive Streams**: Background scheduler uses Rx.Subject but not leveraging reactive composition

### Recommendations for Neuroglia Alignment

```python
# 1. Let domain events trigger SSE automatically
worker.update_telemetry(...)  # Emits TelemetryUpdatedDomainEvent
await repository.update_async(worker)  # Publishes CloudEvent
# DomainEventHandler automatically broadcasts SSE ✓

# 2. Use Mediator for orchestration
class RefreshWorkerMetricsCommand:
    async def handle_async(self, request):
        # Compose multiple focused commands
        await self.mediator.execute_async(SyncWorkerEC2StatusCommand(...))
        await self.mediator.execute_async(CollectMetricsCommand(...))

# 3. Extract shared logic to service layer
class WorkerMetricsService:
    """Service layer between application and infrastructure."""
    async def refresh_metrics(self, worker: CMLWorker):
        # Shared logic used by both command and job

# 4. Use reactive composition (optional for advanced use cases)
from neuroglia.reactive import AsyncRx

# Compose multiple async operations reactively
metrics_stream = AsyncRx.from_async(self._collect_metrics)
status_stream = AsyncRx.from_async(self._check_status)
combined = AsyncRx.combine_latest(metrics_stream, status_stream)
```

---

## Testing Recommendations

### Current Gaps

- ❌ No integration tests for background jobs
- ❌ No tests for SSE filtering
- ❌ No performance tests for concurrent processing
- ❌ Difficult to test due to global state

### Recommended Test Structure

```python
# tests/integration/test_worker_metrics_collection.py
@pytest.mark.asyncio
async def test_concurrent_metrics_collection():
    """Test that metrics collection processes workers concurrently."""
    # Create 50 mock workers
    workers = [create_mock_worker() for _ in range(50)]

    # Time the collection
    start = time.time()
    await metrics_job.run_every()
    duration = time.time() - start

    # Should complete in ~5 seconds (not 100 seconds!)
    assert duration < 10, f"Collection too slow: {duration}s"

# tests/unit/test_sse_event_filtering.py
@pytest.mark.asyncio
async def test_sse_filtering_by_worker_id():
    """Test that SSE events are filtered by worker_id."""
    relay = SSEEventRelay()

    # Client subscribes to worker "abc" only
    client_id, queue = await relay.register_client(
        filters={"worker_ids": ["abc"]}
    )

    # Broadcast event for worker "abc"
    await relay.broadcast_event("worker.metrics", {"worker_id": "abc"})
    event1 = await asyncio.wait_for(queue.get(), timeout=1)
    assert event1["data"]["worker_id"] == "abc"

    # Broadcast event for worker "xyz"
    await relay.broadcast_event("worker.metrics", {"worker_id": "xyz"})

    # Queue should be empty (filtered out)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.5)

# tests/unit/test_worker_metrics_service.py
@pytest.mark.asyncio
async def test_metrics_service_shared_logic():
    """Test that service logic is shared between command and job."""
    service = WorkerMetricsService(mock_aws_client)
    worker = create_mock_worker()

    # Service should update worker state
    result = await service.refresh_worker_metrics(worker)

    assert worker.state.status == CMLWorkerStatus.RUNNING
    assert worker.state.cpu_utilization is not None
    assert result.updated_fields == ["status", "cpu_utilization", ...]
```

---

## Final Verdict

**Architecture Grade**: ⚠️ **C- (Needs Significant Improvement)**

**Strengths**:

- ✅ Correct use of Neuroglia patterns (HostedService, DomainEvents)
- ✅ Recent simplification (removed per-worker jobs)
- ✅ Clean separation between API and background jobs

**Critical Issues**:

- 🔴 ~400 lines of duplicate metrics logic
- 🔴 Sequential processing (10x slower than needed)
- 🔴 N+1 database updates
- 🔴 No SSE event filtering (99% waste)
- 🔴 Global state anti-pattern
- 🔴 Over-engineered APScheduler wrapper (781 lines for 2 jobs)

**Required Actions**:

1. Extract shared logic to `WorkerMetricsService` (Priority 1)
2. Add concurrent processing with semaphore (Priority 1)
3. Implement SSE filtering (Priority 1)
4. Remove global state from scheduler (Priority 1)
5. Replace APScheduler with simple asyncio loop (Priority 2)
6. Split RefreshWorkerMetricsCommand (Priority 2)

**Expected Outcome After Refactoring**:

- 58% code reduction (2,455 → 1,020 lines)
- 10x faster background jobs
- 90% reduction in SSE bandwidth
- Clearer architecture
- Better testability
- Architecture Grade: **A-**

---

## Appendix: Code Deletion Checklist

### Files to Delete

- ✅ `application/services/logger.py` (already deleted)
- ⏳ `application/services/background_scheduler.py` (after Phase 2)

### Code Blocks to Remove

```python
# application/events/domain/cml_worker_events.py
- monitoring_scheduler parameter (lines 87, 144)
- self._monitoring_scheduler assignments
- monitoring_scheduler.stop_monitoring_worker_async() calls

# application/commands/refresh_worker_metrics_command.py
- monitoring_scheduler parameter (line 109)
- self._monitoring_scheduler = monitoring_scheduler
- Manual SSE broadcast (lines ~600)

# application/services/background_scheduler.py
- _global_service_provider (line 56)
- global _global_service_provider (line 369)
- _global_service_provider = self._service_provider (line 370)
- service_provider=_global_service_provider (lines 231, 303)
```

### Documentation to Update

- ✅ `notes/WORKER_MONITORING_ARCHITECTURE.md` (update with new simplified design)
- ✅ `README.md` (update architecture section if mentioned)
- ✅ `CHANGELOG.md` (document breaking changes)

---

**Document Version**: 1.0
**Next Review**: After Phase 1 completion
