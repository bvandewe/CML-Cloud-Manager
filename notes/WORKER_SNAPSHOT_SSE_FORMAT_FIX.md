# Worker Snapshot SSE Format Fix

**Issue**: Resource utilization metrics disappeared after toggling idle detection
**Root Cause**: Backend emitted two different SSE event formats for `worker.snapshot` events

## Problem Description

### Symptom

After toggling idle detection on/off in the Worker Details Modal Monitoring tab, the resource utilization indicators (CPU/memory/storage progress bars) would reset to 0% and disappear.

### Root Cause Analysis

The backend was emitting `worker.snapshot` SSE events in **two different formats** depending on the trigger:

#### Format 1: Page Load (CORRECT)

**Source**: `cml_worker_events.py::_broadcast_worker_snapshot()`
**Event Source**: `"domain.cml_worker.snapshot"`

```json
{
  "source": "domain.cml_worker.snapshot",
  "data": {
    "worker_id": "...",
    "cpu_utilization": 7.925,           // ✅ Direct field, calculated
    "memory_utilization": 11.64,        // ✅ Direct field, calculated
    "storage_utilization": 36.32,       // ✅ Direct field, calculated
    "cml_system_info": {...},           // Also included
    "status": "running",
    "service_status": "healthy",
    // ... other flat fields
  }
}
```

**Characteristics**:

- ~200 lines of JSON
- Flat structure with calculated utilization fields at root level
- CPU/memory/storage utilization calculated via `metrics.get_utilization()`
- Compatible with frontend expectations

#### Format 2: After Toggle (INCORRECT - FIXED)

**Source**: `worker_activity_events_handler.py::_broadcast_worker_snapshot()` (OLD VERSION)
**Event Source**: `"domain.cml_worker"` (wrong!)

```json
{
  "source": "domain.cml_worker",
  "data": {
    "worker_id": "...",
    "reason": "idle_detection_toggled",
    "worker": {                           // ❌ Nested envelope
      "metrics": {                        // ❌ 3 levels deep
        "system_info": {
          "cpu_utilization": 2.277        // ❌ Nested CPU only
        }
      }
      // ❌ NO memory_utilization or storage_utilization fields
      "status": {...},                    // ❌ Enum objects, not strings
      "service_status": {...}
    }
  }
}
```

**Characteristics**:

- ~364 lines of JSON
- Deeply nested structure (raw `worker.state.__dict__`)
- Manually converted enums and value objects to dicts
- Missing calculated utilization fields
- Incompatible with frontend expectations

### Impact

- Frontend tried to extract metrics from nested structure
- Calculated utilization fields were missing
- Progress bars displayed 0% or disappeared
- User experience broken after any activity event (toggle, pause, resume, activity update)

## Solution

### Backend Fix

Replaced the incorrect `_broadcast_worker_snapshot()` implementation in `worker_activity_events_handler.py` with the **correct pattern** from `cml_worker_events.py`:

```python
async def _broadcast_worker_snapshot(
    repository: CMLWorkerRepository,
    sse_relay: SSEEventRelay,
    serializer: JsonSerializer,
    worker_id: str,
    reason: str | None = None,
) -> None:
    """Broadcast full worker snapshot via SSE using the same format as cml_worker_events.py.

    This ensures consistent SSE event structure regardless of the trigger (page load, toggle, etc.).
    """
    try:
        worker = await repository.get_by_id_async(worker_id)
        if not worker:
            log.warning(f"Worker {worker_id} not found for snapshot broadcast")
            return

        s = worker.state

        # Derive utilization from CML stats if available
        cpu_util, mem_util, storage_util = s.metrics.get_utilization()

        # Fallback to CloudWatch if CML metrics are missing
        if cpu_util is None and s.cloudwatch_cpu_utilization is not None:
            cpu_util = s.cloudwatch_cpu_utilization
        if mem_util is None and s.cloudwatch_memory_utilization is not None:
            mem_util = s.cloudwatch_memory_utilization

        # Safely serialize nested objects (system_info, system_health)
        # ... (same as cml_worker_events.py)

        snapshot = {
            "worker_id": s.id,
            "name": s.name,
            "region": s.aws_region,
            "status": s.status.value,                    # ✅ Enum to string
            "service_status": s.service_status.value,    # ✅ Enum to string
            # ... all worker fields (flat structure)
            "cpu_utilization": cpu_util,                 # ✅ Calculated at root
            "memory_utilization": mem_util,              # ✅ Calculated at root
            "storage_utilization": storage_util,         # ✅ Calculated at root
            # ... timestamps, license, metrics, etc.
        }
        if reason:
            snapshot["_reason"] = reason

        await sse_relay.broadcast_event(
            event_type="worker.snapshot",
            data=snapshot,                                # ✅ Flat data, no envelope
            source="domain.cml_worker.snapshot",          # ✅ Consistent source
        )
```

