# Worker Idle Detection and Auto-Pause Implementation

## Overview

Implement worker activity tracking and automatic pause functionality to reduce AWS costs by stopping idle CML workers. Workers are monitored for user activity via CML telemetry events, and automatically paused (stopped in AWS) when idle for a configurable duration.

## Architecture

### Hybrid Two-Tier Monitoring Approach

**Tier 1 (Existing)**: Worker metrics collection (5-minute interval)

- Collects EC2 status, CloudWatch metrics, CML system data
- Continues to work for paused workers (monitors AWS state)

**Tier 2 (New)**: Activity detection job (30-minute interval)

- Fetches CML telemetry events and filters for user activity
- Detects idle timeout and triggers auto-pause
- Separate frequency prevents API overload (telemetry endpoint returns ALL events)

### Event Storage Strategy

- **Lightweight tracking**: Store only last 10 relevant events in worker aggregate
- **Stateful detection**: Track last activity timestamp without storing all historical events
- **Rationale**: Avoids scaling issues with large event arrays while providing visibility

## Event Categories

### Relevant Categories (User Activity Indicators)

From analysis of sample data (3,136 total events):

- `start_lab`, `stop_lab`, `wipe_lab`, `import_lab`, `export_lab` (30 events)
- `start_node`, `stop_node`, `queue_node`, `boot_node` (196 events)
- `user_activity` with user_id NOT matching `^00000000-0000-.*` (genuine user logins)

### Excluded Categories (Automated/Noise)

- `system_stats` (207 events - automated polling by this app)
- `running_nodes` (207 events - periodic automated checks)
- `user_activity` with admin UUID pattern `00000000-0000-.*` (automated API calls)
- System info: `aaa_info`, `license_info`, `dmiinfo`, `cpuinfo`, `meminfo`, `blkinfo`, `hypervisor`

**Total relevant events**: ~226 out of 3,136 (7.2%) - filtering significantly reduces noise

## Domain Model Changes

### CMLWorkerState Extensions

```python
# Activity tracking
last_activity_at: datetime | None  # Last relevant user activity detected
last_activity_check_at: datetime | None  # Last time telemetry was checked
recent_activity_events: list[dict]  # Last 10 relevant events (category, timestamp, data)

# Pause/Resume lifecycle tracking
auto_pause_count: int  # Count of automatic pauses by idle detection
manual_pause_count: int  # Count of manual stop operations
auto_resume_count: int  # Count of automatic resumes (if implemented)
manual_resume_count: int  # Count of manual start operations
last_paused_at: datetime | None  # Timestamp of last pause (auto or manual)
last_resumed_at: datetime | None  # Timestamp of last resume (auto or manual)
paused_by: str | None  # User/system that triggered last pause
pause_reason: str | None  # "idle_timeout" | "manual" | "external"

# Idle detection state
next_idle_check_at: datetime | None  # Next scheduled activity check
target_pause_at: datetime | None  # Calculated pause time if no activity detected
```

### New Domain Events

```python
WorkerActivityUpdatedDomainEvent  # Activity timestamp + recent events updated
WorkerPausedDomainEvent  # Worker paused (auto or manual)
WorkerResumedDomainEvent  # Worker resumed (auto or manual)
```

## Application Layer

### Queries

1. **GetWorkerTelemetryEventsQuery**
   - Fetches raw telemetry events from CML API (`GET /telemetry/events`)
   - Filters for relevant event categories
   - Excludes automated admin user activities
   - Returns: `List[TelemetryEventDto]`

2. **GetWorkerEC2StateQuery**
   - Fetches EC2 instance state from AWS API (works when worker stopped)
   - Retrieves instance tags and metadata
   - Returns: `EC2InstanceStateDto` (state, tags, launch_time, etc.)

3. **GetWorkerActivityQuery**
   - Returns recent activity events from worker aggregate
   - Includes lifecycle timestamps and pause/resume counts
   - Returns: `WorkerActivityDto`

4. **GetWorkerIdleStatusQuery**
   - Calculates idle status and countdown to pause
   - Checks if in snooze period
   - Returns: `WorkerIdleStatusDto` (is_idle, idle_duration, target_pause_at, etc.)

