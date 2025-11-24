# Proper DTO Architecture Implementation

**Date**: 2025-11-24
**Status**: IMPLEMENTED - Reverted worker snapshot broadcasting, introduced proper DTO layer

## Problem Statement

The application was manually crafting worker data structures in multiple places with inconsistent formats:

1. `get_cml_worker_by_id_query.py` - Manual dict crafting in query handler
2. `cml_worker_events.py::_broadcast_worker_snapshot()` - Manual dict crafting for SSE
3. `worker_activity_events_handler.py` - Attempted to duplicate snapshot broadcasting (now removed)

This violated DRY principles and caused SSE format inconsistencies.

## Solution: Proper DTO Architecture

### 1. Introduced CMLWorkerDto

**File**: `src/application/dtos/cml_worker_dto.py`

Created a proper `@dataclass` DTO with all worker fields:

- Identity fields (id, name, region, instance_id, etc.)
- Status fields (status, service_status)
- Network & AMI information
- License data
- CML metrics (version, labs_count, system_info, system_health)
- EC2 & CloudWatch metrics
- Calculated utilization fields (cpu, memory, storage)
- Activity tracking & idle detection fields
- Pause/resume tracking

### 2. Centralized Mapping Logic

**File**: `src/application/mappers/cml_worker_mapper.py`

Created mapping functions:

```python
def map_worker_to_dto(worker: CMLWorker) -> CMLWorkerDto:
    """Map CMLWorker aggregate to CMLWorkerDto."""
    # Single source of truth for worker → DTO mapping
    # Handles:
    # - Calculated utilization from metrics.get_utilization()
    # - CloudWatch fallback for CPU/memory
    # - Value clamping to [0, 100]
    # - Datetime → ISO string conversion
    # - Enum → string conversion
    # - Nested object serialization (system_info, system_health)

def worker_dto_to_dict(dto: CMLWorkerDto) -> dict:
    """Convert DTO to dict for JSON serialization."""
    return asdict(dto)
```

### 3. Removed Duplicate Worker Snapshot Broadcasting

**File**: `src/application/events/domain/worker_activity_events_handler.py`

**Reverted changes**:

- ❌ Removed `_broadcast_worker_snapshot()` function
- ❌ Removed worker snapshot broadcasts from all activity event handlers:
  - `IdleDetectionToggledDomainEventHandler`
  - `WorkerActivityUpdatedDomainEventHandler`
  - `WorkerPausedDomainEventHandler`
  - `WorkerResumedDomainEventHandler`

**Why**: Activity events should send **minimal event data only**. Full worker snapshots are the responsibility of the metrics collection job.

## Architecture Principles

### Single Responsibility Principle

**Activity Event Handlers** (`worker_activity_events_handler.py`):

- Purpose: Broadcast **lightweight** domain event notifications
- Data: Event-specific fields only (worker_id, is_enabled, toggled_at, etc.)
- Format: Minimal JSON payloads
- Source: `"domain.worker_activity"`

**Worker Snapshot Broadcasting** (`cml_worker_events.py`):

- Purpose: Broadcast **full worker state** snapshots
- Data: Complete worker DTO with all fields
- Format: Consistent CMLWorkerDto → dict → JSON
- Source: `"domain.cml_worker.snapshot"`
- Trigger: Scheduled metrics collection job (every N seconds)

### Data Flow

```
┌─────────────────────────┐
│ Domain Event Occurs     │
│ (Idle Detection Toggle) │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────┐
│ IdleDetectionToggled            │
│ DomainEventHandler              │
│                                 │
│ Broadcasts MINIMAL event:       │
│ {                               │
│   worker_id,                    │
│   is_enabled,                   │
│   toggled_by,                   │
│   toggled_at                    │
│ }                               │
└─────────────────────────────────┘
            │
            ▼
     [Frontend receives
      toggle confirmation]
            │
            ▼
┌─────────────────────────────────┐
│ WorkerMetricsCollectionJob      │
│ (next scheduled run)            │
│                                 │
│ 1. Fetches worker aggregate     │
│ 2. Maps to CMLWorkerDto         │
│ 3. Converts to dict             │
│ 4. Broadcasts snapshot via SSE  │
└─────────────────────────────────┘
            │
            ▼
     [Frontend receives
      full worker state
      with updated field]
```

