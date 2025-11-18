# Auto-Import Workers Background Job

## Overview

The `AutoImportWorkersJob` is a recurrent background job that automatically discovers and imports CML Worker instances from AWS EC2 at regular intervals. This eliminates the need for manual worker registration when instances are created outside the application.

## Architecture

**File**: `src/application/jobs/auto_import_workers_job.py`

**Pattern**: Recurrent Background Job with `@backgroundjob` decorator

**Dependencies**:

- `Mediator` - For executing `BulkImportCMLWorkersCommand`
- Uses existing bulk import logic for consistency
- Registered automatically at boot via module scanning

## Configuration

The job is controlled via environment variables in `application/settings.py`:

```python
# Enable/disable the job
AUTO_IMPORT_WORKERS_ENABLED=false  # Default: disabled

# Execution interval (seconds)
AUTO_IMPORT_WORKERS_INTERVAL=3600  # Default: 1 hour

# AWS region to scan
AUTO_IMPORT_WORKERS_REGION=us-east-1  # Default: us-east-1

# AMI name pattern to search for
AUTO_IMPORT_WORKERS_AMI_NAME=CML-2.7.0-*  # Required when enabled
```

## How It Works

1. **Scheduled Execution**: Job runs at intervals defined by `AUTO_IMPORT_WORKERS_INTERVAL`
2. **EC2 Discovery**: Searches for instances matching `AUTO_IMPORT_WORKERS_AMI_NAME` in `AUTO_IMPORT_WORKERS_REGION`
3. **Bulk Import**: Executes `BulkImportCMLWorkersCommand` via Mediator
4. **Idempotent**: Skips instances already registered in the database
5. **Logging**: Reports imported/skipped/total counts with tracing

## Execution Flow

```
AutoImportWorkersJob.execute_async()
├── Check if enabled (skip if disabled)
├── Validate settings (region + AMI name)
├── Create BulkImportCMLWorkersCommand
│   └── aws_region: from AUTO_IMPORT_WORKERS_REGION
│   └── ami_name: from AUTO_IMPORT_WORKERS_AMI_NAME
│   └── created_by: "auto-import-job"
├── Execute via Mediator
│   └── BulkImportCMLWorkersCommandHandler
│       ├── Resolve AMI name to AMI IDs
│       ├── Search EC2 instances
│       ├── Filter out already-imported instances
│       └── Import new instances
└── Return results (imported/skipped counts)
```

## Return Values

The job returns a dict with execution results:

```python
{
    "status": "success" | "skipped" | "failed" | "error",
    "total_found": 10,           # Total instances found
    "total_imported": 3,         # New instances imported
    "total_skipped": 7,          # Already-imported instances
    "imported_worker_ids": [...] # List of imported instance IDs
}
```

## Registration

The job is automatically registered at application startup via:

1. **Decorator**: `@backgroundjob(task_type="recurrent", interval=app_settings.auto_import_workers_interval)`
2. **Module Scanning**: `BackgroundTaskScheduler.configure(builder, modules=["application.jobs"])`
3. **No Manual Registration Required**: All `@backgroundjob` decorated classes in `application.jobs` are auto-discovered

## Job Lifecycle

1. **Boot**: Job registered with APScheduler during `BackgroundTaskScheduler.configure()`
2. **Scheduling**: First run scheduled after `AUTO_IMPORT_WORKERS_INTERVAL` seconds
3. **Execution**: Runs at regular intervals until application shutdown
4. **Persistence**: Job state persisted in Redis/MongoDB (configured in `background_job_store`)
5. **Recovery**: Job resumes after application restart from persisted state

## Integration with Existing Features

- **Reuses `BulkImportCMLWorkersCommand`**: Consistent import logic with manual bulk imports
- **Respects Worker Repository**: Uses existing `CMLWorkerRepository` for duplicate detection
- **CloudEvents**: Import events published via existing event infrastructure
- **Tracing**: OpenTelemetry spans for observability
- **Logging**: Structured logs with job context

