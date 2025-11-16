# CML Worker Monitoring & Reactive Management Architecture

**Status**: Design Proposal
**Date**: 2025-11-16
**Context**: Post-import feature implementation - adding background monitoring and reactive notification handling

---

## Executive Summary

This document outlines the architecture for implementing **reactive worker monitoring** that triggers automatically when workers are registered (created or imported). The design separates concerns into two independent reactive streams aligned with CQRS principles and prepares the system for evolution toward a generic CML Resource Manager.

---

## Current State Analysis

### What Works

- ✅ Worker CRUD operations (create, import, start, stop, terminate)
- ✅ Manual status sync via `UpdateCMLWorkerStatusCommand`
- ✅ CloudEvent publishing for domain events
- ✅ Repository layer with queries (`get_active_workers_async`, `get_by_status_async`)
- ✅ AWS EC2 integration (instance management, status checks, CloudWatch metrics)

### What's Missing

- ❌ Automatic background monitoring when workers are registered
- ❌ Reactive handling of worker lifecycle changes
- ❌ Notification/alert processing for worker events
- ❌ Metrics collection orchestration
- ❌ Separation of concerns: compute layer vs. workload layer

---

## Design Goals

### Primary Objectives

1. **Auto-start monitoring** when a worker is registered (created/imported)
2. **Reactive architecture** using Neuroglia's Rx patterns
3. **Separation of concerns**: Metrics scraping vs. notification handling
4. **CQRS alignment**: Read-side optimizations, write-side commands
5. **Scalability**: Prepare for multi-worker clusters and CML workload distribution

### Non-Goals (Future Work)

- Full workload scheduler/orchestrator
- Multi-region worker clustering
- Auto-scaling based on demand

---

## Architectural Decision: Two Independent Reactive Channels

### Rationale

Based on CQRS separation and the pyneuro reactive programming patterns, we should split monitoring into **two independent observable streams**:

#### 1. **Metrics Collection Channel** (Read-Heavy)

- **Purpose**: Periodically scrape AWS CloudWatch metrics and EC2 status
- **Frequency**: Every 1-5 minutes
- **Operations**: Read from AWS, write to worker state
- **Side effects**: Update worker telemetry, detect drift

#### 2. **Notification/Event Channel** (Write-Heavy)

- **Purpose**: React to worker domain events and external notifications
- **Trigger**: Domain events (worker.created, worker.started, worker.status_changed)
- **Operations**: Process alerts, trigger webhooks, log events
- **Side effects**: Send notifications, update dashboards, trigger remediation

### Analogy to Existing Pattern

```
CloudEvents.Ingestor (Rx.Subject)  →  Subscribes to domain events (read)
CloudEvents.Publisher (Rx.Observer) →  Publishes to external systems (write)

Worker.MetricsCollector (Rx.Subject)  →  Polls AWS metrics (read)
Worker.NotificationHandler (Rx.Observer) →  Reacts to worker events (write)
```

---

## Proposed Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    CML Worker Aggregate                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Domain Events: WorkerCreated, WorkerImported,            │  │
│  │                 WorkerStatusChanged, etc.                 │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ├─────────────────────────────────────┐
                           │                                     │
                           ▼                                     ▼
          ┌────────────────────────────┐          ┌──────────────────────────┐
          │  WorkerMetricsCollector    │          │ WorkerNotificationHandler│
          │  (Application Service)     │          │  (Application Service)   │
          │                            │          │                          │
          │  - Rx.Subject              │          │  - Rx.Observer           │
          │  - Polls AWS every N min   │          │  - Listens to events     │
          │  - Updates telemetry       │          │  - Sends alerts          │
          │  - Detects status drift    │          │  - Triggers webhooks     │
          └────────────┬───────────────┘          └──────────┬───────────────┘
                       │                                     │
                       ▼                                     ▼
          ┌────────────────────────────┐          ┌──────────────────────────┐
          │  WorkerMonitoringScheduler │          │  CloudEventBus           │
          │  (Background Job Manager)  │          │  (Event Distribution)    │
          │                            │          │                          │
          │  - APScheduler             │          │  - Publishes to channels │
          │  - Manages collector jobs  │          │  - Redis/RabbitMQ        │
          │  - Auto-start/stop         │          │  - Event filtering       │
          └────────────────────────────┘          └──────────────────────────┘
