# Worker Refresh Functionality Implementation

## Overview

Implemented a complete worker refresh functionality that allows users to:

1. Query the database for the current state of a worker
2. Refresh worker status from AWS EC2
3. Automatically start monitoring if no active session exists
4. Update the UI with the most recent worker state

## Implementation Details

### Backend Changes

#### 1. New API Endpoint

**File**: `src/api/controllers/workers_controller.py`

Added a new POST endpoint: `/region/{aws_region}/workers/{worker_id}/refresh`

**Functionality**:

- Queries the latest worker details from the database
- Updates worker status from AWS using `UpdateCMLWorkerStatusCommand`
- Ensures monitoring is active by calling `WorkerMonitoringScheduler.start_monitoring_worker_async()`
- Returns the refreshed worker details

**Access**: Requires valid authentication token (available to all authenticated users)

```python
@post("/region/{aws_region}/workers/{worker_id}/refresh")
async def refresh_worker(self, aws_region, worker_id, token):
    # 1. Query latest worker details
    # 2. Update status from AWS
    # 3. Start monitoring if needed
    # 4. Return refreshed worker data
```

### Frontend Changes

#### 1. API Client Function

**File**: `src/ui/src/scripts/api/workers.js`

Added `refreshWorker()` function to call the new backend endpoint:

```javascript
export async function refreshWorker(region, workerId) {
    const response = await apiRequest(
        `/api/workers/region/${region}/workers/${workerId}/refresh`,
        { method: 'POST' }
    );
    return await response.json();
}
```

#### 2. UI Handler Enhancement

**File**: `src/ui/src/scripts/ui/workers.js`

Enhanced `setupRefreshButton()` function with complete implementation:

**Features**:

- Disables button during refresh to prevent double-clicks
- Shows visual feedback with spinner icon
- Calls backend refresh endpoint
- Updates worker details modal with fresh data
- Provides toast notifications for success/error states
- Proper error handling and button re-enabling

```javascript
function setupRefreshButton() {
    refreshBtn.addEventListener('click', async () => {
        // 1. Disable button and show spinner
        // 2. Call refreshWorker API
        // 3. Reload worker details modal
        // 4. Show success/error notifications
        // 5. Re-enable button
    });
}
```

## User Experience

When a user clicks the "Refresh" button in the Worker Details modal:

1. **Visual Feedback**: Button shows spinner and "Refreshing..." text
2. **Backend Processing**:
   - Queries AWS for latest EC2 instance status
   - Updates database with current metrics
   - Starts monitoring job if worker is running/pending
3. **UI Update**: Modal refreshes with latest worker information
4. **Notification**: Toast message confirms success or shows error

## Benefits

- **Real-time sync**: Users can manually trigger sync with AWS state
- **Auto-recovery**: If monitoring stopped, refresh will restart it
- **User control**: No need to wait for automatic polling cycles
- **Debugging**: Helps verify current state when troubleshooting

## Known Issues

### Pickle Error with Background Tasks

**Error**: `Can't pickle local object 'JsonSerializer.configure.<locals>.<lambda>'`

**Root Cause**:

- APScheduler with Redis backend requires all job arguments to be picklable
- The `JsonSerializer.configure()` method in Neuroglia framework uses lambda functions
- When BackgroundTaskScheduler tries to enqueue tasks, APScheduler attempts to pickle the task object
- The task object has references through the service provider chain that lead to JsonSerializer with lambdas

**Impact**:

- Background monitoring jobs (WorkerMetricsCollectionJob) fail to schedule via Redis
- However, the refresh endpoint works independently and can still:
  - Query worker state from database
  - Update status from AWS
  - Return fresh data to UI

**Workaround**:

- Use in-memory jobstore instead of Redis (loses persistence across restarts)
- Or manually call refresh endpoint to keep workers updated

**Proper Fix** (Future Work):

1. Refactor BackgroundTaskScheduler to not pass full task objects to APScheduler
2. Only pass minimal serializable data (e.g., worker_id)
3. Reconstruct task in wrapper using service provider
4. OR: Configure JsonSerializer without lambda functions
5. OR: Use a different serialization approach for Redis jobstore

## Testing

### Manual Testing Steps

1. **Start the application** with monitoring enabled
2. **Navigate to Workers section** in the UI
3. **Click on a worker** to open the Worker Details modal
4. **Click the "Refresh" button** in the modal footer
5. **Verify**:
   - Button shows spinner during refresh
   - Toast notification appears
   - Modal updates with latest data
   - Monitoring starts if worker is running (check backend logs)

### Backend Testing

```bash
# Test refresh endpoint directly
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/workers/region/us-east-1/workers/WORKER_ID/refresh
```

## Files Modified

1. `/src/api/controllers/workers_controller.py` - Added refresh endpoint
2. `/src/ui/src/scripts/api/workers.js` - Added refreshWorker API function
3. `/src/ui/src/scripts/ui/workers.js` - Enhanced setupRefreshButton handler

## Future Enhancements

1. **Auto-refresh Option**: Add checkbox to enable periodic auto-refresh of modal
2. **Refresh All**: Add button to refresh all workers at once
3. **Refresh Indicator**: Show last refresh timestamp in modal
4. **Optimistic Updates**: Update UI optimistically before backend confirmation
5. **Fix Pickle Issue**: Resolve serialization issue to enable persistent background jobs
