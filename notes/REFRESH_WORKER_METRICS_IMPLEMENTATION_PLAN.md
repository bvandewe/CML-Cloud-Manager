# Refresh Worker Metrics Implementation Plan

## Current State Analysis

### Critical Architecture Violations

1. **❌ Controller bypasses CQRS** - `/refresh` endpoint directly instantiates `WorkerMetricsCollectionJob` instead of dispatching a command
2. **❌ Missing CML API Client** - No integration with CML REST API running on worker instances
3. **❌ Background job has too many responsibilities** - Job queries AWS, updates aggregates, publishes events, manages observers
4. **❌ OTEL metrics disconnected** - Metrics collection doesn't update OpenTelemetry gauges/counters

### What Exists vs What's Missing

**✅ Exists:**

- AWS EC2 client for instance metadata
- AWS CloudWatch client for CPU/memory metrics
- CMLWorker aggregate with basic status fields
- Domain events for state changes
- Background job infrastructure (APScheduler)

**❌ Missing:**

- CML API client for application-level metadata
- RefreshWorkerMetricsCommand + handler
- CML system information in worker aggregate
- OTEL metrics updates in collection flow
- Proper command-driven refresh workflow

## Implementation Plan

### Phase 1: Proper Command Pattern (IMMEDIATE)

**Goal**: Fix architecture by using CQRS properly for refresh operations.

**Steps:**

1. Create `RefreshWorkerMetricsCommand` + `RefreshWorkerMetricsCommandHandler`
2. Command orchestrates:
   - Query AWS EC2 for instance state
   - Query AWS CloudWatch for metrics
   - Update worker aggregate (triggers domain events)
   - Update OTEL gauges/counters
   - Schedule/ensure background monitoring active
3. Controller invokes command via mediator (not job directly)
4. Background job delegates to command (thin wrapper)

**Files to Create:**

```
src/application/commands/refresh_worker_metrics_command.py
```

**Files to Modify:**

```
src/api/controllers/workers_controller.py - Use command via mediator
src/application/services/worker_metrics_collection_job.py - Delegate to command
src/application/commands/__init__.py - Export new command
```

**Command Handler Responsibilities:**

- ✅ Query AWS EC2 for current instance status
- ✅ Query AWS CloudWatch for CPU/memory metrics (last 5 minutes)
- ✅ Load worker aggregate from repository
- ✅ Update worker aggregate state (status, IPs, metrics, etc.)
- ✅ Persist worker aggregate (triggers domain event publishing)
- ✅ Update OTEL metrics gauges
- ⚠️ Skip CML API call if worker not RUNNING or no https_endpoint
- ⚠️ Schedule background monitoring if worker RUNNING (use WorkerMonitoringScheduler)

### Phase 2: CML API Client Integration (NEXT)

**Goal**: Collect application-level metadata from CML instances.

**Steps:**

1. Create `CMLApiClient` for REST API integration
2. Implement core endpoints:
   - `GET /api/v0/system_information` - CML version, uptime, system details
   - `GET /api/v0/labs` - Active labs (count, names, states)
   - `GET /api/v0/licensing` - License status, expiration
3. Extend `CMLWorkerState` with CML metadata fields
4. Create domain event `CMLSystemInfoUpdatedDomainEvent`
5. Update command handler to call CML API when worker RUNNING
6. Handle CML API errors gracefully (worker may be booting, network issues)

**Files to Create:**

```
src/integration/services/cml_api_client.py
src/integration/models/cml_system_info_dto.py
src/integration/models/cml_lab_dto.py
src/integration/models/cml_license_info_dto.py
src/domain/events/cml_worker.py - Add CMLSystemInfoUpdatedDomainEvent
```

**Files to Modify:**

```
src/domain/entities/cml_worker.py - Add CML metadata fields to state
src/application/commands/refresh_worker_metrics_command.py - Call CML API
src/integration/services/__init__.py - Export CMLApiClient
```

**CML Metadata to Store:**

```python
class CMLWorkerState(AggregateState[str]):
    # ... existing fields ...

    # CML-specific metadata from API
    cml_system_info: dict | None          # Raw system info JSON
    cml_ready: bool                        # CML service ready flag
    cml_uptime_seconds: int | None        # System uptime
    labs_count: int                        # Active labs count (from API)
    last_cml_api_sync_at: datetime | None # Last successful CML API call
    last_cml_api_error: str | None        # Last API error message
```

### Phase 3: OTEL Metrics Integration

**Goal**: Expose worker metrics via OpenTelemetry.

**Steps:**

1. Define OTEL gauges in observability module:
   - `cml.worker.status` (gauge with status as attribute)
   - `cml.worker.cpu_utilization` (gauge, percentage)
   - `cml.worker.memory_utilization` (gauge, percentage)
   - `cml.worker.labs_count` (gauge)
   - `cml.worker.uptime_seconds` (gauge)
