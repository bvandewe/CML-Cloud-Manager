# Phase 2: Scheduling

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Duration** | Weeks 5-8 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |
| **Prerequisites** | [Phase 1](./phase-1-foundation.md) complete |

---

## 1. Phase Objectives

- Implement Scheduler Service with leader election
- Implement placement algorithm (bin-packing)
- Implement timeslot management and monitoring
- Implement Lab YAML rewriting with port mapping
- Implement instantiation flow (import → start)
- Add SSE updates for instance state changes

---

## 2. Task Breakdown

### Week 5: Scheduler Service Foundation

#### Task 2.1: Scheduler Leader Election (2 days)

**Files to Create:**

```
src/application/services/leader_election_service.py
tests/integration/test_leader_election.py
```

**Acceptance Criteria:**

- [ ] Leader election using etcd leases (15s TTL)
- [ ] Campaign for leadership on startup
- [ ] Maintain leadership via lease renewal
- [ ] Watch for leader changes (standby mode)
- [ ] Graceful leadership handoff on shutdown
- [ ] Integration tests with multiple instances

**Implementation:**

```python
class LeaderElectionService:
    """etcd-based leader election for HA services."""

    def __init__(self, etcd: EtcdStateStore, service_name: str, instance_id: str):
        self._etcd = etcd
        self._service_name = service_name
        self._instance_id = instance_id
        self._is_leader = False
        self._lease = None

    async def start_async(self) -> None:
        """Start leader election process."""
        ...

    async def stop_async(self) -> None:
        """Release leadership gracefully."""
        ...

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    def on_leadership_acquired(self, callback: Callable) -> None:
        """Register callback for when leadership is acquired."""
        ...

    def on_leadership_lost(self, callback: Callable) -> None:
        """Register callback for when leadership is lost."""
        ...
```

**Dependencies:** Phase 1 etcd integration

**Effort Estimate:** 2 days

---

#### Task 2.2: Scheduler Service Core (3 days)

**Files to Create:**

```
src/application/services/scheduler_service.py
src/application/services/placement_engine.py
tests/unit/application/services/test_scheduler_service.py
tests/unit/application/services/test_placement_engine.py
```

**Acceptance Criteria:**

- [ ] SchedulerService with reconciliation loop (30s default)
- [ ] Watch for PENDING instances via etcd
- [ ] Delegate placement decisions to PlacementEngine
- [ ] Call Control Plane API for state transitions
- [ ] Only run loop when leader
- [ ] Comprehensive unit tests with mocks

**Scheduling Loop:**

```python
class SchedulerService:
    """Scheduler service with leader election."""

    async def _run_scheduling_loop(self) -> None:
        """Main scheduling loop - only runs when leader."""
        while self._running:
            if not self._leader_election.is_leader:
                await asyncio.sleep(1)
                continue

            try:
                # Process pending instances
                await self._process_pending_instances()

                # Check scheduled instances approaching timeslot
                await self._check_approaching_timeslots()

                # Reconciliation check
                await self._reconcile_scheduled_instances()

            except Exception as e:
                logger.error(f"Scheduling loop error: {e}")

            await asyncio.sleep(self._reconcile_interval)
```

**Dependencies:** Task 2.1

**Effort Estimate:** 3 days

---

### Week 6: Placement Algorithm & Timeslot Management

#### Task 2.3: Placement Engine (2 days)

**Files to Create:**

```
src/application/services/placement_engine.py
src/application/models/scheduling_decision.py
tests/unit/application/services/test_placement_engine.py
```

**Acceptance Criteria:**

- [ ] Filter workers by license affinity
- [ ] Filter workers by resource requirements
- [ ] Filter workers by AMI requirements
- [ ] Filter workers by available capacity
- [ ] Filter workers by available ports
- [ ] Exclude DRAINING workers
- [ ] Score by utilization (bin-packing: prefer fuller workers)
- [ ] Return ScaleUpRequired if no suitable worker
- [ ] Unit tests with various scenarios

**Algorithm:**

