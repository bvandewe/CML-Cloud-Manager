# Resource-Oriented Architecture (ROA) Migration Plan

## 📋 Executive Summary

This document outlines the migration from the current **imperative command-based architecture** to a **hybrid architecture** supporting both imperative (CQRS commands) and declarative (ROA resource management) APIs for CML Worker lifecycle management.

**Goal**: Enable users to manage CML Workers either imperatively (via commands) or declaratively (via resource specifications), similar to Kubernetes' dual API model.

---

## 🔍 Current Architecture Analysis

### Current State: Imperative CQRS Architecture

```
User → REST API → CQRS Command → Domain Aggregate → Repository → Events
                                      ↓
                                   Business Logic
                                      ↓
                                   AWS EC2 API
```

#### Components

1. **REST API Controllers** (`api/controllers/cml_worker_controller.py`)
   - Imperative endpoints: POST /create, POST /start, POST /stop, POST /terminate
   - CRUD operations: GET /workers, GET /workers/{id}

2. **CQRS Commands** (`application/commands/`)
   - `CreateCMLWorkerCommand` - Provision new EC2 instance
   - `ImportCMLWorkerCommand` - Import existing instance
   - `StartCMLWorkerCommand` - Start stopped instance
   - `StopCMLWorkerCommand` - Stop running instance
   - `TerminateCMLWorkerCommand` - Terminate and cleanup
   - `UpdateCMLWorkerStatusCommand` - Sync status from AWS
   - `UpdateCMLWorkerTagsCommand` - Update AWS tags

3. **Domain Aggregate** (`domain/entities/cml_worker.py`)
   - `CMLWorker` - AggregateRoot with AggregateState pattern
   - Rich domain model with business logic
   - Emits 9 types of domain events

4. **Repository** (`integration/repositories/motor_cml_worker_repository.py`)
   - MongoDB persistence via Neuroglia MotorRepository
   - Event publishing via Mediator

5. **Monitoring System** (Recently refactored)
   - `WorkerMetricsCollectionJob` - APScheduler background job
   - `WorkerNotificationHandler` - Reactive metrics observer
   - `WorkerMonitoringScheduler` - Job lifecycle manager

#### Domain Events Published

- `CMLWorkerCreatedDomainEvent`
- `CMLWorkerStatusUpdatedDomainEvent`
- `CMLServiceStatusUpdatedDomainEvent`
- `CMLWorkerInstanceAssignedDomainEvent`
- `CMLWorkerLicenseUpdatedDomainEvent`
- `CMLWorkerTelemetryUpdatedDomainEvent`
- `CMLWorkerEndpointUpdatedDomainEvent`
- `CMLWorkerImportedDomainEvent`
- `CMLWorkerTerminatedDomainEvent`

### Strengths ✅

1. **Clean separation of concerns** - CQRS, DDD, Repository patterns
2. **Rich domain model** - CMLWorker aggregate with strong business logic
3. **Event-driven** - Comprehensive domain events for integrations
4. **Well-tested** - Existing test suite for commands/queries
5. **Observability** - OpenTelemetry tracing throughout
6. **Background jobs** - APScheduler integration for metrics collection

### Gaps for ROA ⚠️

1. **No declarative API** - Users must explicitly call commands for each action
2. **No desired state management** - No concept of "spec" vs "status"
3. **No continuous reconciliation** - Manual sync via commands only
4. **No drift detection** - No automatic correction of infrastructure divergence
5. **No resource watching** - Polling-based monitoring, not event-driven resource changes
6. **No controller pattern** - Business logic tightly coupled to commands
7. **No eventual consistency** - Commands fail immediately, no retry/reconciliation
8. **Manual lifecycle** - Users must manage state transitions explicitly

---

## 🎯 Target Architecture: Hybrid ROA + CQRS

### Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interfaces                          │
├──────────────────────────┬──────────────────────────────────────┤
│   Imperative API         │        Declarative API               │
│   (Commands)             │        (Resources)                   │
├──────────────────────────┼──────────────────────────────────────┤
│ POST /workers/create     │ PUT /resources/workers/{id}          │
│ POST /workers/{id}/start │ - Submit desired state (spec)        │
│ POST /workers/{id}/stop  │ - System reconciles to spec          │
│ DELETE /workers/{id}     │ - Automatic drift correction         │
└──────────────────────────┴──────────────────────────────────────┘
                    ↓                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                      Application Layer                           │
