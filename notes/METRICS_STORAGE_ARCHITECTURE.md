# Worker Metrics Storage Architecture

## Current State Analysis

### ✅ What Exists Today

#### 1. **CMLWorker Aggregate State** - Stores ONLY Latest Snapshot

```python
# src/domain/entities/cml_worker.py
class CMLWorkerState(AggregateState[str]):
    # Current snapshot metrics (SINGLE point in time)
    cpu_utilization: float | None        # Latest average CPU %
    memory_utilization: float | None      # Latest average memory %
    last_activity_at: datetime | None    # Last time activity detected
    active_labs_count: int               # Current number of active labs
```

**Storage**: MongoDB `workers` collection (one document per worker)

**Purpose**: Represents the **current operational state** of a worker for:

- UI dashboard displays (current status)
- Business rules (idle detection, termination decisions)
- Quick queries (get worker current state)

#### 2. **Domain Event** - CMLWorkerTelemetryUpdatedDomainEvent

```python
# src/domain/events/cml_worker.py
class CMLWorkerTelemetryUpdatedDomainEvent(DomainEvent):
    aggregate_id: str
    last_activity_at: datetime
    active_labs_count: int
    cpu_utilization: Optional[float]
    memory_utilization: Optional[float]
    updated_at: datetime
```

**Storage**: MongoDB `domain_events` collection (event sourcing)

**Purpose**: Audit trail of telemetry updates over time

#### 3. **Real-Time Metrics Query** - `/resources` Endpoint

```python
# Returns live CloudWatch data for a time range
GET /api/workers/region/{region}/workers/{worker_id}/resources?start_time=10m

Response: Ec2InstanceResourcesUtilization
{
    "id": "i-1234567890abcdef0",
    "region_name": "us-east-1",
    "relative_start_time": "10m",
    "avg_cpu_utilization": "45.2",
    "avg_memory_utilization": "62.8",
    "start_time": "2025-11-16T10:00:00Z",
    "end_time": "2025-11-16T10:10:00Z"
}
```

**Storage**: AWS CloudWatch (NOT stored in your DB)

**Purpose**: On-demand historical metrics for UI charts/graphs

---

## ❌ What's Missing

### Problem: Historical Metrics Not Persisted

Currently, there is **NO persistent storage of historical metrics** in your database:

1. **CMLWorker aggregate** - Only stores latest snapshot (overwritten on each update)
2. **Domain events** - Capture changes but not optimized for time-series queries
3. **CloudWatch** - AWS storage, expensive to query repeatedly, retention limits

### UI Limitations

The frontend **cannot show**:

- Trends over time (CPU usage last 24 hours)
- Historical comparisons (week-over-week)
- Aggregated statistics (average daily utilization)
- Metrics after worker termination (CloudWatch data expires)

---

## 📋 Options for Persistent Metrics Storage

### Option 1: Extend CMLWorker Aggregate with Metrics Log (❌ NOT RECOMMENDED)

```python
class CMLWorkerState(AggregateState[str]):
    # ... existing fields ...

    # NEW: Historical metrics log
    metrics_history: List[WorkerMetricsSnapshot] = []  # Last X snapshots

@dataclass
class WorkerMetricsSnapshot:
    timestamp: datetime
    cpu_utilization: float
    memory_utilization: float
    active_labs_count: int
```

**Problems**:

- ❌ Violates Single Responsibility Principle (worker lifecycle ≠ metrics storage)
- ❌ Aggregate documents grow unbounded (MongoDB document size limits)
- ❌ Time-series queries inefficient (scan entire document)
- ❌ Metrics outlive worker (what happens when worker terminated?)
- ❌ Not optimized for time-series data patterns

### Option 2: Separate WorkerMetrics Aggregate (⚠️ POSSIBLE BUT OVERKILL)

```python
class WorkerMetrics(AggregateRoot[WorkerMetricsState, str]):
    """Separate aggregate for worker metrics history"""
    pass

class WorkerMetricsState(AggregateState[str]):
    worker_id: str
    collected_at: datetime
    cpu_utilization: float
    memory_utilization: float
    active_labs_count: int
```

**Storage**: MongoDB `worker_metrics` collection