```python
@dataclass
class SchedulingDecision:
    action: Literal["assign", "scale_up", "wait"]
    worker_id: str | None = None
    worker_template: str | None = None
    reason: str = ""


class PlacementEngine:
    """Placement algorithm for LabletInstances."""

    def schedule(
        self,
        instance: LabletInstance,
        definition: LabletDefinition,
        workers: list[CMLWorker]
    ) -> SchedulingDecision:
        # Phase 1: Filter eligible workers
        candidates = self._filter_eligible(workers, definition)

        if not candidates:
            return SchedulingDecision(
                action="scale_up",
                worker_template=self._select_template(definition),
                reason="No worker with sufficient capacity"
            )

        # Phase 2: Score candidates (bin-packing)
        scored = self._score_candidates(candidates, definition)

        # Phase 3: Select best
        best = max(scored, key=lambda x: x[1])
        return SchedulingDecision(
            action="assign",
            worker_id=best[0].id(),
            reason=f"Best fit with {best[1]:.2f} utilization"
        )
```

**Dependencies:** Phase 1 aggregates

**Effort Estimate:** 2 days

---

#### Task 2.4: Timeslot Manager (2 days)

**Files to Create:**

```
src/application/services/timeslot_manager.py
tests/unit/application/services/test_timeslot_manager.py
```

**Acceptance Criteria:**

- [ ] Monitor scheduled instances approaching timeslot
- [ ] Calculate lead time (35 min = worker boot + instantiation)
- [ ] Trigger instantiation at appropriate time
- [ ] Handle "ASAP" scheduling (immediate)
- [ ] Handle future-dated scheduling
- [ ] Unit tests with time mocking

**Lead Time Calculation:**

```python
WORKER_BOOTUP_DELAY = timedelta(minutes=20)
LABLET_INSTANTIATION_DELAY = timedelta(minutes=15)
TOTAL_LEAD_TIME = WORKER_BOOTUP_DELAY + LABLET_INSTANTIATION_DELAY  # 35 min


class TimeslotManager:
    """Manages timeslot-based scheduling."""

    def get_approaching_instances(
        self,
        instances: list[LabletInstance],
        lookahead: timedelta = TOTAL_LEAD_TIME
    ) -> list[LabletInstance]:
        """Get instances whose timeslot is approaching."""
        now = datetime.now(timezone.utc)
        threshold = now + lookahead

        return [
            i for i in instances
            if i.state.state == LabletInstanceState.SCHEDULED
            and i.state.timeslot_start <= threshold
        ]
```

**Dependencies:** Task 2.2

**Effort Estimate:** 2 days

---

#### Task 2.5: Internal Scheduler Endpoints (1 day)

**Files to Create:**

```
src/api/controllers/internal_scheduler_controller.py
src/application/commands/schedule_instance_command.py
src/application/commands/allocate_ports_command.py
```

**Acceptance Criteria:**

- [ ] POST /api/internal/instances/{id}/schedule
- [ ] POST /api/internal/instances/{id}/allocate-ports
- [ ] POST /api/internal/instances/{id}/transition
- [ ] Internal endpoints secured (API key or service account)
- [ ] Integration tests

**Dependencies:** Tasks 2.2, 2.3

**Effort Estimate:** 1 day

---

### Week 7: Lab YAML Rewriting & Instantiation

#### Task 2.6: Artifact Storage Service (1 day)

**Files to Create:**

```
src/integration/services/artifact_storage_service.py
tests/integration/test_artifact_storage.py
```

**Acceptance Criteria:**

- [ ] Download lab YAML from S3/MinIO
- [ ] Upload rewritten YAML (temporary)
- [ ] Async operations with aiobotocore
- [ ] Error handling and retry logic
- [ ] Integration tests with MinIO

**Dependencies:** Prerequisites (MinIO)

**Effort Estimate:** 1 day

---

#### Task 2.7: Lab YAML Rewriting Service (2 days)

**Files to Create:**

```
src/application/services/lab_yaml_rewriter.py
tests/unit/application/services/test_lab_yaml_rewriter.py
```

