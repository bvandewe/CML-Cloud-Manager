# Lab Delete - Two-Phase Implementation

## Overview

Implemented a robust two-phase approach for lab deletion that ensures immediate UI consistency while maintaining eventual data integrity through background reconciliation.

## Problem Statement

When a lab is deleted via the CML API, the local `LabRecord` in MongoDB was persisting because:

- The `DeleteLabCommand` only deleted from CML API, not local database
- The background `LabsRefreshJob` only created/updated records, never detected deletions
- The `RefreshWorkerLabsCommand` had the same limitation
- Users saw stale data in the UI after successful deletion

## Solution: Two-Phase Delete Architecture

### Phase 1: Immediate Local Cleanup (Best UX)

**Location**: `DeleteLabCommand` handler

**Flow**:

1. Validate worker exists and has HTTPS endpoint
2. Delete lab from CML API via `cml_client.delete_lab()`
3. **Immediately delete local `LabRecord` from MongoDB**
4. Return success response

**Benefits**:

- ✅ Instant UI update - lab disappears immediately
- ✅ No stale data shown to user
- ✅ No extra API calls (single delete operation)
- ✅ Follows single responsibility - command handles immediate action

**Code Changes** (`src/application/commands/delete_lab_command.py`):

```python
# Added LabRecordRepository import
from domain.repositories.lab_record_repository import LabRecordRepository

class DeleteLabCommandHandler:
    def __init__(
        self,
        worker_repository: CMLWorkerRepository,
        lab_record_repository: LabRecordRepository,  # NEW
        cml_api_client_factory: CMLApiClientFactory,
    ):
        self._lab_record_repository = lab_record_repository  # NEW

    async def handle_async(self, request, cancellation_token=None):
        # ... validate worker ...

        # Delete from CML API
        await cml_client.delete_lab(request.lab_id)

        # NEW: Delete local LabRecord from database
        lab_record = await self._lab_record_repository.get_by_lab_id_async(
            request.worker_id, request.lab_id
        )
        if lab_record:
            await self._lab_record_repository.remove_async(lab_record)
            log.info(f"Lab record {request.lab_id} removed from database")
        else:
            log.warning(f"Lab record {request.lab_id} not found in database")

        return self.ok({"lab_id": request.lab_id, "message": "Lab deleted successfully"})
```

### Phase 2: Background Reconciliation (Data Integrity)

**Location**: `LabsRefreshJob` and `RefreshWorkerLabsCommand`

**Flow**:

1. Fetch current lab IDs from CML API
2. Fetch existing `LabRecord` IDs from database for this worker
3. **Identify orphaned records** (in DB but not in CML)
4. Delete orphaned records
5. Continue with existing create/update logic

**Benefits**:

- ✅ Eventually consistent - catches any missed deletions
- ✅ Handles deletions made outside our system (direct CML access)
- ✅ Resilient - if Phase 1 fails to clean DB, Phase 2 catches it
- ✅ Self-healing - runs every 30 minutes (configurable)
- ✅ Separation of concerns - background job handles reconciliation

**Code Changes** (`src/application/jobs/labs_refresh_job.py` and `src/application/commands/refresh_worker_labs_command.py`):

```python
async def _refresh_worker_labs(self, worker, lab_record_repository):
    # Fetch lab IDs from CML
    lab_ids = await cml_client.get_labs()

    # NEW: Detect and remove orphaned lab records
    existing_records = await lab_record_repository.get_all_by_worker_async(worker_id)
    existing_lab_ids = {record.state.lab_id for record in existing_records}
    current_lab_ids = set(lab_ids) if lab_ids else set()
    orphaned_lab_ids = existing_lab_ids - current_lab_ids

    if orphaned_lab_ids:
        log.info(
            f"Found {len(orphaned_lab_ids)} orphaned lab records for worker {worker_id}: "
            f"{list(orphaned_lab_ids)}"
        )
        for orphaned_lab_id in orphaned_lab_ids:
            try:
                orphaned_record = next(
                    (r for r in existing_records if r.state.lab_id == orphaned_lab_id),
                    None
                )
                if orphaned_record:
                    await lab_record_repository.remove_async(orphaned_record)
                    log.info(f"Removed orphaned lab record: {orphaned_lab_id}")
            except Exception as e:
                log.error(f"Failed to remove orphaned lab record {orphaned_lab_id}: {e}")

    # Continue with existing create/update logic...
```

## Architecture Decisions

### Why Two Phases Instead of Just Refresh?

**❌ Alternative: Call refresh after every delete**

- Extra API overhead on every delete
- Refreshes ALL labs when only one changed
- Delays UI update by several seconds
- Doesn't handle deletions outside our system
- Tight coupling between delete and refresh

**✅ Our Approach: Two-Phase Delete**

- Immediate local cleanup (Phase 1)
- Background reconciliation (Phase 2)
- Decoupled concerns
- Resilient to failures
- Handles external deletions

### Why Not Just Delete Locally?

**❌ Just local delete without background sync**

- No safety net if delete command fails
- Can't detect deletions made outside our system
- Database can drift from CML state over time
- Requires perfect execution every time

**✅ Two-Phase with background reconciliation**