├──────────────────────────┬──────────────────────────────────────┤
│   Command Handlers       │    Resource Controller               │
│   - Immediate execution  │    - Event-driven reactions          │
│   - Synchronous response │    - State transition logic          │
└──────────────────────────┴──────────────────────────────────────┘
                    ↓                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                      Domain Layer                                │
│                                                                  │
│   CMLWorker Aggregate (unchanged)                                │
│   - Business logic and validation                                │
│   - Domain events                                                │
└──────────────────────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────────────────────┐
│                Infrastructure Layer                              │
├─────────────────┬──────────────────┬──────────────────────────┤
│ Aggregate Repo  │ Resource Storage │ AWS EC2 Client           │
│ (MongoDB)       │ (MongoDB)        │ (boto3)                  │
└─────────────────┴──────────────────┴──────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────────────────────┐
│                      ROA Components                              │
├──────────────────────────┬──────────────────────────────────────┤
│   Watcher                │    Reconciler                        │
│   - Poll for changes     │    - Periodic consistency checks     │
│   - Emit change events   │    - Timeout handling                │
│   - Notify controller    │    - Drift detection                 │
└──────────────────────────┴──────────────────────────────────────┘
```

### Key Components to Add

#### 1. Resource Definition Layer

**File**: `src/domain/resources/cml_worker_resource.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class CMLWorkerResourceMetadata:
    """Kubernetes-style resource metadata."""
    name: str
    uid: str
    resource_version: str
    creation_timestamp: datetime
    labels: Dict[str, str] = None
    annotations: Dict[str, str] = None

@dataclass
class CMLWorkerResourceSpec:
    """Desired state for CML Worker."""
    # Infrastructure
    aws_region: str
    instance_type: str
    ami_id: Optional[str] = None
    ami_name: Optional[str] = None

    # Desired runtime state
    power_state: str = "running"  # running, stopped

    # CML configuration
    cml_version: Optional[str] = None
    license_token: Optional[str] = None

    # Monitoring
    enable_monitoring: bool = True
    metrics_interval: int = 300

@dataclass
class CMLWorkerResourceStatus:
    """Current/observed state of CML Worker."""
    # Phase indicates overall resource state
    phase: str  # Pending, Provisioning, Ready, Failed, Terminating, Terminated

    # Actual infrastructure state
    aws_instance_id: Optional[str] = None
    instance_state: Optional[str] = None  # EC2 state
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None

    # CML service state
    service_status: str = "unknown"  # available, unavailable, unknown
    https_endpoint: Optional[str] = None
    license_status: str = "unregistered"

    # Monitoring data
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    active_labs_count: int = 0
    last_activity_at: Optional[datetime] = None

    # Conditions for debugging
    conditions: list[Dict[str, Any]] = None

    # Timestamps
    last_reconcile_time: Optional[datetime] = None
    last_transition_time: Optional[datetime] = None

@dataclass
class CMLWorkerResource:
    """Complete resource definition following K8s pattern."""
    api_version: str = "cml.cisco.com/v1"
    kind: str = "CMLWorker"
    metadata: CMLWorkerResourceMetadata = None
    spec: CMLWorkerResourceSpec = None
    status: CMLWorkerResourceStatus = None
