# Idle Detection Toggle UI Implementation

**Date**: November 24, 2025
**Status**: Complete ✅
**Feature**: Admin-only toggle control for worker idle detection with real-time SSE updates

## Overview

Implemented idle detection toggle control in the Worker Details Modal's Monitoring tab, allowing admins to enable/disable automatic idle detection and auto-pause functionality for CML workers.

## Implementation Details

### Backend (Pre-existing)

Commands and handlers already existed:

- `EnableIdleDetectionCommand` / `EnableIdleDetectionCommandHandler`
- `DisableIdleDetectionCommand` / `DisableIdleDetectionCommandHandler`
- API endpoints at `/workers/region/{aws_region}/workers/{worker_id}/idle-detection/enable|disable`

### Frontend Components

#### 1. API Client (`src/ui/src/scripts/api/workers.js`)

Added two methods:

```javascript
export async function enableIdleDetection(region, workerId)
export async function disableIdleDetection(region, workerId)
```

#### 2. Monitoring Tab Renderer (`src/ui/src/scripts/ui/worker-monitoring.js`)

Added toggle control in Idle Detection card:

- Bootstrap toggle switch (`form-check-input` with `role="switch"`)
- Admin-only visibility via `isAdmin()` check
- Data attributes: `data-worker-id` and `data-region` for event handlers
- Displays current idle detection state with badge

#### 3. Event Handlers

Toggle handler attached via `attachIdleDetectionToggleHandler()`:

```javascript
toggleSwitch.addEventListener('change', async (e) => {
    const isEnabled = e.target.checked;
    const workerId = e.target.dataset.workerId;
    const region = e.target.dataset.region;

    if (isEnabled) {
        await enableIdleDetection(region, workerId);
    } else {
        await disableIdleDetection(region, workerId);
    }
});
```

#### 4. SSE Real-time Updates

Domain event handlers broadcast updates via SSE:

- `IdleDetectionToggledDomainEventHandler` - emits `worker.idle_detection.toggled`
- `WorkerActivityUpdatedDomainEventHandler` - emits `worker.activity.updated`
- `WorkerPausedDomainEventHandler` - emits `worker.paused`
- `WorkerResumedDomainEventHandler` - emits `worker.resumed`

After each toggle event, a `worker.snapshot` event is emitted with full worker state.

### Resource Utilization Display

Added CloudWatch and CML metrics visualization:

- CPU utilization (CloudWatch + CML native)
- Memory utilization (CloudWatch)
- CloudWatch polling interval and last collection timestamp

Color-coded progress bars:

- Green: < 70%
- Yellow: 70-85%
- Red: > 85%

## Issues Encountered & Resolutions

### Issue 1: URL Path Inconsistency

**Problem**: Initial implementation used `/api/workers/{region}/{workerId}/...` but backend expected `/api/workers/region/{region}/workers/{workerId}/...`

**Solution**: Updated frontend URLs to match established pattern used by other endpoints.

### Issue 2: Worker Snapshot Event Structure Mismatch

**Problem**: Backend sent `{worker_id, reason, worker: {...}}` but frontend expected worker fields at root level.

**Solution**:

1. Updated `worker-sse.js` to extract from `envelope.worker`
2. Updated `SSEService.js` to unwrap envelope before emitting to EventBus:

```javascript
const workerData = data.data?.worker || data.data;
if (workerData && !workerData.id && data.data?.worker_id) {
    workerData.id = data.data.worker_id;
}
eventBus.emit(EventTypes.WORKER_SNAPSHOT, workerData);
```

### Issue 3: Duplicate Rendering with "Worker data not available"

**Problem**: After toggle, monitoring tab briefly showed "Worker data not available" then recovered after refresh.

**Root Cause**: Two rendering paths were active:

1. WorkerDetailsModal correctly handling `worker.snapshot` event
2. Legacy SSE handlers calling `loadMonitoringTab()` with empty/stale worker from store

**Solution**: Removed legacy SSE handlers from `worker-monitoring.js`:

- Deleted `initializeMonitoringSSE()` implementation (kept stub for backward compatibility)
- Removed `loadMonitoringTab()` implementation (kept stub)
- Removed unused imports (`getActiveWorker`, `sseClient`)

