# CML Data Sync Resilience Fix

**Date**: 2025-11-19
**Issue**: Newly imported workers not getting CML data populated despite background job running
**Status**: ✅ RESOLVED

## Problem Summary

Imported CML workers remained with `cml_ready: false` and `service_status: 'unavailable'` even though the `WorkerMetricsCollectionJob` was running successfully. This prevented labs from being synced because the job logic skips lab refresh when `cml_ready` is false.

### Symptoms

- Worker document showed:
  - `cml_ready: false`
  - `service_status: 'unavailable'`
  - `cml_version: null`
  - `cml_labs_count: 0`
  - `license_status: 'unregistered'`

- Logs showed:
  - `⏭️ Skipping labs refresh for worker [...] - not running or CML not ready`
  - `CML API auth request timed out` errors

## Root Cause Analysis

### The Logic Gap

The original `SyncWorkerCMLDataCommand` implementation had a **fail-fast approach** with a critical architectural flaw:

1. **Health check was a gatekeeper**: The command would first attempt to call `get_system_health()` (requires auth)
2. **Timeout = early exit**: If health check timed out or failed, it would:
   - Set `service_status = UNAVAILABLE`
   - Save worker and **return immediately**
3. **CML data never populated**: The subsequent code that queries `system_information` (which sets `cml_ready`) was **only executed if service status was AVAILABLE**
4. **Catch-22**: Worker stuck in unavailable state because:
   - Health check fails → mark unavailable → return early
   - Never gets to query system_information → `cml_ready` stays false
   - Labs sync skipped because `cml_ready` is false

### Code Flow (Before Fix)

```python
# Old logic in sync_worker_cml_data_command.py (lines 146-222)

# 1. Try health check first
try:
    system_health = await health_check_client.get_system_health()
    if system_health and system_health.valid:
        worker.update_service_status(CMLServiceStatus.AVAILABLE)
    else:
        worker.update_service_status(CMLServiceStatus.ERROR)
        return self.ok({...})  # ❌ EXIT HERE - never gets to system_info

except IntegrationException:
    worker.update_service_status(CMLServiceStatus.UNAVAILABLE)
    return self.ok({...})  # ❌ EXIT HERE - never gets to system_info

# 2. Only runs if service_status == AVAILABLE (line 240)
if worker.state.service_status == CMLServiceStatus.AVAILABLE:
    # This is where system_information is queried and cml_ready is set
    system_info = await cml_client.get_system_information()
    cml_ready = system_info.ready  # Never reached if health check failed!
```

### Why This Happened

The CML endpoint at `https://54.159.113.111` was timing out (confirmed with `curl` test), likely due to:

- Security group not allowing HTTPS from the application location
- Network connectivity issue
- CML service still initializing

However, even when the service became responsive later, the worker remained stuck because:

1. First sync attempt failed → marked unavailable
2. Subsequent sync attempts still used health check as gatekeeper
3. Health check requires authentication (slower, more prone to timeout)
4. `system_information` endpoint (no auth required) was never tried

## Solution: Resilient Multi-Step Approach

Refactored `SyncWorkerCMLDataCommand` to be **resilient** and **opportunistic**:

### New Strategy

1. **Try ALL APIs independently** - don't fail fast
2. **Collect partial data** - get whatever is available
3. **Prefer unauthenticated endpoints** - `system_information` is most reliable
4. **Determine status after collection** - based on what worked
5. **Always update metrics** - even with partial data

### Key Changes

```python
# New logic (lines 146-327)

# 1. Create client once
cml_client = CMLApiClient(...)

# Track what succeeded
api_accessible = False
system_info = None
system_health = None
system_stats = None
license_info_dict = None

# 2. Try system_information (no auth - most reliable)
try:
    system_info = await cml_client.get_system_information()
    if system_info:
        api_accessible = True
        cml_ready = system_info.ready  # ✅ Set this EARLY
except IntegrationException:
    log.warning(...)  # Continue, don't fail

# 3. Try system_health (requires auth)
try:
    system_health = await cml_client.get_system_health()
    if system_health:
        api_accessible = True
except IntegrationException:
    log.warning(...)  # Continue, don't fail

# 4. Try system_stats (requires auth)
try:
    system_stats = await cml_client.get_system_stats()
    if system_stats:
        api_accessible = True
except IntegrationException:
    log.warning(...)  # Continue, don't fail

# 5. Try licensing (requires auth)
try:
    license_info = await cml_client.get_licensing()
    if license_info:
        license_info_dict = license_info.raw_data
except Exception:
    log.warning(...)  # Continue, don't fail

# 6. Determine service status based on results
if not api_accessible:
    worker.update_service_status(CMLServiceStatus.UNAVAILABLE)
    return self.ok({...})  # Only exit if NOTHING worked
elif system_health and system_health.valid:
    worker.update_service_status(CMLServiceStatus.AVAILABLE)
elif system_info:
    # System info worked but health didn't - still mark AVAILABLE
    worker.update_service_status(CMLServiceStatus.AVAILABLE)
else:
    worker.update_service_status(CMLServiceStatus.ERROR)

# 7. Always update metrics with whatever we have
worker.update_cml_metrics(
    cml_version=system_info.version if system_info else None,
    ready=system_info.ready if system_info else False,  # ✅ Updated!
    labs_count=system_stats.running_nodes if system_stats else 0,
    system_info=system_stats.computes if system_stats else {},
    system_health=system_health_dict,
    license_info=license_info_dict,
    ...
)
```