```

**Design Rationale**:

- **Separation of concerns**: `spec` (desired) vs `status` (observed)
- **Kubernetes compatibility**: Familiar API for DevOps users
- **GitOps ready**: Resources are declarative and version-controllable
- **Drift detection**: Compare spec vs status to detect manual changes

#### 2. Resource Storage Layer

**File**: `src/infrastructure/repositories/cml_worker_resource_repository.py`

```python
class CMLWorkerResourceRepository(MotorRepository[CMLWorkerResource, str]):
    """Repository for CML Worker resources."""

    async def list_resources(
        self,
        since_version: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> list[CMLWorkerResource]:
        """List resources, optionally filtered."""
        pass

    async def watch_resources(
        self,
        since_version: Optional[str] = None
    ) -> AsyncIterator[ResourceEvent]:
        """Stream resource changes."""
        pass

    async def update_status(
        self,
        resource_id: str,
        status: CMLWorkerResourceStatus
    ) -> CMLWorkerResource:
        """Update only the status subresource."""
        pass
```

**Design Rationale**:

- **Separate storage**: Resources stored independently from aggregates
- **Version tracking**: Resource versions for optimistic locking
- **Status updates**: Controllers update status without modifying spec
- **Watch support**: Enable efficient change notification

#### 3. Watcher Component

**File**: `src/application/services/cml_worker_watcher.py`

```python
class CMLWorkerWatcher:
    """Watches for CML Worker resource changes."""

    def __init__(
        self,
        resource_repository: CMLWorkerResourceRepository,
        poll_interval: float = 5.0
    ):
        self._repository = resource_repository
        self._poll_interval = poll_interval
        self._last_resource_version = None
        self._event_handlers = []

    def add_event_handler(
        self,
        handler: Callable[[CMLWorkerResource, str], Awaitable[None]]
    ):
        """Register a handler for resource events.

        Args:
            handler: Async function(resource, event_type) -> None
                event_type: ADDED, MODIFIED, DELETED
        """
        self._event_handlers.append(handler)

    async def start_watching(self):
        """Start watching for resource changes."""
        while self._is_running:
            try:
                # Get changes since last known version
                resources = await self._repository.list_resources(
                    since_version=self._last_resource_version
                )

                for resource in resources:
                    event_type = self._determine_event_type(resource)

                    # Notify all handlers
                    for handler in self._event_handlers:
                        await handler(resource, event_type)

                    # Update version
                    self._last_resource_version = resource.metadata.resource_version

                await asyncio.sleep(self._poll_interval)

            except Exception as e:
                logger.error(f"Error in watcher loop: {e}")
                await asyncio.sleep(self._poll_interval)
```

**Design Rationale**:

- **Event-driven**: Notifies controllers of changes immediately (within poll interval)
- **Efficient polling**: Only fetches changes since last version
- **Observer pattern**: Multiple controllers can subscribe
- **Resilient**: Errors don't stop watching

#### 4. Controller Component

**File**: `src/application/services/cml_worker_controller.py`

```python
class CMLWorkerController:
    """Responds to CML Worker resource changes with business logic."""

    def __init__(
        self,
        resource_repository: CMLWorkerResourceRepository,
        worker_repository: CMLWorkerRepository,
        aws_client: AwsEc2Client,
        mediator: Mediator
    ):
        self._resource_repo = resource_repository
        self._worker_repo = worker_repository
        self._aws_client = aws_client
        self._mediator = mediator

    async def handle_resource_event(
        self,
        resource: CMLWorkerResource,
        event_type: str
    ):
        """Handle a resource change event."""

        logger.info(
            f"🎮 Controller processing: {resource.metadata.name} "
            f"({event_type}): phase={resource.status.phase}"
        )

        # State machine based on current phase
        if resource.status.phase == "Pending":
            await self._handle_pending(resource)

        elif resource.status.phase == "Provisioning":
            await self._handle_provisioning(resource)

        elif resource.status.phase == "Ready":
            await self._handle_ready(resource)

        elif resource.status.phase == "Failed":
            await self._handle_failed(resource)

        elif resource.status.phase == "Terminating":
            await self._handle_terminating(resource)

    async def _handle_pending(self, resource: CMLWorkerResource):
        """Handle new resource in Pending state."""
        try:
            # Transition to Provisioning
            resource.status.phase = "Provisioning"
            resource.status.last_transition_time = datetime.now(timezone.utc)

            # Use existing CreateCMLWorkerCommand
            command = CreateCMLWorkerCommand(
                name=resource.metadata.name,
                aws_region=AwsRegion(resource.spec.aws_region),
                instance_type=resource.spec.instance_type,
                ami_id=resource.spec.ami_id,
                ami_name=resource.spec.ami_name,
                cml_version=resource.spec.cml_version,
                created_by="controller"
            )

            result = await self._mediator.send_async(command)

            if result.is_success:
                # Update status with instance details
                instance_data = result.content
                resource.status.aws_instance_id = instance_data["aws_instance_id"]
                resource.status.instance_state = instance_data["instance_state"]
                resource.status.public_ip = instance_data.get("public_ip")
                resource.status.private_ip = instance_data.get("private_ip")
            else:
                raise Exception(result.errors)

            await self._resource_repo.update_status(
                resource.metadata.uid,
                resource.status
            )

        except Exception as e:
            logger.error(f"Failed to provision resource: {e}")
            await self._mark_failed(resource, str(e))

    async def _handle_ready(self, resource: CMLWorkerResource):
        """Handle resource in Ready state - check for spec changes."""

        # Check if desired power state matches actual state
        desired_power = resource.spec.power_state
        actual_state = resource.status.instance_state

        if desired_power == "stopped" and actual_state == "running":
            # User changed spec to request stop
            await self._stop_worker(resource)

        elif desired_power == "running" and actual_state == "stopped":
            # User changed spec to request start
            await self._start_worker(resource)

    async def _stop_worker(self, resource: CMLWorkerResource):
        """Stop a running worker."""
        command = StopCMLWorkerCommand(
            worker_id=resource.metadata.uid
        )
        await self._mediator.send_async(command)

    async def _start_worker(self, resource: CMLWorkerResource):
        """Start a stopped worker."""
        command = StartCMLWorkerCommand(
            worker_id=resource.metadata.uid
        )
        await self._mediator.send_async(command)
```

**Design Rationale**:

- **State machine**: Clear phases for resource lifecycle
- **Reuses commands**: Leverages existing CQRS commands for actions
- **Event-driven**: Reacts immediately to resource changes
- **Separation**: Controller orchestrates, commands execute
- **Observability**: Comprehensive logging at each transition

#### 5. Reconciler Component

**File**: `src/application/services/cml_worker_reconciler.py`

```python
class CMLWorkerReconciler:
    """Periodic reconciliation for consistency and safety."""

    def __init__(
        self,
        resource_repository: CMLWorkerResourceRepository,
        aws_client: AwsEc2Client,
        reconcile_interval: float = 30.0,
        timeout_threshold: int = 600  # 10 minutes
    ):
        self._resource_repo = resource_repository
        self._aws_client = aws_client
        self._reconcile_interval = reconcile_interval
        self._timeout_threshold = timeout_threshold

    async def start_reconciliation(self):
        """Start the reconciliation loop."""
        while self._is_running:
            try:
                await self._reconcile_all_resources()
                await asyncio.sleep(self._reconcile_interval)
            except Exception as e:
                logger.error(f"Reconciliation error: {e}")
                await asyncio.sleep(self._reconcile_interval)

    async def _reconcile_all_resources(self):
        """Reconcile all non-terminated resources."""
        resources = await self._resource_repo.list_resources()

        logger.info(f"🔄 Reconciling {len(resources)} resources")

        for resource in resources:
            if resource.status.phase not in ["Terminated"]:
                await self._reconcile_resource(resource)

    async def _reconcile_resource(self, resource: CMLWorkerResource):
        """Reconcile a single resource."""

        # 1. Timeout detection
        if await self._check_timeout(resource):
            return  # Timeout handler updated status

        # 2. Drift detection
        if await self._check_drift(resource):
            return  # Drift handler corrected state

        # 3. Status sync
        await self._sync_status(resource)

        # Update last reconcile time
        resource.status.last_reconcile_time = datetime.now(timezone.utc)
        await self._resource_repo.update_status(
            resource.metadata.uid,
            resource.status
        )

    async def _check_timeout(self, resource: CMLWorkerResource) -> bool:
        """Check if resource is stuck in a transitioning state."""

        if resource.status.phase != "Provisioning":
            return False

        transition_time = resource.status.last_transition_time
        if not transition_time:
            return False

        age = (datetime.now(timezone.utc) - transition_time).total_seconds()

        if age > self._timeout_threshold:
            logger.warning(
                f"⚠️ Resource {resource.metadata.name} stuck in "
                f"Provisioning for {age}s, marking as Failed"
            )

            resource.status.phase = "Failed"
            resource.status.conditions = resource.status.conditions or []
            resource.status.conditions.append({
                "type": "ProvisioningTimeout",
                "status": "True",
                "reason": "Timeout",
                "message": f"Provisioning exceeded {self._timeout_threshold}s timeout",
                "last_transition_time": datetime.now(timezone.utc).isoformat()
            })

            await self._resource_repo.update_status(
                resource.metadata.uid,
                resource.status
            )
            return True

        return False

    async def _check_drift(self, resource: CMLWorkerResource) -> bool:
        """Check if actual infrastructure differs from desired state."""

        if not resource.status.aws_instance_id:
            return False

        # Query actual AWS state
        try:
            actual_state = await self._aws_client.get_instance_status(
                aws_region=AwsRegion(resource.spec.aws_region),
                instance_id=resource.status.aws_instance_id
            )

            # Check if instance was manually terminated
            if actual_state.instance_state == "terminated":
                if resource.status.phase != "Terminated":
                    logger.warning(
                        f"⚠️ Drift detected: {resource.metadata.name} "
                        f"manually terminated outside system"
                    )

                    resource.status.phase = "Terminated"
                    resource.status.instance_state = "terminated"
                    resource.status.conditions = resource.status.conditions or []
                    resource.status.conditions.append({
                        "type": "DriftDetected",
                        "status": "True",
                        "reason": "ManualTermination",
                        "message": "Instance terminated outside resource controller",
                        "last_transition_time": datetime.now(timezone.utc).isoformat()
                    })

                    await self._resource_repo.update_status(
                        resource.metadata.uid,
                        resource.status
                    )
                    return True

            # Check power state drift
            desired_power = resource.spec.power_state
            actual_power = actual_state.instance_state

            if desired_power == "running" and actual_power == "stopped":
                logger.warning(
                    f"⚠️ Drift detected: {resource.metadata.name} "
                    f"manually stopped, restarting..."
                )
                # Trigger correction via command
                # (Controller will handle this via normal event flow)
                return False

        except Exception as e:
            logger.error(f"Failed to check drift for {resource.metadata.name}: {e}")

        return False
```

**Design Rationale**:

- **Safety net**: Catches timeouts and stuck states
- **Drift detection**: Discovers manual infrastructure changes
- **Periodic checks**: Independent of event-driven controller
- **Condition reporting**: Kubernetes-style conditions for debugging
- **Corrective actions**: Can trigger commands to fix drift

#### 6. Orchestrator/Scheduler

**File**: `src/application/services/cml_worker_resource_manager.py`

```python
class CMLWorkerResourceManager:
    """Orchestrates ROA components lifecycle."""

    def __init__(
        self,
        watcher: CMLWorkerWatcher,
        controller: CMLWorkerController,
        reconciler: CMLWorkerReconciler
    ):
        self._watcher = watcher
        self._controller = controller
        self._reconciler = reconciler
        self._tasks = []

    async def start_async(self):
        """Start all ROA components concurrently."""
        logger.info("🚀 Starting CML Worker Resource Manager...")

        # Subscribe controller to watcher events
        self._watcher.add_event_handler(
            self._controller.handle_resource_event
        )

        # Start components concurrently
        self._tasks = [
            asyncio.create_task(self._watcher.start_watching()),
            asyncio.create_task(self._reconciler.start_reconciliation())
        ]

        logger.info("✅ Resource Manager started")

    async def stop_async(self):
        """Stop all ROA components."""
        logger.info("🛑 Stopping CML Worker Resource Manager...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for graceful shutdown
        await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("✅ Resource Manager stopped")
```

---

## 🔄 Migration Strategy

### Phase 1: APScheduler Improvements (CURRENT)

✅ Completed base refactoring
⏳ Implement recommendations:

1. **Job Serialization Fix**
   - Store only worker_id in job data
   - Re-inject dependencies on deserialization
   - Use service provider for DI

2. **Job Stop Implementation**
   - Add BackgroundTaskScheduler reference to WorkerMonitoringScheduler
   - Call `scheduler.stop_task(job_id)` in `stop_monitoring_worker_async()`

3. **Redis Job Store**
   - Add configuration to settings
   - Test distributed job persistence

4. **Job State Validation**
   - Add worker status check in `WorkerMetricsCollectionJob.run_every()`
   - Raise exception to signal job termination

### Phase 2: ROA Foundation (Next)

1. **Resource Definition**
   - Create `CMLWorkerResource` dataclass
   - Add resource repository
   - Implement MongoDB storage with versioning

2. **Basic Watcher**
   - Simple polling watcher
   - Event notification to controller
   - Version tracking

3. **Basic Controller**
   - Handle Pending → Provisioning transition
   - Reuse existing CreateCMLWorkerCommand
   - Update resource status

4. **Basic Reconciler**
   - Timeout detection for stuck Provisioning
   - Mark as Failed after threshold
   - Periodic status sync

### Phase 3: Declarative API (Final)

1. **REST API for Resources**
   - `PUT /resources/cmlworkers/{name}` - Apply resource
   - `GET /resources/cmlworkers/{name}` - Get resource
   - `GET /resources/cmlworkers` - List resources
   - `DELETE /resources/cmlworkers/{name}` - Delete resource

2. **Complete State Machine**
   - Handle all phase transitions
   - Implement power state changes
   - License management

3. **Advanced Drift Detection**
   - Detect manual AWS changes
   - Automatic correction
   - Condition reporting

4. **GitOps Integration**
   - YAML/JSON resource definitions
   - CI/CD pipeline support
   - Kubectl-style CLI

---

## 🎯 Benefits of ROA Migration

### For Users

1. **Declarative Management**
   - Define desired state, system maintains it
   - No need to orchestrate state transitions manually
   - GitOps-friendly

2. **Automatic Recovery**
   - System detects and corrects drift
   - Handles timeouts and failures automatically
   - Eventual consistency guarantees

3. **Dual API Support**
   - Use imperative API for immediate actions
   - Use declarative API for long-lived resources
   - Choose the right tool for the job

### For Developers

1. **Separation of Concerns**
   - Controller handles business logic
   - Watcher handles change detection
   - Reconciler handles safety/consistency

2. **Reusability**
   - ROA components reuse existing commands
   - No duplication of business logic
   - Commands remain independently usable

3. **Testability**
   - Each component testable in isolation
   - Mock resource events for controller tests
   - Time-travel reconciler tests

4. **Observability**
   - Clear phase transitions in logs
   - Condition reporting for debugging
   - Resource version tracking

---

## 🔧 Implementation Recommendations

### 1. Keep Aggregates Separate from Resources

**DO NOT** merge CMLWorker aggregate with CMLWorkerResource.

**Rationale**:

- **Aggregate** = Domain model with business logic and event sourcing
- **Resource** = Infrastructure specification (spec) and status
- **Relationship**: Controller uses aggregate (via commands) to implement resource spec

```
Resource (what user wants)
   ↓
Controller (orchestrates)
   ↓
Command (executes action)
   ↓
Aggregate (business logic)
   ↓
Events (what happened)
```

### 2. Use Commands from Controller

Controller should **not** directly manipulate aggregates. Instead:

- Controller detects resource changes (via Watcher)
- Controller sends appropriate Command via Mediator
- Command handler contains business logic
- Command handler updates aggregate
- Aggregate publishes domain events

This maintains clean separation and reusability.

### 3. Resource Storage Design

Store resources separately from aggregates:

```
MongoDB Collections:
- cml_workers (aggregates) - Current collection
- cml_worker_resources (ROA resources) - New collection

Each resource has:
- metadata.uid (links to aggregate id)
- metadata.resource_version (for optimistic locking)
- spec (desired state)
- status (observed state)
```

### 4. Version Management

Implement resource versioning for:

- **Optimistic locking**: Prevent conflicting updates
- **Change detection**: Watcher tracks changes since last version
- **Audit trail**: Historical resource states

```python
resource.metadata.resource_version = str(version_counter)
```

### 5. Event Integration

Connect ROA events with existing domain events:

```python
# Domain event → Update resource status
@integration_event_handler(CMLWorkerStatusUpdatedDomainEvent)
async def on_worker_status_updated(event: CMLWorkerStatusUpdatedDomainEvent):
    # Update corresponding resource status
    resource = await resource_repo.get_by_id_async(event.aggregate_id)
    resource.status.instance_state = event.new_status.value
    await resource_repo.update_status(event.aggregate_id, resource.status)
```

### 6. Gradual Migration

**Phase 1**: Implement ROA alongside existing API (no breaking changes)
**Phase 2**: Encourage adoption with documentation and examples
**Phase 3**: (Optional) Deprecate some imperative endpoints if desired

Users can mix both approaches:

- Use declarative API for long-lived infrastructure
- Use imperative API for immediate one-off actions

---

## 📊 Success Metrics

1. **Functional**
   - ✅ Users can submit resource specs
   - ✅ System automatically provisions infrastructure
   - ✅ System detects and corrects drift
   - ✅ System handles timeouts gracefully

2. **Performance**
   - Watcher latency < 10 seconds (with 5s poll interval)
   - Reconciler runs every 30 seconds without performance issues
   - No impact on existing imperative API response times

3. **Reliability**
   - 99.9% eventual consistency (resource reaches desired state)
   - Zero data loss on resource updates
   - Automatic recovery from transient failures

---

## 🚧 Neuroglia Framework Enhancement Proposals

Based on this migration, consider PRs to Neuroglia for:

### 1. ROA Base Classes

```python
# In neuroglia.roa.abstractions

@dataclass
class ResourceMetadata:
    """Standard metadata for all resources."""
    name: str
    uid: str
    resource_version: str
    creation_timestamp: datetime
    labels: Dict[str, str] = None
    annotations: Dict[str, str] = None

class Resource(ABC, Generic[TSpec, TStatus]):
    """Base class for all resources."""
    api_version: str
    kind: str
    metadata: ResourceMetadata
    spec: TSpec
    status: TStatus

class ResourceRepository(ABC, Generic[TResource]):
    """Base repository for resource storage."""

    @abstractmethod
    async def list_resources(
        self,
        since_version: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> list[TResource]:
        pass

    @abstractmethod
    async def update_status(
        self,
        resource_id: str,
        status: Any
    ) -> TResource:
        pass

class Watcher(ABC, Generic[TResource]):
    """Base watcher implementation."""

    @abstractmethod
    async def start_watching(self):
        pass

    def add_event_handler(
        self,
        handler: Callable[[TResource, str], Awaitable[None]]
    ):
        pass

class Controller(ABC, Generic[TResource]):
    """Base controller implementation."""

    @abstractmethod
    async def handle_resource_event(
        self,
        resource: TResource,
        event_type: str
    ):
        pass

class Reconciler(ABC, Generic[TResource]):
    """Base reconciler implementation."""

    @abstractmethod
    async def start_reconciliation(self):
        pass

    @abstractmethod
    async def _reconcile_resource(self, resource: TResource):
        pass
```

### 2. Resource Versioning Support

Add to `MotorRepository`:

```python
async def list_since_version(
    self,
    since_version: Optional[str] = None
) -> list[TEntity]:
    """List entities changed since resource version."""
    query = {}
    if since_version:
        query["_resource_version"] = {"$gt": since_version}
    ...
```

### 3. Watch Support

Add streaming support:

```python
async def watch_changes(
    self,
    since_version: Optional[str] = None
) -> AsyncIterator[tuple[TEntity, str]]:
    """Stream entity changes."""
    # Using MongoDB change streams or polling
    ...
```

---

## 📚 Documentation Needs

1. **User Guide**: "Managing CML Workers - Imperative vs Declarative"
2. **Migration Guide**: "Transitioning from Commands to Resources"
3. **ROA Architecture**: "Understanding the Resource-Oriented Architecture"
4. **API Reference**: Resource schema, endpoints, examples
5. **Troubleshooting**: Debugging stuck resources, understanding phases/conditions

---

## 🎯 Next Steps

1. ✅ **Complete APScheduler recommendations** (this PR)
2. 🔄 **Create Resource layer** (next PR)
3. 🔄 **Implement Watcher** (subsequent PR)
4. 🔄 **Implement Controller** (subsequent PR)
5. 🔄 **Implement Reconciler** (subsequent PR)
6. 🔄 **Add Declarative API** (final PR)

Each phase is independently testable and deployable without breaking existing functionality.

---

## 🤝 Collaboration

This migration opens opportunities for:

- **Neuroglia Framework** contributions (ROA base classes)
- **Community templates** (resource definitions for common patterns)
- **GitOps tooling** (kubectl-style CLI for CML workers)
- **Operator patterns** (more complex orchestration scenarios)

---

**Status**: Phase 1 (APScheduler improvements) in progress
**Next**: Phase 2 (ROA Foundation) planning
**Timeline**: Iterative, with deployable milestones