- Self-healing architecture
- Eventually consistent
- Handles edge cases (direct CML access, API failures, etc.)
- Follows DDD principles (local aggregate deletion matches source of truth)

## Files Modified

### Command Layer

1. **`src/application/commands/delete_lab_command.py`**
   - Added `LabRecordRepository` dependency
   - Added immediate local database cleanup after CML deletion
   - Enhanced logging to track both CML and DB operations

### Command Layer (Refresh)

2. **`src/application/commands/refresh_worker_labs_command.py`**
   - Added orphaned record detection logic
   - Added cleanup loop for orphaned records
   - Enhanced logging for reconciliation operations

### Background Jobs

3. **`src/application/jobs/labs_refresh_job.py`**
   - Added orphaned record detection logic (same as refresh command)
   - Added cleanup loop for orphaned records
   - Runs every 30 minutes (configurable via `LABS_REFRESH_INTERVAL`)

## Testing Scenarios

### Happy Path

1. User deletes lab via UI
2. Lab deleted from CML API ✓
3. Lab record deleted from MongoDB ✓
4. UI refreshes, lab no longer visible ✓
5. Background job runs, no orphans found ✓

### Edge Case: Phase 1 DB Delete Fails

1. User deletes lab via UI
2. Lab deleted from CML API ✓
3. Lab record delete from MongoDB fails ✗
4. UI might still show lab (stale data)
5. Background job runs in 30 minutes
6. Detects orphaned record (in DB but not CML)
7. Removes orphaned record ✓
8. UI eventually consistent ✓

### Edge Case: Direct CML Deletion

1. Admin deletes lab directly in CML UI
2. Our system has no knowledge of deletion
3. Lab record remains in MongoDB (stale)
4. Background job runs
5. Detects orphaned record (in DB but not CML)
6. Removes orphaned record ✓
7. Next UI refresh shows accurate data ✓

### Edge Case: Network Failure

1. User deletes lab via UI
2. CML API delete succeeds ✓
3. Network interruption before DB delete
4. Local record persists (stale)
5. User sees stale data temporarily
6. Background job runs
7. Detects orphan, removes it ✓
8. Eventually consistent ✓

## Monitoring & Observability

### Log Messages Added

**Phase 1 (Immediate Delete)**:

```
INFO: Deleting lab {lab_id} from worker {worker_id}
INFO: Lab {lab_id} deleted from CML on worker {worker_id}
INFO: Lab record {lab_id} removed from database
WARNING: Lab record {lab_id} not found in database (may not have been synced yet)
INFO: Successfully deleted lab {lab_id} from worker {worker_id}
ERROR: Failed to delete lab {lab_id} from worker {worker_id}: {error}
```

**Phase 2 (Background Reconciliation)**:

```
INFO: Found {count} orphaned lab records for worker {worker_id}: {lab_ids}
INFO: Removed orphaned lab record: {lab_id}
ERROR: Failed to remove orphaned lab record {lab_id}: {error}
```

### Metrics to Monitor

1. **Delete success rate**: Track Phase 1 completion rate
2. **Orphan detection count**: How many records cleaned by Phase 2
3. **Reconciliation duration**: Time for background job to run
4. **Error rates**: Track failures in both phases

## Benefits Summary

### User Experience

- ✅ Instant feedback - lab disappears immediately from UI
- ✅ No confusing stale data
- ✅ Predictable behavior matching user expectations

### Data Integrity

- ✅ Eventually consistent with CML (source of truth)
- ✅ Self-healing - catches missed deletions
- ✅ Handles deletions from any source (UI, direct CML, API)

### Architecture

- ✅ Separation of concerns (immediate vs. reconciliation)
- ✅ Resilient to failures in either phase
- ✅ Follows DDD principles
- ✅ No tight coupling between command and refresh
- ✅ Observability through comprehensive logging

### Maintenance

- ✅ Clear logging for debugging
- ✅ Easy to understand flow
- ✅ Testable phases (unit test each independently)
- ✅ Configurable reconciliation interval

## Future Enhancements

### Possible Improvements

1. **Soft Delete**: Add `deleted_at` timestamp instead of hard delete (allows undo)
2. **Deletion Events**: Publish CloudEvent for lab deletion (enables audit trail)
3. **Metrics Dashboard**: Track orphan detection and cleanup statistics
4. **Manual Reconciliation**: Admin endpoint to trigger reconciliation on-demand
5. **Deletion Notifications**: Notify users when their labs are deleted externally
6. **Batch Reconciliation**: Optimize to handle large numbers of labs efficiently

## Related Documentation

- Lab CRUD Operations: `notes/LAB_CRUD_OPERATIONS_COMPLETE.md`
- Labs Integration: `notes/LABS_INTEGRATION_COMPLETE.md`
- Background Jobs: `notes/APSCHEDULER_IMPROVEMENTS_COMPLETE.md`
- Worker Monitoring: `notes/WORKER_MONITORING_ARCHITECTURE.md`

## Completion Status

**Implementation**: ✅ Complete
**Testing**: ⏳ Pending manual validation
**Documentation**: ✅ Complete
**Deployment**: ⏳ Ready for staging deployment

Both phases are fully implemented and ready for testing in a live environment.