**Acceptance Criteria:**

- [ ] Parse lab YAML using ruamel-yaml (preserve formatting)
- [ ] Replace port placeholders with allocated ports
- [ ] Handle smart_annotations tags (serial:, vnc:)
- [ ] Handle node tags
- [ ] Validate rewritten YAML
- [ ] Comprehensive unit tests with sample YAMLs

**Implementation:**

```python
class LabYamlRewriter:
    """Rewrites lab YAML with allocated ports."""

    def rewrite(
        self,
        lab_yaml: str,
        port_template: PortTemplate,
        allocated_ports: dict[str, int]
    ) -> str:
        """
        Replace port placeholders with actual ports.

        Template: serial:${PORT_SERIAL_1}
        Output:   serial:5041
        """
        yaml = ruamel.yaml.YAML()
        yaml.preserve_quotes = True

        data = yaml.load(lab_yaml)

        # Build placeholder -> port mapping
        port_map = self._build_port_map(port_template, allocated_ports)

        # Rewrite smart_annotations
        self._rewrite_annotations(data, port_map)

        # Rewrite node tags
        self._rewrite_node_tags(data, port_map)

        # Serialize back
        stream = StringIO()
        yaml.dump(data, stream)
        return stream.getvalue()
```

**Dependencies:** Task 2.6

**Effort Estimate:** 2 days

---

#### Task 2.8: Instantiation Service (2 days)

**Files to Create:**

```
src/application/services/instantiation_service.py
src/application/commands/instantiate_lablet_command.py
tests/unit/application/services/test_instantiation_service.py
```

**Acceptance Criteria:**

- [ ] Download lab YAML from artifact storage
- [ ] Rewrite with allocated ports
- [ ] Import lab to CML worker via CML API
- [ ] Start lab on CML worker
- [ ] Update instance state (INSTANTIATING → RUNNING)
- [ ] Handle errors (INSTANTIATING → TERMINATED)
- [ ] Unit tests with mocked dependencies

**Instantiation Flow:**

```python
class InstantiationService:
    """Handles LabletInstance instantiation on workers."""

    async def instantiate_async(
        self,
        instance_id: str,
        cancellation_token=None
    ) -> OperationResult[str]:
        """
        Instantiate a scheduled LabletInstance.

        Steps:
        1. Get instance and validate state (SCHEDULED)
        2. Get definition and download lab YAML
        3. Rewrite YAML with allocated ports
        4. Transition to INSTANTIATING
        5. Import lab to CML worker
        6. Start lab on CML worker
        7. Transition to RUNNING with cml_lab_id
        """
        ...
```

**Dependencies:** Tasks 2.6, 2.7, Phase 1 CML API client

**Effort Estimate:** 2 days

---

### Week 8: SSE Updates & Integration Testing

#### Task 2.9: SSE Instance State Updates (2 days)

**Files to Modify:**

```
src/application/services/sse_event_relay.py (extend)
src/api/controllers/events_controller.py (extend)
```

**Files to Create:**

```
src/application/events/lablet_instance_state_changed_event.py
```

**Acceptance Criteria:**

- [ ] Broadcast instance state changes via SSE
- [ ] Filter by instance_id, definition_id, owner_id
- [ ] Include state transition details
- [ ] Integration with existing SSE infrastructure
- [ ] UI can subscribe to instance updates

**Event Payload:**

```python
@dataclass
class LabletInstanceStateChangedEvent:
    instance_id: str
    previous_state: str
    new_state: str
    worker_id: str | None
    allocated_ports: dict[str, int] | None
    timestamp: datetime
```

**Dependencies:** Task 2.8

**Effort Estimate:** 2 days

---

#### Task 2.10: Scheduler Integration Tests (2 days)

**Files to Create:**

```
tests/integration/test_scheduler_e2e.py
tests/integration/test_instantiation_e2e.py
```

**Acceptance Criteria:**