### Benefits

1. **No single point of failure**: Each API is tried independently
2. **Graceful degradation**: Partial data is better than no data
3. **Better for slow networks**: Timeouts on one API don't block others
4. **Earlier readiness detection**: `system_information` (no auth) tried first
5. **More informative logging**: Each API attempt logged separately

## Verification

### Before Fix

```javascript
// MongoDB document state
{
    cml_ready: false,
    service_status: 'unavailable',
    cml_version: null,
    cml_labs_count: 0,
    license_status: 'unregistered'
}
```

Log output:

```
⏭️ Skipping labs refresh for worker [...] - not running or CML not ready
❌ CML service not accessible for worker [...]: CML API auth request timed out
```

### After Fix

```javascript
// MongoDB document state (after first successful sync)
{
    cml_ready: true,
    service_status: 'available',
    cml_version: '2.9.0+build.3',
    cml_labs_count: 9,
    license_status: 'registered'
}
```

Log output:

```
✅ Retrieved system info for worker [...]: version=2.9.0+build.3, ready=True
✅ Retrieved system health for worker [...]: valid=True, licensed=True
✅ Retrieved system stats for worker [...]: running_nodes=9
✅ CML licensing info collected for worker [...]: CML_Enterprise (COMPLETED)
✅ CML service healthy for worker [...] - marked as AVAILABLE
✅ CML data synced for worker [...]: version=2.9.0+build.3, ready=True, service=available
```

And labs sync now proceeds:

```
Refreshing labs for worker [...]
```

## Alignment with Framework

### Neuroglia Framework Compliance

✅ **CommandHandler helper methods**: Used `self.ok()` and `self.bad_request()` consistently
✅ **No OperationResult construction**: Only used helper methods, never imported OperationResult
✅ **Proper mediator usage**: Called with single argument only
✅ **Tracing integration**: Used OpenTelemetry span attributes
✅ **Repository patterns**: Proper async usage with cancellation_token
✅ **Logging conventions**: Consistent emoji prefixes (✅, ⚠️, ❌)

### Architecture Principles

✅ **Observable**: Enhanced tracing with per-API error attributes
✅ **Resilient**: Graceful degradation with partial data collection
✅ **Actionable**: Clear logging for debugging
✅ **Maintainable**: Self-documenting code with inline comments

## Files Modified

- `src/application/commands/sync_worker_cml_data_command.py`
  - Refactored lines 146-327
  - Removed fail-fast health check gatekeeper
  - Added independent API call attempts
  - Added resilient status determination logic
  - Fixed type error (system_info parameter)

## Testing

1. **Manual verification**: Curl test confirmed endpoint timeout
2. **Log inspection**: Confirmed new resilient behavior
3. **Database check**: Verified CML data populated after fix
4. **Integration test**: Labs sync now proceeds for worker

## Lessons Learned

1. **Don't use authenticated APIs as health checks**: Unauthenticated endpoints are more reliable
2. **Fail-fast is not always best**: Resilient collection of partial data is better
3. **Consider network conditions**: Timeouts happen, design for them
4. **Test edge cases**: Newly imported workers are a critical edge case
5. **Order matters**: Try most reliable APIs first (system_information before system_health)

## Related Documentation

- `notes/WORKER_MONITORING_ARCHITECTURE.md` - Overall monitoring system
- `notes/CML_API_INTEGRATION.md` - CML API client patterns
- `notes/IMPORT_EXISTING_INSTANCES_FEATURE.md` - Worker import flow
- Architecture decision: Prefer resilience over strict validation

## Future Improvements

Consider:

1. **Circuit breaker pattern**: Skip failing APIs temporarily after repeated failures
2. **Exponential backoff**: Retry with increasing delays for transient failures
3. **Parallel API calls**: Use `asyncio.gather` for independent queries (with timeouts)
4. **Health check endpoint**: Add dedicated lightweight health endpoint to CML API
5. **Caching**: Cache system_information responses briefly to reduce API calls