```

---

## Detailed Component Design

### 1. WorkerMetricsCollector (Application Service)

**Type**: `Rx.Subject` (Observable + Observer)
**Responsibility**: Poll AWS for worker metrics and status
**Lifecycle**: Starts when worker registered, stops when worker terminated

```python
# src/application/services/worker_metrics_collector.py

from neuroglia.reactive import RxAsyncSubject
from integration.services.aws_ec2_api_client import AwsEc2Client
from domain.repositories import CMLWorkerRepository
import asyncio

class WorkerMetricsCollector(RxAsyncSubject):
    """
    Reactive metrics collector for a single CML Worker.

    Polls AWS EC2 and CloudWatch APIs at regular intervals to:
    - Sync worker status (running, stopped, etc.)
    - Collect CPU/memory utilization
    - Check instance health status
    - Detect configuration drift
    """

    def __init__(
        self,
        worker_id: str,
        aws_ec2_client: AwsEc2Client,
        worker_repository: CMLWorkerRepository,
        poll_interval_seconds: int = 300,  # 5 minutes
    ):
        super().__init__()
        self.worker_id = worker_id
        self.aws_ec2_client = aws_ec2_client
        self.worker_repository = worker_repository
        self.poll_interval = poll_interval_seconds
        self._running = False
        self._task = None

    async def start_async(self) -> None:
        """Start the metrics collection loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info(f"Started metrics collection for worker {self.worker_id}")

    async def stop_async(self) -> None:
        """Stop the metrics collection loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped metrics collection for worker {self.worker_id}")

    async def _collect_loop(self) -> None:
        """Main collection loop - runs periodically."""
        while self._running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error collecting metrics for {self.worker_id}: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _collect_metrics(self) -> None:
        """Collect metrics for this worker."""
        worker = await self.worker_repository.get_by_id_async(self.worker_id)
        if not worker:
            logger.warning(f"Worker {self.worker_id} not found, stopping collector")
            await self.stop_async()
            return

        # Skip if worker is terminated
        if worker.state.status == CMLWorkerStatus.TERMINATED:
            await self.stop_async()
            return

        with tracer.start_as_current_span("collect_worker_metrics") as span:
            span.set_attribute("worker.id", self.worker_id)
            span.set_attribute("worker.aws_instance_id", worker.state.aws_instance_id)

            # 1. Sync EC2 instance status
            status_checks = self.aws_ec2_client.get_instance_status_checks(
                aws_region=AwsRegion(worker.state.aws_region),
                instance_id=worker.state.aws_instance_id,
            )

            # 2. Map EC2 state to worker status
            ec2_state = status_checks["instance_state"]
            new_status = self._map_ec2_state_to_worker_status(ec2_state)

            if new_status != worker.state.status:
                worker.update_status(new_status)
                logger.info(f"Worker {self.worker_id} status: {worker.state.status} → {new_status}")

            # 3. Collect CloudWatch metrics (if running)
            if new_status == CMLWorkerStatus.RUNNING:
                metrics = self.aws_ec2_client.get_instance_resources_utilization(
                    aws_region=AwsRegion(worker.state.aws_region),
                    instance_id=worker.state.aws_instance_id,
                    relative_start_time=Ec2InstanceResourcesUtilizationRelativeStartTime.LAST_5_MINUTES,
                )

                if metrics:
                    worker.update_telemetry(
                        cpu_utilization=float(metrics.avg_cpu_utilization) if metrics.avg_cpu_utilization != "unknown" else None,
                        memory_utilization=float(metrics.avg_memory_utilization) if metrics.avg_memory_utilization != "unknown" else None,
                        last_activity_at=datetime.now(timezone.utc),
                    )

            # 4. Save worker (publishes domain events)
            await self.worker_repository.update_async(worker)

            # 5. Emit metrics to observers
            await self.on_next_async({
                "worker_id": self.worker_id,
                "status": new_status.value,
                "status_checks": status_checks,
                "metrics": metrics if new_status == CMLWorkerStatus.RUNNING else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
```

---

### 2. WorkerNotificationHandler (Application Service)

**Type**: `Rx.Observer`
**Responsibility**: React to worker domain events
**Lifecycle**: Always active, filters events by type

```python
# src/application/services/worker_notification_handler.py

from neuroglia.reactive import RxAsyncObserver
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from domain.events.cml_worker import (
    CMLWorkerCreatedDomainEvent,
    CMLWorkerImportedDomainEvent,
    CMLWorkerStatusChangedDomainEvent,
    CMLWorkerTerminatedDomainEvent,
)

class WorkerNotificationHandler(RxAsyncObserver):
    """
    Reactive notification handler for CML Worker events.

    Subscribes to domain events and:
    - Sends alerts for critical status changes
    - Triggers webhooks for integration
    - Logs important lifecycle events
    - Initiates remediation workflows
    """

    def __init__(
        self,
        cloud_event_bus: CloudEventBus,
        monitoring_scheduler: 'WorkerMonitoringScheduler',
        settings: Settings,
    ):
        super().__init__()
        self.cloud_event_bus = cloud_event_bus
        self.monitoring_scheduler = monitoring_scheduler
        self.settings = settings

    async def on_next_async(self, event: Any) -> None:
        """Handle incoming domain events."""
        try:
            if isinstance(event, (CMLWorkerCreatedDomainEvent, CMLWorkerImportedDomainEvent)):
                await self._handle_worker_registered(event)
            elif isinstance(event, CMLWorkerStatusChangedDomainEvent):
                await self._handle_status_changed(event)
            elif isinstance(event, CMLWorkerTerminatedDomainEvent):
                await self._handle_worker_terminated(event)
        except Exception as e:
            logger.error(f"Error handling worker event {type(event).__name__}: {e}")

    async def _handle_worker_registered(
        self,
        event: CMLWorkerCreatedDomainEvent | CMLWorkerImportedDomainEvent
    ) -> None:
        """Handle new worker registration - START MONITORING."""
        worker_id = event.aggregate_id
        logger.info(f"🟢 Worker registered: {worker_id} ({event.name})")

        # Auto-start metrics collection
        await self.monitoring_scheduler.start_monitoring_worker_async(worker_id)

        # Send notification
        await self._send_notification(
            title=f"Worker Registered: {event.name}",
            message=f"Worker {worker_id} is now being monitored",
            severity="info",
            worker_id=worker_id,
        )

    async def _handle_status_changed(self, event: CMLWorkerStatusChangedDomainEvent) -> None:
        """Handle status changes - alert on critical transitions."""
        old_status = event.old_status
        new_status = event.new_status

        # Alert on critical transitions
        if new_status == "terminated":
            await self._send_notification(
                title=f"Worker Terminated",
                message=f"Worker {event.aggregate_id} has been terminated",
                severity="warning",
                worker_id=event.aggregate_id,
            )
        elif new_status == "stopped" and old_status == "running":
            await self._send_notification(
                title=f"Worker Stopped",
                message=f"Worker {event.aggregate_id} stopped unexpectedly",
                severity="warning",
                worker_id=event.aggregate_id,
            )

    async def _handle_worker_terminated(self, event: CMLWorkerTerminatedDomainEvent) -> None:
        """Handle worker termination - STOP MONITORING."""
        worker_id = event.aggregate_id
        logger.info(f"🔴 Worker terminated: {worker_id}")

        # Stop metrics collection
        await self.monitoring_scheduler.stop_monitoring_worker_async(worker_id)

    async def _send_notification(
        self,
        title: str,
        message: str,
        severity: str,
        worker_id: str,
    ) -> None:
        """Send notification (implement actual notification logic)."""
        # TODO: Integrate with notification service (email, Slack, webhooks)
        logger.info(f"📢 Notification [{severity}]: {title} - {message}")
```

---

### 3. WorkerMonitoringScheduler (Background Service)

**Type**: Background job manager
**Responsibility**: Manage collector lifecycles
**Implementation**: APScheduler + in-memory collector registry

```python
# src/application/services/worker_monitoring_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from typing import Dict

class WorkerMonitoringScheduler:
    """
    Manages the lifecycle of WorkerMetricsCollector instances.

    Responsibilities:
    - Start/stop collectors when workers are registered/terminated
    - Maintain registry of active collectors
    - Handle collector failures and restarts
    """

    def __init__(
        self,
        aws_ec2_client: AwsEc2Client,
        worker_repository: CMLWorkerRepository,
        settings: Settings,
    ):
        self.aws_ec2_client = aws_ec2_client
        self.worker_repository = worker_repository
        self.settings = settings

        # Registry: worker_id -> WorkerMetricsCollector
        self._collectors: Dict[str, WorkerMetricsCollector] = {}

        # Scheduler for periodic tasks
        self.scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            job_defaults={'coalesce': True, 'max_instances': 1}
        )

    async def initialize_async(self) -> None:
        """Initialize scheduler and start monitoring existing active workers."""
        logger.info("🚀 Initializing Worker Monitoring Scheduler...")

        # Start scheduler
        self.scheduler.start()

        # Auto-start monitoring for existing active workers
        active_workers = await self.worker_repository.get_active_workers_async()
        for worker in active_workers:
            await self.start_monitoring_worker_async(worker.id())

        logger.info(f"✅ Monitoring {len(self._collectors)} active workers")

    async def start_monitoring_worker_async(self, worker_id: str) -> None:
        """Start metrics collection for a worker."""
        if worker_id in self._collectors:
            logger.debug(f"Worker {worker_id} already being monitored")
            return

        collector = WorkerMetricsCollector(
            worker_id=worker_id,
            aws_ec2_client=self.aws_ec2_client,
            worker_repository=self.worker_repository,
            poll_interval_seconds=self.settings.worker_metrics_poll_interval,
        )

        await collector.start_async()
        self._collectors[worker_id] = collector
        logger.info(f"✅ Started monitoring worker {worker_id}")

    async def stop_monitoring_worker_async(self, worker_id: str) -> None:
        """Stop metrics collection for a worker."""
        collector = self._collectors.pop(worker_id, None)
        if collector:
            await collector.stop_async()
            logger.info(f"⏹️  Stopped monitoring worker {worker_id}")

    async def shutdown_async(self) -> None:
        """Gracefully shutdown all collectors."""
        logger.info("🛑 Shutting down Worker Monitoring Scheduler...")

        # Stop all collectors
        for worker_id, collector in list(self._collectors.items()):
            await collector.stop_async()

        # Shutdown scheduler
        self.scheduler.shutdown(wait=True)
        logger.info("✅ Worker Monitoring Scheduler shut down")
```

---

## Integration with Application Startup

### main.py Configuration

```python
# src/main.py

from application.services.worker_metrics_collector import WorkerMetricsCollector
from application.services.worker_notification_handler import WorkerNotificationHandler
from application.services.worker_monitoring_scheduler import WorkerMonitoringScheduler

async def configure_worker_monitoring(app: WebApplicationBuilder) -> None:
    """Configure reactive worker monitoring."""

    # 1. Create monitoring scheduler
    scheduler = WorkerMonitoringScheduler(
        aws_ec2_client=app.services.get(AwsEc2Client),
        worker_repository=app.services.get(CMLWorkerRepository),
        settings=app_settings,
    )

    # 2. Create notification handler
    notification_handler = WorkerNotificationHandler(
        cloud_event_bus=app.services.get(CloudEventBus),
        monitoring_scheduler=scheduler,
        settings=app_settings,
    )

    # 3. Subscribe notification handler to CloudEventBus
    cloud_event_bus = app.services.get(CloudEventBus)
    cloud_event_bus.subscribe(notification_handler)

    # 4. Initialize scheduler (starts monitoring existing workers)
    await scheduler.initialize_async()

    # 5. Register as singleton
    app.services.add_singleton(WorkerMonitoringScheduler, singleton=scheduler)
    app.services.add_singleton(WorkerNotificationHandler, singleton=notification_handler)

    logger.info("✅ Worker monitoring system configured")

# In main startup
builder = WebApplicationBuilder()
# ... existing configuration ...
await configure_worker_monitoring(builder)
```

---

## Domain Model: Are Watchers/Handlers Separate Aggregates?

### Analysis

**Question**: Should `WorkerMetricsCollector` and `WorkerNotificationHandler` be new entities/aggregates?

**Answer**: **NO** - They are **Application Services**, not Domain Entities.

### Justification

| Aspect | WorkerMetricsCollector | WorkerNotificationHandler | CMLWorker (Aggregate) |
|--------|------------------------|---------------------------|----------------------|
| **Layer** | Application | Application | Domain |
| **Role** | Orchestration | Orchestration | Business Logic |
| **Identity** | Transient (no ID) | Transient (no ID) | Has UUID |
| **Persistence** | No (in-memory) | No (stateless) | Yes (MongoDB) |
| **Lifecycle** | Managed by scheduler | Always running | Managed by repository |
| **Business Rules** | None | None | Worker status rules |

### Conclusion

- `CMLWorker` **remains the only aggregate** in the Worker bounded context
- Collectors and handlers are **infrastructure/application services** that operate on workers
- This aligns with DDD: **aggregates = business entities**, **services = orchestration**

---

## Evolution Path: Toward CML Resource Manager

### Current State (Phase 1)

```
CML Worker = Compute Resource (EC2 instance wrapper)
```

### Future State (Phase 2-3)

```
CML Resource Manager
├── Compute Layer (Workers)
│   ├── Worker Clusters
│   ├── Worker Pools
│   └── Worker Lifecycle Management
│
└── Workload Layer (CML Lablets)
    ├── Lablet Instances
    ├── Lablet Scheduler
    └── Lablet Health Monitoring
```

### Design Considerations for Future

1. **Separate Aggregates**:
   - `CMLWorkerCluster` (aggregate root for worker groups)
   - `CMLLablet` (aggregate root for CML workloads)
   - `WorkerPool` (aggregate for capacity management)

2. **Monitoring Evolution**:
   - Current: 1 collector per worker
   - Future: 1 collector per cluster + 1 per lablet

3. **Reactive Streams**:
   - Add `ClusterMetricsCollector`
   - Add `LabletHealthMonitor`
   - Add `WorkloadScheduler` (reactive to capacity events)

---

## Implementation Plan

### Phase 1: Core Monitoring (2-3 days)

- [ ] Create `WorkerMetricsCollector` service
- [ ] Create `WorkerNotificationHandler` service
- [ ] Create `WorkerMonitoringScheduler` service
- [ ] Integrate with `main.py` startup
- [ ] Add settings: `worker_metrics_poll_interval`, `worker_notification_webhooks`

### Phase 2: Testing & Observability (1-2 days)

- [ ] Unit tests for collectors and handlers
- [ ] Integration tests with mocked AWS
- [ ] Add OpenTelemetry metrics for monitoring
- [ ] Add health check endpoints

### Phase 3: Enhancement (1-2 days)

- [ ] Implement actual notification channels (email, Slack, webhooks)
- [ ] Add auto-remediation workflows (auto-restart failed workers)
- [ ] Add dashboard integration (expose metrics via API)

### Phase 4: Future Work (Future Sprints)

- [ ] Multi-region worker clustering
- [ ] Lablet scheduler integration
- [ ] Auto-scaling based on demand

---

## Configuration

### New Settings

```python
# src/application/settings.py

class Settings(BaseSettings):
    # ... existing settings ...

    # Worker Monitoring
    worker_metrics_poll_interval: int = Field(
        default=300,  # 5 minutes
        description="Interval in seconds for polling worker metrics from AWS"
    )

    worker_monitoring_enabled: bool = Field(
        default=True,
        description="Enable automatic worker monitoring on registration"
    )

    worker_notification_webhooks: list[str] = Field(
        default=[],
        description="Webhook URLs for worker event notifications"
    )

    worker_auto_remediation: bool = Field(
        default=False,
        description="Enable automatic remediation for worker failures"
    )
```

---

## Open Questions

1. **Persistence**: Should we persist collector state for crash recovery?
   - **Answer**: Not initially - collectors are ephemeral and will restart on app restart

2. **Scaling**: How does this work with multiple app instances?
   - **Answer**: Phase 1 = single instance only. Phase 2 = add distributed locking (Redis)

3. **Notification Channels**: Which notification services to integrate?
   - **Answer**: Start with logging, add webhooks in Phase 3

4. **Metrics Storage**: Where to store historical metrics?
   - **Answer**: Use existing MongoDB for worker telemetry, consider TimescaleDB for long-term storage

---

## References

- [Neuroglia Reactive Programming](https://bvandewe.github.io/pyneuro/patterns/reactive-programming/)
- [CQRS Pattern](../docs/architecture/cqrs-pattern.md)
- [Domain Events](../docs/architecture/domain-events.md)
- [CloudEvent Publishing](../notes/CLOUDEVENT_PUBLISHING_FIX.md)

---

## Conclusion

This architecture provides:
✅ **Reactive monitoring** triggered by worker registration
✅ **Separation of concerns** (metrics vs. notifications)
✅ **CQRS alignment** (read-heavy collectors, write-heavy handlers)
✅ **Scalability path** toward cluster/workload management
✅ **DDD compliance** (workers remain aggregates, services are orchestration)

**Next Step**: Review and approval → Implement Phase 1
