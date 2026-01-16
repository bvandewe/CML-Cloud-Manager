# Phase 1: Foundation

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Duration** | Weeks 1-4 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |

---

## 1. Phase Objectives

- Define and implement LabletDefinition aggregate
- Define and implement LabletInstance aggregate
- Extend CMLWorker with capacity tracking
- Implement basic CRUD APIs for definitions and instances
- Implement port allocation service
- Set up etcd integration foundation

---

## 2. Task Breakdown

### Week 1: Domain Model - LabletDefinition

#### Task 1.1: LabletDefinition Aggregate (3 days)

**Files to Create:**

```
src/domain/entities/lablet_definition.py
src/domain/events/lablet_definition_events.py
src/domain/value_objects/resource_requirements.py
src/domain/value_objects/port_template.py
src/domain/enums/license_type.py
```

**Acceptance Criteria:**

- [ ] LabletDefinitionState dataclass with all required fields
- [ ] LabletDefinition aggregate with `@dispatch` event handlers
- [ ] Domain events: Created, VersionCreated, Deprecated
- [ ] Value objects: ResourceRequirements, PortTemplate, AmiRequirement
- [ ] LicenseType enum: PERSONAL, ENTERPRISE, EVALUATION
- [ ] Unit tests with ≥90% coverage

**Implementation Pattern:**

```python
# Follow existing pattern from lab_record.py
@dataclass
class LabletDefinitionState(AggregateState[str]):
    id: str
    name: str
    version: str  # Semantic version
    lab_artifact_uri: str
    lab_yaml_hash: str
    resource_requirements: ResourceRequirements
    license_affinity: list[LicenseType]
    node_count: int
    port_template: PortTemplate
    # ... see architecture doc for full spec
```

**Dependencies:** None (foundation task)

**Effort Estimate:** 3 days

---

#### Task 1.2: LabletDefinition Repository (2 days)

**Files to Create:**

```
src/domain/repositories/lablet_definition_repository.py
src/integration/repositories/mongo_lablet_definition_repository.py
```

**Acceptance Criteria:**

- [ ] Abstract repository interface with async methods
- [ ] MongoDB implementation using MotorRepository pattern
- [ ] Methods: `add_async`, `get_by_id_async`, `get_by_name_and_version_async`, `list_async`
- [ ] Version filtering support
- [ ] Integration tests with MongoDB

**Implementation Pattern:**

```python
# Follow existing pattern from integration/repositories/
class LabletDefinitionRepository(ABC):
    @abstractmethod
    async def add_async(self, definition: LabletDefinition, ct=None) -> None: ...

    @abstractmethod
    async def get_by_id_async(self, id: str, ct=None) -> LabletDefinition | None: ...

    @abstractmethod
    async def list_versions_async(self, name: str, ct=None) -> list[LabletDefinition]: ...
```

**Dependencies:** Task 1.1

**Effort Estimate:** 2 days

---

### Week 2: Domain Model - LabletInstance & CMLWorker Extensions

#### Task 1.3: LabletInstance Aggregate (3 days)

**Files to Create:**

```
src/domain/entities/lablet_instance.py
src/domain/events/lablet_instance_events.py
src/domain/enums/lablet_instance_state.py
src/domain/value_objects/grading_score.py
src/domain/value_objects/state_transition.py
```

**Acceptance Criteria:**

- [ ] LabletInstanceState dataclass with all required fields
- [ ] State enum with all 10 states (PENDING → TERMINATED)
- [ ] Domain events for each state transition
- [ ] State transition validation (prevent invalid transitions)
- [ ] State history tracking (list of StateTransition)
- [ ] Unit tests with ≥90% coverage

**State Machine Validation:**

```python
VALID_TRANSITIONS = {
    LabletInstanceState.PENDING: [SCHEDULED, TERMINATED],
    LabletInstanceState.SCHEDULED: [INSTANTIATING, TERMINATED],
    LabletInstanceState.INSTANTIATING: [RUNNING, TERMINATED],
    LabletInstanceState.RUNNING: [COLLECTING, STOPPING],
    # ... etc
}
```

**Dependencies:** Task 1.1 (for definition reference)

**Effort Estimate:** 3 days

---

#### Task 1.4: LabletInstance Repository (1 day)

**Files to Create:**

```
src/domain/repositories/lablet_instance_repository.py
src/integration/repositories/mongo_lablet_instance_repository.py
```

**Acceptance Criteria:**

- [ ] Abstract repository interface
- [ ] MongoDB implementation
- [ ] Query methods: by_id, by_worker, by_state, by_owner
- [ ] Timeslot-based queries (approaching timeslots)
- [ ] Integration tests

**Dependencies:** Task 1.3

**Effort Estimate:** 1 day

---

#### Task 1.5: CMLWorker Capacity Extensions (1 day)

**Files to Modify:**