## Use Cases

### 1. Auto-Scale Worker Fleet

When external auto-scaling creates EC2 instances:

```bash
# EC2 Auto Scaling Group launches instances with AMI "CML-2.7.0-prod"
# Job automatically imports them within 1 hour
AUTO_IMPORT_WORKERS_ENABLED=true
AUTO_IMPORT_WORKERS_AMI_NAME=CML-2.7.0-prod
AUTO_IMPORT_WORKERS_REGION=us-west-2
AUTO_IMPORT_WORKERS_INTERVAL=300  # 5 minutes for faster discovery
```

### 2. Multi-Region Deployments

Run separate instances with different configurations:

```bash
# Instance 1 - US East
AUTO_IMPORT_WORKERS_REGION=us-east-1
AUTO_IMPORT_WORKERS_AMI_NAME=CML-*-east

# Instance 2 - US West
AUTO_IMPORT_WORKERS_REGION=us-west-2
AUTO_IMPORT_WORKERS_AMI_NAME=CML-*-west
```

### 3. Development/Staging Environments

Auto-discover ephemeral workers:

```bash
AUTO_IMPORT_WORKERS_ENABLED=true
AUTO_IMPORT_WORKERS_AMI_NAME=CML-*-dev
AUTO_IMPORT_WORKERS_INTERVAL=1800  # 30 minutes
```

## Monitoring

### Logs

```
🔄 Starting auto-import workers job (region: us-east-1, AMI name: CML-2.7.0-*)
✅ Auto-import completed: 3 imported, 7 skipped, 10 total found
⏭️ Auto-import workers disabled - skipping job
⚠️ auto_import_workers_ami_name not configured
❌ Auto-import failed: [error details]
```

### Metrics (OpenTelemetry)

- `job.type`: "auto_import_workers"
- `job.aws_region`: Region scanned
- `job.ami_name`: AMI pattern searched
- `job.workers_found`: Total instances discovered
- `job.workers_imported`: New instances imported
- `job.workers_skipped`: Already-imported instances
- `job.status`: "success" | "failed" | "error"

## Safety & Error Handling

1. **Disabled by Default**: Must explicitly enable via `AUTO_IMPORT_WORKERS_ENABLED=true`
2. **Validation**: Checks for required settings before execution
3. **Graceful Degradation**: Logs warnings and skips execution if misconfigured
4. **Non-Blocking**: Errors in auto-import don't affect other background jobs
5. **Idempotent**: Safe to run multiple times - skips existing workers

## Testing

```python
# Enable job with short interval for testing
AUTO_IMPORT_WORKERS_ENABLED=true
AUTO_IMPORT_WORKERS_INTERVAL=60  # 1 minute
AUTO_IMPORT_WORKERS_REGION=us-east-1
AUTO_IMPORT_WORKERS_AMI_NAME=CML-test-*

# Monitor logs for execution
docker compose logs -f app | grep -i "auto-import"
```

## Comparison with Other Jobs

| Job | Interval | Purpose | Command Used |
|-----|----------|---------|--------------|
| `WorkerMetricsCollectionJob` | 5 min | Collect metrics from all workers | `RefreshWorkerMetricsCommand` + `RefreshWorkerLabsCommand` |
| `LabsRefreshJob` | 30 min | Sync lab records from CML API | Direct CML API calls |
| `AutoImportWorkersJob` | 1 hour | Discover and import new workers | `BulkImportCMLWorkersCommand` |

## Related Files

- **Job Implementation**: `src/application/jobs/auto_import_workers_job.py`
- **Settings**: `src/application/settings.py` (lines 163-172)
- **Command**: `src/application/commands/bulk_import_cml_workers_command.py`
- **Registration**: `src/main.py` (BackgroundTaskScheduler configuration)
- **Changelog**: `CHANGELOG.md` (Unreleased section)