### Commands

1. **DetectWorkerIdleCommand**
   - Orchestrates idle detection for a single worker
   - Fetches telemetry events via query
   - Updates last_activity_at if relevant events found
   - Triggers PauseWorkerCommand if idle timeout exceeded
   - Returns: `OperationResult[IdleDetectionResultDto]`

2. **PauseWorkerCommand**
   - Stops worker in AWS (similar to StopCMLWorkerCommand)
   - Records pause reason and metrics
   - Increments auto_pause_count or manual_pause_count
   - Returns: `OperationResult[bool]`

3. **UpdateWorkerActivityCommand** (internal)
   - Updates activity tracking fields in worker aggregate
   - Stores recent events (max 10)
   - Emits WorkerActivityUpdatedDomainEvent
   - Returns: `OperationResult[dict]`

### Background Jobs

**ActivityDetectionJob** (RecurrentBackgroundJob)

- Interval: Configurable (default 30 minutes)
- Iterates through all running workers
- Executes DetectWorkerIdleCommand for each
- Respects snooze period (1 hour after resume)
- Decorator: `@backgroundjob(task_type="recurrent", interval=1800)`

## Settings

```python
# Idle detection configuration
worker_idle_timeout_minutes: int = 60  # Idle time before auto-pause
worker_activity_detection_interval: int = 1800  # 30 minutes between checks
worker_auto_pause_enabled: bool = True  # Feature flag
worker_auto_pause_snooze_minutes: int = 60  # Prevent re-pause after resume
worker_activity_events_max_stored: int = 10  # Max recent events to store

# Event filtering
worker_activity_relevant_categories: list[str] = [
    "start_lab", "stop_lab", "wipe_lab", "import_lab", "export_lab",
    "start_node", "stop_node", "queue_node", "boot_node",
    "user_activity"  # Filtered further by user_id pattern
]
worker_activity_excluded_user_pattern: str = "^00000000-0000-.*"  # Admin UUIDs
```

## Integration Layer

### CMLApiClient Extensions

```python
async def get_telemetry_events(
    self,
    worker_endpoint: str,
    auth_token: str | None = None
) -> list[dict]:
    """Fetch all telemetry events from CML worker.

    Endpoint: GET /api/v0/telemetry/events
    No parameters supported - returns full list.

    Returns:
        List of event objects with category, timestamp, data
    """
```

### AwsEc2Client Extensions

No changes needed - existing methods support querying stopped instances:

- `describe_instance()` - works for stopped instances
- `get_instance_tags()` - works for stopped instances

## API Endpoints

### New Endpoints

1. **GET /region/{aws_region}/workers/{worker_id}/activity**
   - Returns recent activity events and lifecycle timestamps
   - Response: `WorkerActivityDto`

2. **GET /region/{aws_region}/workers/{worker_id}/idle-status**
   - Returns idle detection state with countdown
   - Response: `WorkerIdleStatusDto`

3. **POST /region/{aws_region}/workers/{worker_id}/pause**
   - Manually pause worker (alias for stop with tracking)
   - Records as manual pause
   - Response: `OperationResult[bool]`

## UI Integration

### Worker Details Modal - Monitoring Tab

**New Section: "Activity & Lifecycle"**

Display:

- Last activity timestamp (human-readable, e.g., "2 hours ago")
- Recent activity events table (last 10):
  - Timestamp | Event Category | Details
- Lifecycle statistics:
  - Auto-pause count | Manual pause count
  - Auto-resume count | Manual resume count
  - Last paused: timestamp + reason
  - Last resumed: timestamp + by whom
- Idle status indicator:
  - Current state: Active / Idle (XX minutes)
  - Next check: timestamp
  - Auto-pause in: countdown timer (if idle)
  - Snooze status: "Protected from auto-pause for XX minutes"

## Idle Detection Algorithm