WorkerDetailsModal now exclusively handles updates via EventBus `WORKER_SNAPSHOT` event.

## Architecture Notes

### Dual Implementation Paths

The codebase has two implementations:

1. **New (Web Components)**: `WorkersApp` + `WorkerDetailsModal` - **Active by default**
2. **Legacy**: `workers.js` + `worker-init.js` - Accessible via feature flag

Feature flag: `localStorage.getItem('use-web-components') !== 'false'` (default: enabled)

### Monitoring Tab Usage

The monitoring tab (`worker-monitoring.js`) is ONLY used by `WorkerDetailsModal`. There is no standalone monitoring view. Legacy SSE handlers were removed to prevent conflicts.

## Testing Checklist

- [x] Toggle switch visible only to admins
- [x] Toggle state reflects `is_idle_detection_enabled` field
- [x] Enable/disable API calls succeed (200 OK)
- [x] SSE events received (`worker.idle_detection.toggled`, `worker.snapshot`)
- [x] UI updates in real-time without full page refresh
- [x] Worker remains visible in table during toggle
- [x] Monitoring tab stays populated (no "Worker data not available")
- [x] Other tabs (Overview, License, Labs) unaffected
- [x] Resource utilization charts display correctly

## API Endpoints

### Enable Idle Detection

```
POST /api/workers/region/{aws_region}/workers/{worker_id}/idle-detection/enable
Authorization: Admin role required
Response: {worker_id, idle_detection_enabled: true, message}
```

### Disable Idle Detection

```
POST /api/workers/region/{aws_region}/workers/{worker_id}/idle-detection/disable
Authorization: Admin role required
Response: {worker_id, idle_detection_enabled: false, message}
```

## SSE Events

### worker.idle_detection.toggled

```json
{
  "type": "worker.idle_detection.toggled",
  "source": "domain.worker_activity",
  "time": "2025-11-24T00:29:09.089701+00:00Z",
  "data": {
    "worker_id": "uuid",
    "is_enabled": true,
    "toggled_by": "user-uuid",
    "toggled_at": "2025-11-24T00:29:09.036000Z"
  }
}
```

### worker.snapshot (follows toggle event)

```json
{
  "type": "worker.snapshot",
  "source": "domain.cml_worker",
  "time": "2025-11-24T00:29:09.089701+00:00Z",
  "data": {
    "worker_id": "uuid",
    "reason": "idle_detection_toggled",
    "worker": {
      "id": "uuid",
      "name": "Worker Name",
      "is_idle_detection_enabled": true,
      // ... full worker state (56 fields)
    }
  }
}
```

## Files Modified

### Backend

- `src/api/controllers/workers_controller.py` - Updated endpoint paths for consistency

### Frontend

- `src/ui/src/scripts/api/workers.js` - Added enable/disable methods
- `src/ui/src/scripts/ui/worker-monitoring.js` - Toggle UI, event handlers, cleanup
- `src/ui/src/scripts/services/SSEService.js` - Fixed envelope unwrapping
- `src/ui/src/scripts/ui/worker-sse.js` - Fixed snapshot parsing
- `src/ui/src/scripts/components-v2/WorkerDetailsModal.js` - Debug logging

### New Files

- `src/application/events/domain/worker_activity_events_handler.py` - SSE event publishers
- `src/application/events/domain/__init__.py` - Registered new handlers

## Future Enhancements

1. **Historical Metrics Chart**: Requires time-series storage (MongoDB time-series collection or separate TSDB)
2. **Idle Detection Configuration**: UI to configure idle timeout threshold (currently backend-only setting)
3. **Activity Threshold Tuning**: Expose idle detection sensitivity settings to admins
4. **Legacy Code Removal**: After sufficient production validation, remove `workers.js`/`worker-init.js` and feature flag

## Related Documentation

- Architecture: `notes/WORKER_MONITORING_ARCHITECTURE.md`
- Web Components Migration: `notes/FRONTEND_WEB_COMPONENTS_MIGRATION_COMPLETE.md`
- Authentication: `notes/AUTHENTICATION_ARCHITECTURE.md`