2. Update gauges in command handler after worker update
3. Add worker_id and region as metric attributes

**Files to Create/Modify:**

```
src/observability/metrics/worker_metrics.py - Define OTEL instruments
src/application/commands/refresh_worker_metrics_command.py - Update metrics
```

### Phase 4: Background Monitoring Refactoring (LATER)

**Goal**: Simplify background job to be thin wrapper around command.

**Current State:**

- `WorkerMetricsCollectionJob` duplicates logic (AWS queries, aggregate updates)
- Job has direct dependencies on AWS clients, repositories
- Difficult to test job vs command independently

**Target State:**

- Job is thin wrapper that invokes `RefreshWorkerMetricsCommand`
- All business logic in command handler (single source of truth)
- Job only responsible for scheduling and error handling

**Implementation:**

```python
class WorkerMetricsCollectionJob(RecurrentBackgroundJob):
    async def run_every(self, *args, **kwargs) -> None:
        # Get mediator from service provider
        mediator = self._service_provider.get_required_service(Mediator)

        # Dispatch command (all logic lives here)
        command = RefreshWorkerMetricsCommand(worker_id=self.worker_id)
        result = await mediator.execute_async(command)

        if not result.is_success:
            logger.error(f"Metrics collection failed: {result.errors}")
            # Notify observers of failure
        else:
            # Notify observers of success (metrics data in result)
```

## Implementation Order

### ✅ Step 1: Create RefreshWorkerMetricsCommand (NOW)

- Command + handler skeleton
- AWS EC2/CloudWatch queries
- Worker aggregate update
- Basic OTEL metrics (if instrumentation exists)

### 🔨 Step 2: Integrate in Controller (NOW)

- Remove direct job instantiation
- Dispatch command via mediator
- Use WorkerMonitoringScheduler for background scheduling

### 📝 Step 3: Build CML API Client (NEXT SESSION)

- CMLApiClient with system_information endpoint
- Extend worker state with CML metadata
- Add CML API call to command handler

### 🔄 Step 4: Refactor Background Job (AFTER CML API)

- Job delegates to command
- Remove duplicate logic
- Simplify configuration

## Success Criteria

### Phase 1 Complete When

- [ ] `RefreshWorkerMetricsCommand` exists and handles AWS queries
- [ ] Controller uses command via mediator (not direct job)
- [ ] Worker aggregate updated with latest AWS state
- [ ] Domain events published on state changes
- [ ] Background monitoring scheduled via WorkerMonitoringScheduler
- [ ] OTEL metrics updated (if instrumentation exists)

### Phase 2 Complete When

- [ ] `CMLApiClient` can call CML REST API endpoints
- [ ] Worker aggregate stores CML metadata (version, labs, uptime)
- [ ] Command handler calls CML API when worker RUNNING
- [ ] Errors handled gracefully (worker booting, network issues)
- [ ] UI displays CML metadata in worker details modal

### Phase 3 Complete When

- [ ] OTEL gauges defined for worker metrics
- [ ] Metrics updated after each refresh
- [ ] Prometheus/Grafana can scrape worker metrics
- [ ] Metrics include proper labels (worker_id, region)

## Architecture Principles

### ✅ Do This

- **Commands for write operations** - RefreshWorkerMetricsCommand is a write operation
- **Queries for read operations** - GetCMLWorkerByIdQuery already exists
- **Aggregate as single source of truth** - All state in CMLWorkerState
- **Domain events for side effects** - Events trigger notifications, monitoring
- **Thin background jobs** - Jobs delegate to commands/queries

### ❌ Don't Do This

- **Controllers calling jobs directly** - Bypass mediator pattern
- **Jobs with business logic** - Logic belongs in command handlers
- **Multiple sources of truth** - Don't duplicate state across models
- **Silent failures** - Always handle errors and log clearly
- **Tight coupling** - Use dependency injection, not direct imports

## Testing Strategy

### Unit Tests

- Command handler logic (AWS queries, aggregate updates)
- CML API client (mock HTTP responses)
- Worker aggregate methods (state transitions)

### Integration Tests

- End-to-end refresh flow (controller → command → repository)
- Background job scheduling (APScheduler integration)
- Domain event publishing (mediator pipeline)

### Manual Tests

- UI refresh button triggers metrics collection
- Worker details modal shows updated data
- Background monitoring continues after manual refresh
- CML API errors don't crash application

## Notes

- CML API documentation: https://developer.cisco.com/docs/modeling-labs/
- CML API authentication: Basic auth or API token (check settings)
- OTEL metrics export: Configured via `src/observability/` module
- APScheduler persistence: Redis job store for distributed execution
