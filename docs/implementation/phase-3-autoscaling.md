# Phase 3: Auto-Scaling

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Duration** | Weeks 9-12 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |
| **Prerequisites** | [Phase 2](./phase-2-scheduling.md) complete |

---

## 1. Phase Objectives

- Implement Resource Controller with reconciliation loop
- Implement scale-up logic (trigger new workers)
- Implement scale-down logic with DRAINING state
- Implement Cloud Provider SPI (AWS adapter)
- Integrate worker template configuration
- Add scaling decision audit logging

---

## 2. Task Breakdown

### Week 9: Resource Controller Foundation

#### Task 3.1: Resource Controller Service (3 days)

**Files to Create:**
```
src/application/services/resource_controller.py
src/application/services/instance_reconciler.py
src/application/services/worker_reconciler.py
tests/unit/application/services/test_resource_controller.py
```

**Acceptance Criteria:**
- [ ] ResourceController with reconciliation loop (30s default)
- [ ] Leader election (same pattern as Scheduler)
- [ ] Delegate to specialized reconcilers
- [ ] Compare desired vs actual state
- [ ] Generate corrective actions
- [ ] Unit tests with mocks

**Reconciliation Loop:**
```python
class ResourceController:
    """Resource Controller with reconciliation loop."""
    
    async def _run_reconciliation_loop(self) -> None:
        """Main reconciliation loop - only runs when leader."""
        while self._running:
            if not self._leader_election.is_leader:
                await asyncio.sleep(1)
                continue
            
            try:
                # Reconcile instances
                instance_actions = await self._instance_reconciler.reconcile()
                
                # Reconcile workers
                worker_actions = await self._worker_reconciler.reconcile()
                
                # Execute actions
                await self._execute_actions(instance_actions + worker_actions)
                
            except Exception as e:
                logger.error(f"Reconciliation loop error: {e}")
            
            await asyncio.sleep(self._reconcile_interval)
```

**Dependencies:** Phase 2 Leader Election

**Effort Estimate:** 3 days

---

#### Task 3.2: Instance Reconciler (2 days)

**Files to Create:**
```
src/application/services/instance_reconciler.py
tests/unit/application/services/test_instance_reconciler.py
```

**Acceptance Criteria:**
- [ ] Detect instances stuck in INSTANTIATING (timeout)
- [ ] Detect instances past timeslot_end (auto-stop)
- [ ] Detect orphaned instances (worker terminated)
- [ ] Generate appropriate state transitions
- [ ] Unit tests for each scenario

**Reconciliation Logic:**
```python
class InstanceReconciler:
    """Reconciles LabletInstance desired vs actual state."""
    
    async def reconcile(self) -> list[ReconciliationAction]:
        actions = []
        
        # Check for stuck instantiating instances
        actions.extend(await self._check_stuck_instantiating())
        
        # Check for expired timeslots
        actions.extend(await self._check_expired_timeslots())
        
        # Check for orphaned instances (worker gone)
        actions.extend(await self._check_orphaned_instances())
        
        return actions
```

**Dependencies:** Task 3.1

**Effort Estimate:** 2 days

---

### Week 10: Scale-Up Logic

#### Task 3.3: Scale-Up Decision Engine (2 days)

**Files to Create:**
```
src/application/services/scale_up_engine.py
src/application/models/scale_action.py
tests/unit/application/services/test_scale_up_engine.py
```

**Acceptance Criteria:**
- [ ] Detect scheduled instances with no capacity
- [ ] Account for worker startup time (20 min)
- [ ] Select appropriate WorkerTemplate
- [ ] Check for pending workers (avoid over-provisioning)
- [ ] Generate ScaleUpAction with reason
- [ ] Unit tests with time scenarios

**Scale-Up Logic:**
```python
WORKER_BOOTUP_DELAY_MINUTES = 20


class ScaleUpEngine:
    """Determines when new workers are needed."""
    
    async def check_scale_up_needed(self) -> list[ScaleUpAction]:
        actions = []
        
        # Get scheduled instances approaching timeslot
        approaching = await self._get_approaching_instances(
            lead_time_minutes=WORKER_BOOTUP_DELAY_MINUTES + 15
        )
        
        for instance in approaching:
            if instance.state.worker_id is None:
                # Instance not yet placed - scheduler couldn't find capacity
                definition = await self._get_definition(instance.state.definition_id)
                template = self._select_template(definition)
                
                # Check if scale-up already in progress
                pending = await self._get_pending_workers(template.name)
                if not pending:
                    actions.append(ScaleUpAction(
                        template=template,
                        reason=f"Instance {instance.id()} approaching timeslot"
                    ))
        
        return actions
```