**Pros**:

- ✅ Separate lifecycle from worker
- ✅ Each metric snapshot is an independent entity
- ✅ Persists after worker termination

**Cons**:

- ⚠️ Not a true domain aggregate (no business rules/invariants)
- ⚠️ Overkill for simple time-series data
- ⚠️ MongoDB not optimized for time-series (no time-series collection features until v5.0+)

### Option 3: Time-Series Collection (✅ RECOMMENDED)

**Use MongoDB Time-Series Collections** (MongoDB 5.0+):

```python
# Simple data model (NOT an aggregate root)
@dataclass
class WorkerMetricsSample:
    """Time-series sample for worker metrics"""
    worker_id: str           # metadata
    region: str              # metadata
    timestamp: datetime       # time field
    cpu_utilization: float    # measurement
    memory_utilization: float # measurement
    active_labs_count: int    # measurement
    status: str              # metadata
```

**Storage**: MongoDB time-series collection `worker_metrics_timeseries`

```python
db.create_collection(
    "worker_metrics_timeseries",
    timeseries={
        "timeField": "timestamp",
        "metaField": "worker_id",
        "granularity": "minutes"
    },
    expireAfterSeconds=2592000  # 30 days retention
)
```

**Pros**:

- ✅ Optimized for time-series data (compression, query performance)
- ✅ Automatic expiration (TTL for old data)
- ✅ Efficient aggregation queries (time-based grouping)
- ✅ Simple data model (just measurements, no domain logic)
- ✅ Independent of worker lifecycle

**Cons**:

- ⚠️ Requires MongoDB 5.0+ (check your version)
- ⚠️ Different query patterns than regular collections

### Option 4: External Time-Series Database (🎯 BEST FOR SCALE)

Use dedicated time-series database:

**Options**:

- **Prometheus** - Pull-based metrics scraping, PromQL queries
- **InfluxDB** - Purpose-built time-series DB, SQL-like query language
- **TimescaleDB** - PostgreSQL extension, full SQL support
- **VictoriaMetrics** - High-performance Prometheus alternative

**Pros**:

- ✅ Purpose-built for metrics (best performance)
- ✅ Rich query languages (aggregations, downsampling, retention policies)
- ✅ Built-in visualization tools (Grafana integration)
- ✅ Industry-standard observability stack

**Cons**:

- ⚠️ Additional infrastructure to manage
- ⚠️ More complex deployment
- ⚠️ Learning curve for new technology

---

## 🎯 Recommended Architecture

### Phase 1: Minimal (Current State + CloudWatch)

**Status**: ✅ Already Implemented

```
┌─────────────────────┐
│   CMLWorker         │  Stores: Latest snapshot only
│   Aggregate         │  - cpu_utilization (current)
│                     │  - memory_utilization (current)
└─────────────────────┘

┌─────────────────────┐
│   AWS CloudWatch    │  Stores: Time-series metrics (AWS-managed)
│                     │  - Query via /resources endpoint
│                     │  - Retention: AWS default (15 months)
└─────────────────────┘
```

**Use Case**: Basic monitoring, current status display

### Phase 2: MongoDB Time-Series (Recommended Next Step)

**Status**: 📝 To Be Implemented

```
┌─────────────────────┐
│   CMLWorker         │  Stores: Latest snapshot only
│   Aggregate         │  - For quick "current state" queries
└─────────────────────┘

┌─────────────────────┐
│   MongoDB TS        │  Stores: Historical metrics samples
│   Collection        │  - worker_metrics_timeseries
│                     │  - 30 day retention (configurable)
└─────────────────────┘

┌─────────────────────┐
│   AWS CloudWatch    │  Stores: Raw AWS metrics
│                     │  - Fallback for long-term history
└─────────────────────┘
```

**Implementation**:

```python
# New repository (NOT an aggregate root repository)
class WorkerMetricsRepository:
    """Repository for time-series metrics storage"""

    async def add_sample(self, sample: WorkerMetricsSample) -> None:
        """Insert a metrics sample"""
        pass

    async def get_samples(
        self,
        worker_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[WorkerMetricsSample]:
        """Query samples for time range"""
        pass

    async def get_aggregated_stats(
        self,
        worker_id: str,
        start_time: datetime,
        end_time: datetime,
        interval: timedelta,
    ) -> List[MetricsAggregation]:
        """Get aggregated metrics (avg, min, max per interval)"""
        pass
```