```
src/domain/entities/cml_worker.py
src/domain/events/cml_worker.py (add new events)
src/domain/value_objects/worker_capacity.py (new)
src/domain/value_objects/port_allocation.py (new)
```

**Acceptance Criteria:**

- [ ] WorkerCapacity value object (cpu_cores, memory_gb, storage_gb, max_nodes)
- [ ] PortAllocation value object (instance_id, ports dict, allocated_at)
- [ ] New fields on CMLWorkerState: template_name, declared_capacity, allocated_capacity, port_allocations, instance_ids
- [ ] New domain events: CapacityUpdated, PortsAllocated, PortsReleased
- [ ] Computed properties: available_capacity, available_ports
- [ ] Backward compatibility with existing CMLWorker usage
- [ ] Unit tests for new functionality

**Dependencies:** None (extends existing)

**Effort Estimate:** 1 day

---

### Week 3: etcd Integration & Port Allocation

#### Task 1.6: etcd Client Service (2 days)

**Files to Create:**

```
src/integration/services/etcd_client.py
src/integration/services/etcd_state_store.py
tests/integration/test_etcd_client.py
```

**Acceptance Criteria:**

- [ ] Async etcd client wrapper (singleton service)
- [ ] Key-value operations: get, put, delete, watch
- [ ] Lease management for leader election
- [ ] Connection pooling and retry logic
- [ ] Health check method
- [ ] Integration tests with etcd container

**Key Structure:**

```python
class EtcdStateStore:
    """State store operations using etcd."""

    # Key patterns
    INSTANCE_STATE_KEY = "/ccm/instances/{id}/state"
    WORKER_STATE_KEY = "/ccm/workers/{id}/state"
    WORKER_PORTS_KEY = "/ccm/workers/{id}/ports"
    LEADER_KEY = "/ccm/{service}/leader"

    async def get_instance_state(self, instance_id: str) -> str | None: ...
    async def set_instance_state(self, instance_id: str, state: str) -> None: ...
    async def watch_instances_by_state(self, state: str) -> AsyncIterator[...]: ...
```

**Dependencies:** Prerequisites complete (etcd running)

**Effort Estimate:** 2 days

---

#### Task 1.7: Port Allocation Service (2 days)

**Files to Create:**

```
src/application/services/port_allocation_service.py
tests/unit/application/services/test_port_allocation_service.py
```

**Acceptance Criteria:**

- [ ] Allocate ports for LabletInstance based on PortTemplate
- [ ] Track allocations per worker (in etcd)
- [ ] Prevent conflicts (atomic allocation)
- [ ] Release ports on instance termination
- [ ] Port range validation (2000-9999)
- [ ] Unit tests with mocked etcd
- [ ] Integration tests with real etcd

**Implementation:**

```python
class PortAllocationService:
    """Manages port allocation per worker."""

    def __init__(self, etcd_store: EtcdStateStore, worker_repo: CMLWorkerRepository):
        self._etcd = etcd_store
        self._workers = worker_repo

    async def allocate_ports(
        self,
        worker_id: str,
        instance_id: str,
        port_template: PortTemplate
    ) -> dict[str, int]:
        """Allocate ports for instance on worker. Returns port mapping."""
        ...

    async def release_ports(self, worker_id: str, instance_id: str) -> None:
        """Release ports when instance terminates."""
        ...
```

**Dependencies:** Task 1.6

**Effort Estimate:** 2 days

---

#### Task 1.8: Worker Template Service (1 day)

**Files to Create:**

```
src/domain/entities/worker_template.py
src/application/services/worker_template_service.py
src/domain/repositories/worker_template_repository.py
src/integration/repositories/mongo_worker_template_repository.py
```

**Acceptance Criteria:**

- [ ] WorkerTemplate aggregate (seeded from config per ADR-007)
- [ ] Load templates from YAML config file
- [ ] Seed to MongoDB on startup (upsert by name)
- [ ] Select template based on LabletDefinition requirements
- [ ] Unit tests

**Dependencies:** Task 1.5 (WorkerCapacity value object)

**Effort Estimate:** 1 day

---

### Week 4: CRUD APIs

#### Task 1.9: LabletDefinition CRUD Commands/Queries (2 days)

**Files to Create:**

```
src/application/commands/create_lablet_definition_command.py
src/application/commands/sync_lablet_definition_command.py
src/application/queries/get_lablet_definition_query.py
src/application/queries/list_lablet_definitions_query.py
src/application/dtos/lablet_definition_dto.py
```

**Acceptance Criteria:**

- [ ] CreateLabletDefinitionCommand with validation
- [ ] SyncLabletDefinitionCommand (trigger artifact sync)
- [ ] GetLabletDefinitionQuery (by id, by name+version)
- [ ] ListLabletDefinitionsQuery (with pagination, filters)
- [ ] DTOs for API responses
- [ ] Unit tests for handlers

**Pattern:** Self-contained command/query files (request + handler)