```python
def detect_idle(worker: CMLWorker, telemetry_events: list[dict], settings: Settings) -> IdleDecision:
    """
    Determine if worker should be paused due to inactivity.
    """
    # Filter for relevant events since last check
    relevant_events = filter_relevant_events(
        events=telemetry_events,
        categories=settings.worker_activity_relevant_categories,
        exclude_user_pattern=settings.worker_activity_excluded_user_pattern,
        since=worker.last_activity_check_at
    )

    # Update activity timestamp if relevant events found
    if relevant_events:
        update_last_activity(worker, relevant_events)
        return IdleDecision(should_pause=False, reason="recent_activity")

    # Calculate idle duration
    idle_duration = now() - worker.last_activity_at
    idle_threshold = timedelta(minutes=settings.worker_idle_timeout_minutes)

    # Check if idle timeout exceeded
    if idle_duration < idle_threshold:
        target_pause = worker.last_activity_at + idle_threshold
        return IdleDecision(
            should_pause=False,
            reason="not_idle_yet",
            target_pause_at=target_pause
        )

    # Check snooze period (prevent immediate re-pause after resume)
    if in_snooze_period(worker, settings):
        snooze_until = worker.last_resumed_at + timedelta(minutes=settings.worker_auto_pause_snooze_minutes)
        return IdleDecision(
            should_pause=False,
            reason="in_snooze_period",
            snooze_until=snooze_until
        )

    # Trigger auto-pause
    return IdleDecision(
        should_pause=True,
        reason="idle_timeout_exceeded",
        idle_duration=idle_duration
    )
```

## Event Filtering Logic

```python
def filter_relevant_events(
    events: list[dict],
    categories: list[str],
    exclude_user_pattern: str,
    since: datetime | None
) -> list[dict]:
    """
    Filter telemetry events for genuine user activity.
    """
    relevant = []

    for event in events:
        # Skip if before last check timestamp
        if since and parse_timestamp(event["timestamp"]) <= since:
            continue

        # Check category
        category = event["category"]
        if category not in categories:
            continue

        # Special handling for user_activity
        if category == "user_activity":
            user_id = event.get("data", {}).get("user_id", "")
            # Exclude automated admin API calls
            if re.match(exclude_user_pattern, user_id):
                continue

        relevant.append(event)

    return relevant
```

## Resume Detection

Since workers can be resumed manually or externally (via AWS console):

1. **Existing metrics collection** already detects state changes
2. **UpdateCMLWorkerStatusCommand** handles state transitions
3. **Extend logic** to detect resume:
   - If previous state was STOPPED and new state is RUNNING
   - Update `last_resumed_at` timestamp
   - Reset `target_pause_at` to None
   - Determine if resume was manual (via app) or external (AWS console)

## Migration Path

### Phase 1 (This Implementation)

- Domain model extensions
- Activity detection and auto-pause
- Manual pause/resume tracking
- Basic UI display

### Phase 2 (Future)

- Auto-resume on new activity detection (requires webhook or push mechanism)
- Advanced analytics (idle patterns, cost savings)
- Per-worker idle timeout configuration
- Multi-region optimization

## Scalability Considerations

1. **Event Volume**: 30-minute polling interval reduces API load
2. **Storage**: Only 10 events per worker (not cumulative)
3. **Filtering**: Server-side filtering reduces data transfer
4. **Async Processing**: Background job doesn't block user operations
5. **AWS Costs**: Monitoring stopped instances is free

## Testing Strategy

1. **Unit Tests**:
   - Event filtering logic
   - Idle detection algorithm
   - Snooze period calculation

2. **Integration Tests**:
   - Telemetry API integration
   - EC2 state queries for stopped workers
   - Command orchestration

3. **Manual Testing**:
   - Verify event filtering with sample data
   - Test auto-pause with different idle timeouts
   - Verify snooze period prevents immediate re-pause

## Rollout

1. Deploy with `worker_auto_pause_enabled=false` initially
2. Monitor activity detection accuracy (logs)
3. Enable for non-production workers first
4. Gradually enable for production with conservative timeout (2+ hours)

## Success Metrics

- AWS cost reduction (stopped instance hours)
- Auto-pause accuracy (false positives/negatives)
- User satisfaction (not paused during active use)
- Resume response time (user convenience)

## Implementation Date

November 19, 2025