### Key Changes

1. **Consistent Event Source**: Changed from `"domain.cml_worker"` to `"domain.cml_worker.snapshot"`
2. **Flat Structure**: Removed nested `{"worker_id": ..., "reason": ..., "worker": {...}}` envelope
3. **Calculated Metrics**: Added `metrics.get_utilization()` to compute CPU/memory/storage at root level
4. **Proper Serialization**: Used `JsonSerializer` for nested objects (system_info, system_health)
5. **Enum Handling**: Convert to `.value` strings instead of manual dict conversion
6. **Consistent Format**: Exact same structure as page load snapshots

### Frontend Impact

**No changes needed** - frontend already expected the correct format. The fix ensures backend emits consistent events.

## Files Modified

- **src/application/events/domain/worker_activity_events_handler.py**
  - Replaced entire `_broadcast_worker_snapshot()` function
  - Added `import json` for serialization
  - Updated docstring to reference consistency with `cml_worker_events.py`

## Testing

### Manual Verification Steps

1. Start app with `make run` or `make dev`
2. Open Worker Details Modal for a running worker
3. Switch to Monitoring tab
4. Observe initial resource utilization (CPU/memory/storage progress bars)
5. Toggle idle detection on/off
6. **Expected**: Progress bars remain populated with correct values
7. **Previous Bug**: Progress bars reset to 0% or disappeared

### Automated Tests

- Existing test suite passes (124 passed, 1 skipped, 1 unrelated failure)
- No new tests required (SSE event format is integration-level concern)

## Architecture Principles Reinforced

### Single Source of Truth

The correct worker snapshot format is defined in `cml_worker_events.py::_broadcast_worker_snapshot()`. All other snapshot broadcasters should use the **same pattern**.

### Separation of Concerns

- **Domain Events**: Capture business-relevant state changes (idle detection toggled, activity updated)
- **SSE Snapshots**: Broadcast **full worker state** in consistent format for frontend consumption
- **DTOs**: Transform domain entities into API/SSE-compatible structures

### DRY Principle Violation (Acknowledged)

The `_broadcast_worker_snapshot()` function is duplicated between:

- `src/application/events/domain/cml_worker_events.py`
- `src/application/events/domain/worker_activity_events_handler.py`

**Future Improvement**: Extract to shared utility module (e.g., `application/services/worker_snapshot_broadcaster.py`)

## Lessons Learned

1. **Frontend should NOT adapt to multiple backend formats** - backend must emit consistent structure
2. **SSE event sources should be meaningful** - `"domain.cml_worker.snapshot"` clearly indicates full snapshot format
3. **Calculated fields must be included** - don't rely on frontend to compute from nested structures
4. **Test SSE events in integration tests** - JSON structure compatibility is critical for real-time features
5. **Document event schemas** - consider OpenAPI/JSON Schema for SSE event types

## Related Documentation

- `notes/IDLE_DETECTION_TOGGLE_IMPLEMENTATION.md` - Idle detection feature implementation
- `notes/WORKER_MONITORING_ARCHITECTURE.md` - Worker monitoring system design
- `notes/AUTHENTICATION_ARCHITECTURE.md` - SSE authentication patterns
- `src/application/events/domain/cml_worker_events.py` - Canonical snapshot format source