### Benefits

1. **Consistency**: All worker data uses same DTO structure
2. **DRY**: Single mapping function, not duplicated across files
3. **Type Safety**: Dataclass provides field validation
4. **Maintainability**: Changes to worker structure require updates in one place
5. **Testability**: DTO mapping can be unit tested independently
6. **Separation of Concerns**: Event handlers don't need repository/serializer access

## Migration Path

### Query Handlers (Future Work)

The `get_cml_worker_by_id_query.py` handler still uses manual dict crafting.

**Recommendation**: Refactor to use the DTO:

```python
# Before (current)
result = {
    "id": worker.state.id,
    "name": worker.state.name,
    # ... 100+ lines of manual mapping
}
return self.ok(result)

# After (recommended)
from application.mappers import map_worker_to_dto, worker_dto_to_dict

dto = map_worker_to_dto(worker)
return self.ok(worker_dto_to_dict(dto))
```

### SSE Snapshot Broadcasting (Future Work)

The `cml_worker_events.py::_broadcast_worker_snapshot()` function should also use the DTO:

```python
# Before (current)
snapshot = {
    "worker_id": s.id,
    "name": s.name,
    # ... 70+ lines of manual mapping
}
await relay.broadcast_event(
    event_type="worker.snapshot",
    data=snapshot,
    source="domain.cml_worker.snapshot",
)

# After (recommended)
from application.mappers import map_worker_to_dto, worker_dto_to_dict

dto = map_worker_to_dto(worker)
snapshot = worker_dto_to_dict(dto)

await relay.broadcast_event(
    event_type="worker.snapshot",
    data=snapshot,
    source="domain.cml_worker.snapshot",
)
```

## Files Created

- `src/application/dtos/__init__.py` - DTOs package init
- `src/application/dtos/cml_worker_dto.py` - CMLWorkerDto dataclass
- `src/application/mappers/__init__.py` - Mappers package init
- `src/application/mappers/cml_worker_mapper.py` - Mapping functions

## Files Modified

- `src/application/events/domain/worker_activity_events_handler.py`
  - Removed `_broadcast_worker_snapshot()` function
  - Removed repository/serializer dependencies from all handlers
  - Updated docstrings to clarify minimal event broadcasting

## Testing

### Verification Steps

1. **Idle detection toggle should work**:
   - Toggle sends `worker.idle_detection.toggled` event only
   - No worker.snapshot immediately after toggle
   - Next metrics poll (5 minutes) sends full snapshot with updated `is_idle_detection_enabled` field

2. **Frontend should display toggle state**:
   - Toggle switch reflects backend state
   - Utilization charts remain visible (not reset to 0%)
   - Charts update on next metrics poll

3. **All activity events follow same pattern**:
   - Pause/resume/activity events send minimal data
   - No redundant snapshot broadcasting
   - Frontend receives state updates via scheduled polls

### Expected Behavior

**Before**: Toggle → immediate worker.snapshot with inconsistent format → metrics disappear
**After**: Toggle → minimal event confirmation → wait for next poll → full snapshot with consistent format → metrics persist

## Lessons Learned

1. **Don't duplicate snapshot broadcasting**: One job, one responsibility
2. **Use DTOs consistently**: Manual dict crafting leads to inconsistencies
3. **Separate concerns**: Event notifications ≠ state synchronization
4. **Trust the scheduler**: Let background jobs handle periodic state broadcasting
5. **Type safety matters**: Dataclasses catch errors at development time

## Related Documentation

- `notes/IDLE_DETECTION_TOGGLE_IMPLEMENTATION.md` - Original feature implementation
- `notes/WORKER_MONITORING_ARCHITECTURE.md` - Background job scheduling
- `notes/WORKER_SNAPSHOT_SSE_FORMAT_FIX.md` - Previous (incorrect) fix attempt