**Dependencies:** Task 3.1, Phase 1 Worker Templates

**Effort Estimate:** 2 days

---

#### Task 3.4: Cloud Provider SPI Interface (1 day)

**Files to Create:**
```
src/integration/services/cloud_provider_spi.py
src/integration/models/cloud_instance.py
```

**Acceptance Criteria:**
- [ ] Abstract interface for cloud operations
- [ ] Methods: create, start, stop, terminate, get_status, list
- [ ] Cloud-agnostic data models
- [ ] Designed for multi-cloud (future AWS, GCP, Azure)

**Interface Definition:**
```python
from abc import ABC, abstractmethod


class ICloudProviderAdapter(ABC):
    """Abstract interface for cloud provider operations."""
    
    @abstractmethod
    async def create_instance(
        self,
        template: WorkerTemplate,
        tags: dict[str, str]
    ) -> CloudInstance:
        """Create a new compute instance."""
        ...
    
    @abstractmethod
    async def start_instance(self, instance_id: str) -> None:
        """Start a stopped instance."""
        ...
    
    @abstractmethod
    async def stop_instance(self, instance_id: str) -> None:
        """Stop a running instance."""
        ...
    
    @abstractmethod
    async def terminate_instance(self, instance_id: str) -> None:
        """Terminate and delete an instance."""
        ...
    
    @abstractmethod
    async def get_instance_status(self, instance_id: str) -> CloudInstanceStatus:
        """Get current instance status."""
        ...
```

**Dependencies:** None (interface only)

**Effort Estimate:** 1 day

---

#### Task 3.5: AWS EC2 Adapter (2 days)

**Files to Create:**
```
src/integration/services/aws_ec2_adapter.py
tests/integration/test_aws_ec2_adapter.py
```

**Acceptance Criteria:**
- [ ] Implement ICloudProviderAdapter for AWS EC2
- [ ] Use existing AwsEc2Client as base
- [ ] Handle AMI selection based on pattern
- [ ] Apply tags from WorkerTemplate
- [ ] Return CloudInstance with AWS-specific details
- [ ] Integration tests with LocalStack or mocked boto3

**Implementation:**
```python
class AwsEc2Adapter(ICloudProviderAdapter):
    """AWS EC2 implementation of Cloud Provider SPI."""
    
    def __init__(self, ec2_client: AwsEc2Client, settings: Settings):
        self._ec2 = ec2_client
        self._settings = settings
    
    async def create_instance(
        self,
        template: WorkerTemplate,
        tags: dict[str, str]
    ) -> CloudInstance:
        # Find AMI matching pattern
        ami_id = await self._find_ami(template.ami_pattern)
        
        # Create EC2 instance
        response = await self._ec2.create_instance_async(
            ami_id=ami_id,
            instance_type=template.instance_type,
            tags={**template.tags, **tags, "ManagedBy": "ccm"}
        )
        
        return CloudInstance(
            id=response["InstanceId"],
            provider="aws",
            region=template.region,
            status=CloudInstanceStatus.PENDING
        )
```

**Dependencies:** Task 3.4, existing AwsEc2Client

**Effort Estimate:** 2 days

---

### Week 11: Scale-Down Logic

#### Task 3.6: Worker DRAINING State (2 days)

**Files to Modify:**
```
src/domain/entities/cml_worker.py (add DRAINING state)
src/domain/enums.py (update CMLWorkerStatus)
src/domain/events/cml_worker.py (add drain events)
```

**Files to Create:**
```
src/application/commands/drain_worker_command.py
src/application/commands/cancel_drain_command.py
```

**Acceptance Criteria:**
- [ ] Add DRAINING to CMLWorkerStatus enum
- [ ] Drain transition: RUNNING → DRAINING
- [ ] Cancel drain: DRAINING → RUNNING (admin action)
- [ ] Auto-stop: DRAINING → STOPPING (when empty)
- [ ] Domain events: WorkerDrainingStarted, WorkerDrainCancelled
- [ ] Unit tests for state transitions

**State Machine Update:**
```python
class CMLWorkerStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    DRAINING = "draining"  # NEW
    STOPPING = "stopping"
    STOPPED = "stopped"
    TERMINATED = "terminated"
```

**Dependencies:** Phase 1 CMLWorker

**Effort Estimate:** 2 days

---

#### Task 3.7: Scale-Down Decision Engine (2 days)

