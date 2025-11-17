# CML API Integration - System Information

## Overview

Integrated CML API `/system_information` endpoint to fetch and persist CML version, ready state, and other application-specific data during worker metrics refresh.

## Implementation Date

November 17, 2025

## Changes Made

### 1. CML API Client (`src/integration/services/cml_api_client.py`)

**Added CMLSystemInformation Dataclass:**

```python
@dataclass
class CMLSystemInformation:
    version: str            # CML version (e.g., "2.9.0")
    ready: bool             # Whether CML has compute available
    allow_ssh_pubkey_auth: bool  # SSH pubkey auth enabled
    oui: Optional[str]      # OUI prefix for MAC addresses
```

**Added get_system_information() Method:**

- Endpoint: `GET /api/v0/system_information`
- **No authentication required** (public endpoint)
- Returns CMLSystemInformation or None if unavailable
- Handles connection errors, timeouts gracefully
- Falls back if endpoint not found (older CML versions)

**Updated health_check() Method:**

- Now uses `get_system_information()` instead of `get_system_stats()`
- More reliable as it doesn't require authentication
- Faster response time

### 2. Domain Events (`src/domain/events/worker_metrics_events.py`)

**Updated CMLMetricsUpdatedDomainEvent:**

- Added `cml_version: Optional[str]` field
- Field captures CML version from system_information endpoint
- Persisted to worker state through event sourcing

### 3. Domain Model (`src/domain/entities/cml_worker.py`)

**Updated CMLMetricsUpdatedDomainEvent Handler:**

```python
@dispatch(CMLMetricsUpdatedDomainEvent)
def on(self, event: CMLMetricsUpdatedDomainEvent) -> None:
    self.cml_version = event.cml_version  # ← NEW
    self.cml_system_info = event.system_info
    self.cml_ready = event.ready
    # ... rest of fields
```

**Updated update_cml_metrics() Method:**

- Added `cml_version` parameter (first position)
- Updated docstring to document version parameter
- Passes version to CMLMetricsUpdatedDomainEvent

### 4. Refresh Worker Metrics Command (`src/application/commands/refresh_worker_metrics_command.py`)

**Enhanced CML API Integration (Lines 281-353):**

**Previous Behavior:**

- Only called `get_system_stats()` (requires auth)
- Assumed CML ready if stats returned
- No version information collected

**New Behavior:**

1. Call `get_system_information()` first (no auth needed)
   - Fetch CML version
   - Get actual ready state from CML
2. Call `get_system_stats()` for node/resource metrics (requires auth)
3. Combine data from both endpoints
4. Update worker with comprehensive CML metrics

**Code Flow:**

```python
# Step 1: Get version and ready state (public endpoint)
system_info = await cml_client.get_system_information()
cml_version = system_info.version if system_info else None
cml_ready = system_info.ready if system_info else False

# Step 2: Get resource stats (requires auth)
system_stats = await cml_client.get_system_stats()

# Step 3: Update worker with combined data
worker.update_cml_metrics(
    cml_version=cml_version,      # ← NEW
    system_info=system_stats.computes,
    ready=cml_ready,              # ← Now from system_information
    uptime_seconds=None,
    labs_count=system_stats.running_nodes,
)
```

**Enhanced Observability:**

- Added `cml.version` span attribute
- Added `cml.ready` span attribute
- Enhanced log messages with version info

**Graceful Degradation:**

- If `get_system_stats()` fails but `get_system_information()` succeeds:
  - Still persists version and ready state
  - Sets labs_count to 0
  - Logs warning about missing stats
- If both fail:
  - Marks CML as not ready
  - Sets all values to None/False/0

### 5. UI - CML Tab (`src/ui/src/scripts/ui/workers.js`)

**Already Implemented (No Changes Needed):**

- `loadCMLTab()` function correctly reads `worker.cml_version`
- Displays version in Application Info section
- Shows "Unknown" if version not available
- Escapes HTML for security

## API Endpoints Used

### `/api/v0/system_information` (NEW)

- **Method:** GET
- **Auth:** None required (public endpoint)
- **Returns:**

  ```json
  {
    "version": "2.9.0",
    "ready": true,
    "allow_ssh_pubkey_auth": false,
    "oui": "00:11:22:33:44:55"
  }
  ```

- **Purpose:** Get CML version and ready state
- **Speed:** Fast (no auth, no heavy computation)