**Dependencies:** Tasks 1.1, 1.2

**Effort Estimate:** 2 days

---

#### Task 1.10: LabletInstance CRUD Commands/Queries (2 days)

**Files to Create:**

```
src/application/commands/create_lablet_instance_command.py
src/application/commands/terminate_lablet_instance_command.py
src/application/queries/get_lablet_instance_query.py
src/application/queries/list_lablet_instances_query.py
src/application/dtos/lablet_instance_dto.py
```

**Acceptance Criteria:**

- [ ] CreateLabletInstanceCommand (reservation request)
- [ ] TerminateLabletInstanceCommand
- [ ] GetLabletInstanceQuery
- [ ] ListLabletInstancesQuery (filter by state, worker, owner)
- [ ] DTOs for API responses
- [ ] Unit tests for handlers

**Dependencies:** Tasks 1.3, 1.4

**Effort Estimate:** 2 days

---

#### Task 1.11: REST API Controllers (1 day)

**Files to Create:**

```
src/api/controllers/lablet_definitions_controller.py
src/api/controllers/lablet_instances_controller.py
```

**Acceptance Criteria:**

- [ ] LabletDefinitionsController with CRUD endpoints
- [ ] LabletInstancesController with CRUD endpoints
- [ ] OpenAPI documentation
- [ ] Authentication via existing DualAuthService
- [ ] Integration tests

**Endpoints:**

```
POST   /api/v1/definitions
GET    /api/v1/definitions
GET    /api/v1/definitions/{id}
POST   /api/v1/definitions/{id}/sync

POST   /api/v1/instances
GET    /api/v1/instances
GET    /api/v1/instances/{id}
DELETE /api/v1/instances/{id}
```

**Dependencies:** Tasks 1.9, 1.10

**Effort Estimate:** 1 day

---

## 3. Dependencies Graph

```
Week 1                  Week 2                  Week 3                  Week 4
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 1.1│──────────▶│ Task 1.3│            │ Task 1.6│──────────▶│ Task 1.9│
│ Defn    │            │ Instance│            │ etcd    │            │ Defn API│
│ Aggr    │            │ Aggr    │            │ Client  │            │         │
└────┬────┘            └────┬────┘            └────┬────┘            └─────────┘
     │                      │                      │                      │
     ▼                      ▼                      ▼                      │
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 1.2│            │ Task 1.4│            │ Task 1.7│            │Task 1.10│
│ Defn    │            │ Instance│            │ Port    │            │ Inst API│
│ Repo    │            │ Repo    │            │ Alloc   │            │         │
└─────────┘            └─────────┘            └────┬────┘            └────┬────┘
                            │                      │                      │
                            │                 ┌────┴────┐                 │
                       ┌────┴────┐            │ Task 1.8│            ┌────┴────┐
                       │ Task 1.5│            │ Worker  │            │Task 1.11│
                       │ CMLWrkr │            │ Template│            │ REST    │
                       │ Extend  │            │ Service │            │ Ctrlrs  │
                       └─────────┘            └─────────┘            └─────────┘
```

---

## 4. Test Coverage Requirements

| Component | Unit Tests | Integration Tests | Target Coverage |
|-----------|------------|-------------------|-----------------|
| LabletDefinition Aggregate | Yes | - | ≥90% |
| LabletInstance Aggregate | Yes | - | ≥90% |
| Repositories | Yes | Yes (MongoDB) | ≥85% |
| etcd Client | Yes | Yes (etcd) | ≥80% |
| Port Allocation Service | Yes | Yes | ≥90% |
| Commands/Queries | Yes | - | ≥85% |
| Controllers | - | Yes | ≥80% |

---

## 5. Phase 1 Acceptance Criteria

### Functional

- [ ] LabletDefinitions can be created, retrieved, and listed via API
- [ ] LabletInstances can be created (in PENDING state), retrieved, and listed
- [ ] Port allocation correctly reserves unique ports per worker
- [ ] CMLWorker capacity tracking reflects allocated resources
- [ ] etcd stores instance/worker state and can be watched

### Non-Functional

- [ ] All new code follows Neuroglia patterns (CQRS, DI, @dispatch)
- [ ] No regressions in existing functionality
- [ ] API response time < 500ms (p95)
- [ ] Test coverage ≥85% overall for Phase 1 code

### Documentation

- [ ] All new aggregates documented with docstrings
- [ ] API endpoints documented in OpenAPI spec
- [ ] README updated with new capabilities

---

## 6. Risks & Mitigations (Phase 1 Specific)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| etcd learning curve | Medium | Medium | Allocate buffer time, pair programming |
| MongoDB schema changes | Medium | Low | Use versioned migrations, backward compat |
| Port allocation race conditions | High | Medium | Use etcd transactions for atomicity |
| Aggregate complexity | Medium | Low | Follow existing patterns strictly |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