**Files to Create:**
```
src/application/services/scale_down_engine.py
tests/unit/application/services/test_scale_down_engine.py
```

**Acceptance Criteria:**
- [ ] Identify idle workers (no running instances)
- [ ] Check for approaching scheduled work
- [ ] Initiate DRAINING (not immediate stop)
- [ ] Prefer stopping over terminating
- [ ] Honor minimum warm capacity (configurable)
- [ ] Unit tests for each scenario

**Scale-Down Logic:**
```python
SCALE_DOWN_GRACE_PERIOD_MINUTES = 30


class ScaleDownEngine:
    """Determines when workers can be scaled down."""
    
    async def check_scale_down_candidates(self) -> list[ScaleDownAction]:
        actions = []
        
        # Check running workers
        for worker in await self._get_running_workers():
            if await self._has_active_instances(worker):
                continue
            
            if await self._has_scheduled_instances(worker):
                continue
            
            if await self._has_approaching_work(worker, SCALE_DOWN_GRACE_PERIOD_MINUTES):
                continue
            
            # Worker is idle - candidate for draining
            actions.append(ScaleDownAction(
                worker_id=worker.id(),
                action=ScaleDownActionType.DRAIN,
                reason="No running or scheduled instances"
            ))
        
        # Check draining workers ready to stop
        for worker in await self._get_draining_workers():
            if not await self._has_any_instances(worker):
                actions.append(ScaleDownAction(
                    worker_id=worker.id(),
                    action=ScaleDownActionType.STOP,
                    reason="Draining complete"
                ))
        
        return actions
```

**Dependencies:** Task 3.6

**Effort Estimate:** 2 days

---

#### Task 3.8: Drain Timeout Handler (1 day)

**Files to Create:**
```
src/application/services/drain_timeout_handler.py
tests/unit/application/services/test_drain_timeout_handler.py
```

**Acceptance Criteria:**
- [ ] Track drain start time per worker
- [ ] Use per-template drain timeout (from WorkerTemplate)
- [ ] Force-stop after timeout (even with running instances)
- [ ] Log warnings before force-stop
- [ ] Unit tests with time mocking

**Implementation:**
```python
class DrainTimeoutHandler:
    """Handles drain timeouts for workers."""
    
    async def check_timeouts(self) -> list[ScaleDownAction]:
        actions = []
        
        for worker in await self._get_draining_workers():
            template = await self._get_template(worker.state.template_name)
            timeout = timedelta(hours=template.drain_timeout_hours)
            
            if worker.state.drain_started_at + timeout < datetime.now(timezone.utc):
                logger.warning(f"Worker {worker.id()} drain timeout exceeded, force stopping")
                actions.append(ScaleDownAction(
                    worker_id=worker.id(),
                    action=ScaleDownActionType.FORCE_STOP,
                    reason="Drain timeout exceeded"
                ))
        
        return actions
```

**Dependencies:** Task 3.6

**Effort Estimate:** 1 day

---

### Week 12: Integration & Audit

#### Task 3.9: Scaling Audit Events (1 day)

**Files to Create:**
```
src/application/events/scaling_audit_events.py
src/application/services/scaling_audit_service.py
```

**Acceptance Criteria:**
- [ ] Log all scaling decisions with context
- [ ] Store in MongoDB for querying
- [ ] Include: action, reason, worker_id, template, timestamp
- [ ] Queryable via API
- [ ] Retention aligned with NFR-3.5.5 (3-12 months)

**Audit Event:**
```python
@dataclass
class ScalingAuditEvent:
    id: str
    timestamp: datetime
    action: str  # scale_up, scale_down, drain, cancel_drain
    worker_id: str | None
    worker_template: str | None
    reason: str
    triggered_by: str  # system, admin, api
    context: dict  # Additional context
```

**Dependencies:** Task 3.3, 3.7

**Effort Estimate:** 1 day

---

#### Task 3.10: Internal Controller Endpoints (1 day)

**Files to Create:**
```
src/api/controllers/internal_controller_controller.py
src/application/commands/scale_up_worker_command.py
src/application/commands/scale_down_worker_command.py
```

**Acceptance Criteria:**
- [ ] POST /api/internal/workers/scale-up
- [ ] POST /api/internal/workers/{id}/drain
- [ ] POST /api/internal/workers/{id}/cancel-drain
- [ ] POST /api/internal/workers/{id}/stop
- [ ] Internal endpoints secured
- [ ] Integration tests

**Dependencies:** Tasks 3.3, 3.6, 3.7

