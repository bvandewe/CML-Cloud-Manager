# Worker Metrics Source Separation

## Overview

The CML Worker aggregate has been refactored to clearly separate metrics by their data source, improving clarity, maintainability, and enabling independent display of each metric type in the UI.

## Metric Sources

### 1. **EC2 Metrics** (AWS EC2 API)

Infrastructure-level health checks for the EC2 instance.

**State Fields:**

- `ec2_instance_state_detail: str | None` - Instance status check (e.g., "ok", "impaired", "insufficient-data")
- `ec2_system_status_check: str | None` - System/hardware status check (e.g., "ok", "impaired")
- `ec2_last_checked_at: datetime | None` - Timestamp of last EC2 status check

**Domain Event:** `EC2MetricsUpdatedDomainEvent`

**Aggregate Method:** `worker.update_ec2_metrics(instance_state_detail, system_status_check, checked_at=None)`

**Data Source:** `aws_ec2_client.get_instance_status_checks()` via `DescribeInstanceStatus` API

**Updated By:** `RefreshWorkerMetricsCommandHandler` on every refresh

### 2. **CloudWatch Metrics** (AWS CloudWatch API)

Resource utilization metrics collected by AWS CloudWatch monitoring.

**State Fields:**

- `cloudwatch_cpu_utilization: float | None` - CPU usage percentage (0-100)
- `cloudwatch_memory_utilization: float | None` - Memory usage percentage (0-100)
- `cloudwatch_last_collected_at: datetime | None` - Timestamp of last CloudWatch collection
- `cloudwatch_detailed_monitoring_enabled: bool` - Whether 1-minute granularity is enabled

**Domain Event:** `CloudWatchMetricsUpdatedDomainEvent`

**Aggregate Method:** `worker.update_cloudwatch_metrics(cpu_utilization, memory_utilization, collected_at=None)`

**Data Source:** `aws_ec2_client.get_instance_resources_utilization()` via CloudWatch `GetMetricStatistics` API

**Updated By:** `RefreshWorkerMetricsCommandHandler` when instance status is RUNNING

**Requirements:**

- Instance must be RUNNING
- Detailed monitoring recommended for 1-minute granularity (costs $2.10/month)
- Basic monitoring provides 5-minute granularity (free)

### 3. **CML Metrics** (CML API)

Application-level metrics from the CML software itself.

**State Fields:**

- `cml_system_info: dict | None` - Full system information from CML `/api/v0/system_information`
- `cml_ready: bool` - CML application ready state
- `cml_uptime_seconds: int | None` - CML uptime in seconds
- `cml_labs_count: int` - Number of labs reported by CML API
- `cml_last_synced_at: datetime | None` - Timestamp of last successful CML API sync

**Domain Event:** `CMLMetricsUpdatedDomainEvent`

**Aggregate Method:** `worker.update_cml_metrics(system_info, ready, uptime_seconds, labs_count, synced_at=None)`

**Data Source:** CML API `GET /api/v0/system_information` endpoint

**Updated By:** (Future) Will be updated by `RefreshWorkerMetricsCommandHandler` or dedicated CML sync job

**Requirements:**

- Instance must be RUNNING
- CML service must be AVAILABLE
- HTTPS endpoint must be configured
- Valid CML API authentication

## Refresh Flow

The `RefreshWorkerMetricsCommand` now orchestrates separate updates for each source:

```
RefreshWorkerMetricsCommandHandler:
├── 1. Query EC2 Status (describe_instance_status)
│   └── worker.update_ec2_metrics()
│       └── Publishes EC2MetricsUpdatedDomainEvent
│
├── 2. Update Worker Status (EC2 state → CMLWorkerStatus)
│   └── worker.update_status()
│       └── Publishes CMLWorkerStatusUpdatedDomainEvent
│
├── 3. Query CloudWatch Metrics (if RUNNING)
│   └── worker.update_cloudwatch_metrics()
│       └── Publishes CloudWatchMetricsUpdatedDomainEvent
│
├── 4. Query CML API (if RUNNING + AVAILABLE) [FUTURE]
│   └── worker.update_cml_metrics()
│       └── Publishes CMLMetricsUpdatedDomainEvent
│
└── 5. Update OTEL Metrics
    ├── Status gauge (from worker.state.status)
    ├── CPU/Memory gauges (from cloudwatch_*)
    └── Labs gauge (from cml_labs_count)
```

## Backward Compatibility

The legacy `update_telemetry()` method is retained for backward compatibility:

- Marked as **DEPRECATED** in docstring
- Maps to CloudWatch CPU/memory fields
- Existing `CMLWorkerTelemetryUpdatedDomainEvent` handler updated to populate new fields
- Event sourcing maintains history with old events

## UI Display Recommendations

### Worker Detail View

**Infrastructure Section:**

```
EC2 Instance Health
├── Instance Status: ok | impaired | insufficient-data
├── System Status: ok | impaired
└── Last Checked: 2025-11-16 10:30:00 UTC
```

**Resource Utilization Section:**

```
CloudWatch Metrics
├── CPU: 45.2% (last 5 min avg)
├── Memory: 68.7% (last 5 min avg)
├── Last Collected: 2025-11-16 10:29:45 UTC
└── Monitoring: Detailed (1-min) | Basic (5-min)
```

**CML Application Section:**

```
CML Status
├── Ready: Yes | No
├── Uptime: 3 days 14 hours
├── Labs Count: 12 active labs
└── Last Synced: 2025-11-16 10:29:50 UTC
```

## API Response Structure

Worker details should expose metrics by source:

```json
{
  "id": "uuid",
  "name": "cml-worker-1",
  "status": "RUNNING",
  "ec2_metrics": {
    "instance_state_detail": "ok",
    "system_status_check": "ok",
    "last_checked_at": "2025-11-16T10:30:00Z"
  },
  "cloudwatch_metrics": {
    "cpu_utilization": 45.2,
    "memory_utilization": 68.7,
    "last_collected_at": "2025-11-16T10:29:45Z",
    "detailed_monitoring_enabled": true
  },
  "cml_metrics": {
    "ready": true,
    "uptime_seconds": 311400,
    "labs_count": 12,
    "last_synced_at": "2025-11-16T10:29:50Z",
    "system_info": { ... }
  }
}
```

## Benefits

1. **Clear Data Provenance**: Each metric clearly shows its source
2. **Independent Collection**: Sources can be queried/updated independently
3. **Better Error Handling**: Failure in one source doesn't affect others
4. **Timestamp Tracking**: Each source has its own "last updated" timestamp
5. **UI Flexibility**: UI can display/hide sections based on data availability
6. **Future Extensibility**: Easy to add new sources (e.g., Prometheus, custom agents)

## Implementation Status

✅ **Completed:**

- State fields separated by source
- Domain events created for each source
- Aggregate methods for each source
- Event handlers for all events
- RefreshWorkerMetricsCommand uses source-specific methods
- OTEL metrics use source-specific fields
- Backward compatibility maintained

📋 **Pending:**

- CML API client implementation
- CML metrics collection in refresh command
- UI updates to display source-separated metrics
- API response DTO updates to expose metric sources
- Documentation updates for API consumers