**When to Write Samples**:

```python
# In WorkerMetricsCollectionJob.run_every()
async def run_every(self, *args, **kwargs) -> None:
    # ... existing code ...

    # After updating worker aggregate:
    await worker_repository.update_async(worker)

    # NEW: Also persist to time-series collection
    metrics_sample = WorkerMetricsSample(
        worker_id=self.worker_id,
        region=worker.state.aws_region,
        timestamp=datetime.now(timezone.utc),
        cpu_utilization=worker.state.cpu_utilization,
        memory_utilization=worker.state.memory_utilization,
        active_labs_count=worker.state.active_labs_count,
        status=worker.state.status.value,
    )
    await metrics_repository.add_sample(metrics_sample)
```

### Phase 3: Dedicated Observability Stack (Future)

**Status**: 🔮 Future Enhancement

```
┌─────────────────────┐
│   Prometheus        │  Pull-based metrics scraping
│   + Grafana         │  Rich dashboards, alerting
└─────────────────────┘
        ↓
┌─────────────────────┐
│   Metrics Exporter  │  FastAPI /metrics endpoint
│   (application)     │  Exposes worker metrics in Prometheus format
└─────────────────────┘
```

**Benefits**:

- Industry-standard observability
- Pre-built Grafana dashboards
- Advanced alerting rules
- Cross-system correlation (app + infra metrics)

---

## 🏗️ Implementation Recommendation

### Immediate Next Steps

1. **Keep Current Architecture** (Phase 1)
   - ✅ CMLWorker stores latest snapshot
   - ✅ `/resources` endpoint queries CloudWatch on-demand
   - ✅ Domain events capture changes (audit trail)

2. **Add MongoDB Time-Series Collection** (Phase 2)
   - Create time-series collection in MongoDB
   - Add `WorkerMetricsRepository` (simple data access, NOT aggregate repository)
   - Modify `WorkerMetricsCollectionJob` to write samples after each collection
   - Add new API endpoint: `GET /workers/{id}/metrics/history?start=X&end=Y`
   - Update UI to show historical charts from time-series data

3. **Future Migration** (Phase 3)
   - Evaluate Prometheus + Grafana when ready to scale
   - Keep time-series collection for application-specific metrics
   - Use Prometheus for infrastructure and cross-system metrics

### What NOT to Do

- ❌ Don't add `metrics_history: List[]` to CMLWorker aggregate
- ❌ Don't create WorkerMetrics as an AggregateRoot (no business rules)
- ❌ Don't query CloudWatch repeatedly for historical data (expensive)
- ❌ Don't try to query domain events for metrics analysis (wrong tool)

---

## Summary: Fundamentals Clarified

### Current State of Worker Metrics

1. **Latest Snapshot**: Stored in `CMLWorker.state` (MongoDB workers collection)
   - Purpose: Current operational state for business rules and quick queries
   - Updated: Every 5 minutes by `WorkerMetricsCollectionJob`

2. **Historical Metrics**: Queried from AWS CloudWatch (NOT stored in your DB)
   - Purpose: On-demand time-series data for UI charts
   - Accessed: Via `/resources` endpoint when user opens Metrics tab

3. **Change History**: Captured in domain events (MongoDB domain_events collection)
   - Purpose: Audit trail, event sourcing, debugging
   - Not optimized: For time-series analysis or metrics queries

### Recommended Enhancement

**Add MongoDB Time-Series Collection**:

- Simple data model (not an aggregate root)
- Stores historical samples with automatic expiration
- Optimized for time-series queries and aggregations
- Independent of worker lifecycle (survives worker termination)

This gives you:

- ✅ Current state in worker aggregate (fast queries)
- ✅ Historical trends in time-series collection (charts/graphs)
- ✅ Raw metrics in CloudWatch (long-term backup)
- ✅ Change audit in domain events (compliance)

Each storage mechanism serves a different purpose - no duplication, clear separation of concerns.