**Effort Estimate:** 1 day

---

#### Task 3.11: Resource Controller Startup (1 day)

**Files to Modify:**
```
src/main.py (register controller startup)
```

**Files to Create:**
```
src/application/jobs/resource_controller_startup_job.py
```

**Acceptance Criteria:**
- [ ] Controller starts on application startup (if enabled)
- [ ] Graceful shutdown on termination
- [ ] Configuration via settings
- [ ] Logging of controller lifecycle

**Dependencies:** Task 3.1

**Effort Estimate:** 1 day

---

#### Task 3.12: Auto-Scaling Integration Tests (2 days)

**Files to Create:**
```
tests/integration/test_scale_up_e2e.py
tests/integration/test_scale_down_e2e.py
tests/integration/test_draining_e2e.py
```

**Acceptance Criteria:**
- [ ] End-to-end scale-up test (no capacity → new worker)
- [ ] End-to-end scale-down test (idle → drain → stop)
- [ ] Drain timeout test
- [ ] Admin cancel drain test
- [ ] Leader election failover for Controller
- [ ] All tests pass in CI

**Dependencies:** All Phase 3 tasks

**Effort Estimate:** 2 days

---

## 3. Dependencies Graph

```
Week 9                  Week 10                 Week 11                 Week 12
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 3.1│──────────▶│ Task 3.3│            │ Task 3.6│──────────▶│ Task 3.9│
│ Resource│            │ Scale-Up│            │ DRAINING│            │ Audit   │
│ Ctrl    │            │ Engine  │            │ State   │            │ Events  │
└────┬────┘            └────┬────┘            └────┬────┘            └─────────┘
     │                      │                      │                      │
     ▼                      │                      ▼                      │
┌─────────┐            ┌────┴────┐            ┌─────────┐            ┌─────────┐
│ Task 3.2│            │ Task 3.4│            │ Task 3.7│            │Task 3.10│
│ Instance│            │ Cloud   │            │Scale-Dwn│            │ Internal│
│ Reconc  │            │ SPI     │            │ Engine  │            │ Endpts  │
└─────────┘            └────┬────┘            └────┬────┘            └────┬────┘
                            │                      │                      │
                            ▼                      ▼                      │
                       ┌─────────┐            ┌─────────┐            ┌────┴────┐
                       │ Task 3.5│            │ Task 3.8│            │Task 3.11│
                       │ AWS EC2 │            │ Drain   │            │ Startup │
                       │ Adapter │            │ Timeout │            │ Job     │
                       └─────────┘            └─────────┘            └────┬────┘
                                                                          │
                                                                     ┌────┴────┐
                                                                     │Task 3.12│
                                                                     │ Integ   │
                                                                     │ Tests   │
                                                                     └─────────┘
```

---

## 4. Test Coverage Requirements

| Component | Unit Tests | Integration Tests | Target Coverage |
|-----------|------------|-------------------|-----------------|
| Resource Controller | Yes | Yes | ≥85% |
| Instance Reconciler | Yes | - | ≥90% |
| Scale-Up Engine | Yes | Yes | ≥90% |
| Scale-Down Engine | Yes | Yes | ≥90% |
| AWS EC2 Adapter | Yes | Yes (mocked) | ≥85% |
| DRAINING State | Yes | Yes | ≥95% |
| Drain Timeout | Yes | - | ≥90% |

---

## 5. Phase 3 Acceptance Criteria

### Functional
- [ ] Scale-up triggers when no worker has capacity
- [ ] New workers created via AWS EC2
- [ ] Idle workers transition to DRAINING
- [ ] DRAINING workers accept no new instances
- [ ] DRAINING workers stop when empty
- [ ] Admin can cancel draining
- [ ] Drain timeout enforced
- [ ] All scaling decisions audited

### Non-Functional
- [ ] Scale-up decision time < 5s
- [ ] Worker creation initiated within 1 min of decision
- [ ] No over-provisioning (check pending workers)
- [ ] Minimum warm capacity maintained

### Documentation
- [ ] Auto-scaling behavior documented
- [ ] DRAINING state documented
- [ ] Audit query API documented
- [ ] Operational runbook for manual scaling

---

## 6. Risks & Mitigations (Phase 3 Specific)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| AWS API rate limits | Medium | Low | Implement backoff, request batching |
| Over-provisioning | High | Medium | Check pending workers before scale-up |
| Premature scale-down | High | Low | Grace period, approaching work check |
| Orphaned workers (controller failure) | Medium | Low | Reconciliation on startup |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