### `/api/v0/system_stats` (Existing)

- **Method:** GET
- **Auth:** Bearer token required
- **Returns:** Compute node stats, resource usage, node counts
- **Purpose:** Get detailed resource metrics
- **Speed:** Slower (requires auth + resource calculations)

## Benefits

1. **Complete Version Tracking:**
   - CML version now visible in worker details modal
   - Useful for debugging version-specific issues
   - Helps track upgrade progress across fleet

2. **Accurate Ready State:**
   - Previously assumed ready if API responded
   - Now uses actual `ready` field from CML
   - Better reflects CML's compute availability

3. **Better Error Handling:**
   - Can get version even if stats API fails
   - Partial success scenarios handled gracefully
   - More informative error messages

4. **Improved Performance:**
   - `system_information` endpoint is faster (no auth)
   - Health checks more responsive
   - Reduces auth overhead for basic checks

5. **Enhanced Observability:**
   - Version included in OpenTelemetry spans
   - Better tracing for version-specific issues
   - More detailed logs for debugging

## Testing Checklist

- [x] CML API client methods implemented correctly
- [x] Domain event includes cml_version field
- [x] Event handler updates worker state
- [x] Refresh command fetches and persists version
- [ ] Manual test: Start worker with CML installed
- [ ] Manual test: Run refresh metrics command
- [ ] Manual test: Check worker details modal shows version
- [ ] Manual test: Verify version persists after refresh
- [ ] Manual test: Check logs show version in output
- [ ] Manual test: Verify OpenTelemetry spans include version

## Testing Instructions

1. **Start Application:**

   ```bash
   make run
   ```

2. **Ensure Worker Has CML Running:**
   - Worker status must be `RUNNING`
   - Worker must have `https_endpoint` configured
   - Worker service_status must be `AVAILABLE`

3. **Trigger Metrics Refresh:**
   - Option A: Click refresh button in worker details modal
   - Option B: Wait for automatic scheduled refresh
   - Option C: Call API: `POST /api/workers/{region}/workers/{worker_id}/metrics/refresh`

4. **Verify Version Appears:**
   - Open worker details modal
   - Click "CML" tab
   - Check "CML Version" field shows actual version (e.g., "2.9.0")
   - Verify "Ready State" badge is accurate
   - Check "Last Synced" shows recent timestamp

5. **Check Logs:**

   ```bash
   grep "CML stats" logs/app.log | tail -5
   ```

   Should show output like:

   ```
   Worker abc123 CML stats: Version=2.9.0, Ready=True, Nodes=5/10, CPUs allocated=20
   ```

6. **Verify Persistence:**
   - Close and reopen worker details modal
   - Version should still be displayed (not "Unknown")
   - Confirms data persisted to database

## Troubleshooting

**Version Shows "Unknown":**

- Worker may not be RUNNING
- HTTPS endpoint may not be configured
- CML service may not be available
- Network connectivity issues
- Check logs for IntegrationException errors

**Ready State Shows "Not Ready":**

- CML may not have compute nodes configured
- Check CML's system configuration
- Verify compute nodes are registered

**Version Not Updating:**

- Refresh command may not be running
- Check for API authentication errors
- Verify CML API is accessible
- Check worker service_status field

## Related Files

- `src/integration/services/cml_api_client.py` - CML API client
- `src/domain/events/worker_metrics_events.py` - Domain events
- `src/domain/entities/cml_worker.py` - Worker aggregate
- `src/application/commands/refresh_worker_metrics_command.py` - Refresh command
- `src/ui/src/scripts/ui/workers.js` - UI CML tab
- `notes/cml_v2.9_openapi.json` - CML API specification

## Future Enhancements

Potential improvements for CML API integration:

1. **Parse Uptime from System Info:**
   - Extract uptime from system_information or system_stats
   - Display as formatted duration in UI

2. **OUI Prefix Display:**
   - Show OUI prefix in CML tab
   - Useful for network debugging

3. **SSH Auth Status:**
   - Display allow_ssh_pubkey_auth flag
   - Help users configure console access

4. **Version Comparison:**
   - Compare worker versions across fleet
   - Highlight outdated workers
   - Track upgrade campaigns

5. **Version History:**
   - Track version changes over time
   - Display upgrade timeline
   - Useful for rollback decisions

6. **Compute Node Details:**
   - Parse and display individual compute nodes
   - Show resource allocation per node
   - Visualize cluster topology