- [ ] End-to-end test: create instance → scheduled → instantiated → running
- [ ] Test leader election failover
- [ ] Test placement with multiple workers
- [ ] Test timeslot-based scheduling
- [ ] Test port allocation and rewriting
- [ ] All tests pass in CI

**Dependencies:** All Phase 2 tasks

**Effort Estimate:** 2 days

---

#### Task 2.11: Scheduler Background Job Registration (1 day)

**Files to Modify:**

```
src/main.py (register scheduler startup)
```

**Files to Create:**

```
src/application/jobs/scheduler_startup_job.py
```

**Acceptance Criteria:**

- [ ] Scheduler starts on application startup (if enabled)
- [ ] Graceful shutdown on application termination
- [ ] Configuration via settings (enable/disable)
- [ ] Logging of scheduler lifecycle events

**Dependencies:** Tasks 2.1, 2.2

**Effort Estimate:** 1 day

---

## 3. Dependencies Graph

```
Week 5                  Week 6                  Week 7                  Week 8
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 2.1│──────────▶│ Task 2.3│            │ Task 2.6│──────────▶│ Task 2.9│
│ Leader  │            │ Placement│            │ Artifact│            │ SSE     │
│ Election│            │ Engine   │            │ Storage │            │ Updates │
└────┬────┘            └────┬────┘            └────┬────┘            └─────────┘
     │                      │                      │                      │
     ▼                      │                      ▼                      │
┌─────────┐            ┌────┴────┐            ┌─────────┐            ┌─────────┐
│ Task 2.2│──────────▶│ Task 2.4│            │ Task 2.7│            │Task 2.10│
│Scheduler│            │ Timeslot│            │ YAML    │            │ Integ   │
│ Service │            │ Manager │            │ Rewrite │            │ Tests   │
└────┬────┘            └────┬────┘            └────┬────┘            └────┬────┘
     │                      │                      │                      │
     │                      ▼                      ▼                      │
     │                 ┌─────────┐            ┌─────────┐            ┌────┴────┐
     │                 │ Task 2.5│◀───────────│ Task 2.8│            │Task 2.11│
     └────────────────▶│ Internal│            │ Instant-│            │ Startup │
                       │ Endpoints            │ iation  │            │ Job     │
                       └─────────┘            └─────────┘            └─────────┘
```

---

## 4. Test Coverage Requirements

| Component | Unit Tests | Integration Tests | Target Coverage |
|-----------|------------|-------------------|-----------------|
| Leader Election | Yes | Yes (multi-instance) | ≥85% |
| Scheduler Service | Yes | Yes | ≥85% |
| Placement Engine | Yes | - | ≥90% |
| Timeslot Manager | Yes | - | ≥90% |
| Lab YAML Rewriter | Yes | - | ≥95% |
| Instantiation Service | Yes | Yes | ≥85% |
| SSE Updates | - | Yes | ≥80% |

---

## 5. Phase 2 Acceptance Criteria

### Functional

- [ ] Scheduler automatically assigns PENDING instances to workers
- [ ] Placement algorithm correctly selects worker based on constraints
- [ ] Instances are instantiated when timeslot approaches
- [ ] Lab YAML is correctly rewritten with allocated ports
- [ ] Labs are imported and started on CML workers
- [ ] Instance state changes broadcast via SSE
- [ ] Leader election provides HA (failover < 30s)

### Non-Functional

- [ ] Scheduling decision time < 5s
- [ ] Instantiation time < 3 min (excluding worker startup)
- [ ] Scheduler loop interval configurable
- [ ] No orphaned instances (state machine consistency)

### Documentation

- [ ] Scheduler architecture documented
- [ ] Placement algorithm explained
- [ ] Troubleshooting guide for scheduling issues

---

## 6. Risks & Mitigations (Phase 2 Specific)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Leader election race conditions | High | Low | Use etcd transactions, comprehensive testing |
| CML API timeout during instantiation | Medium | Medium | Implement retry with exponential backoff |
| Lab YAML format variations | Medium | Medium | Extensive test fixtures, graceful error handling |
| Timeslot miscalculation | High | Low | Buffer time in lead time calculation |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
