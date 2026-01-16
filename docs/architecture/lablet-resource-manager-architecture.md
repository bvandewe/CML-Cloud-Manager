# Lablet Resource Manager - Architecture Design

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.2.0 |
| **Status** | Draft |
| **Created** | 2026-01-15 |
| **Last Updated** | 2026-01-15 |
| **Author** | Architecture Team |
| **Related** | [Requirements Specification](../specs/lablet-resource-manager-requirements.md), [ADRs](./adr/README.md) |

---

## 1. Architecture Overview

### 1.1 Design Principles

| Principle | Application |
|-----------|-------------|
| **Declarative over Imperative** | Users declare desired state; system reconciles |
| **Separation of Concerns** | API, Scheduling, Control each have distinct responsibilities |
| **Event-Driven Integration** | CloudEvents for async external communication |
| **API-Centric State Management** | Single source of truth via Control Plane API |
| **Provider Abstraction** | SPI pattern for cloud provider independence |

### 1.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL CLIENTS                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │ REST API │  │ UI (SPA) │  │ Assessment Svc   │  │ Audit/Compliance  │   │
│  │ Clients  │  │          │  │ (CloudEvents)    │  │ (CloudEvents)     │   │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  └─────────┬─────────┘   │
└───────┼─────────────┼─────────────────┼──────────────────────┼─────────────┘
        │             │                 │                      │
        ▼             ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CML CLOUD MANAGER SYSTEM                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CONTROL PLANE API                               │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │   │
│  │  │ Definition  │ │ Instance    │ │ Worker      │ │ Reservation   │  │   │
│  │  │ Endpoints   │ │ Endpoints   │ │ Endpoints   │ │ Endpoints     │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────────────┘  │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │   │
│  │  │ SSE Stream  │ │ Admission   │ │ Rate        │ │ Auth/RBAC     │  │   │
│  │  │             │ │ Control     │ │ Limiting    │ │               │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────────────┘  │   │
│  └───────────────────────────┬─────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DUAL STORAGE ARCHITECTURE                       │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────┐   ┌────────────────────────────────┐ │   │
│  │  │      STATE STORE (etcd)   │   │     SPEC STORE (MongoDB)       │ │   │
│  │  │                           │   │                                │ │   │
│  │  │  • Instance states        │   │  • LabletDefinitions (full)    │ │   │
│  │  │  • Worker states          │   │  • WorkerTemplates (full)      │ │   │
│  │  │  • Port allocations       │   │  • Audit events (CloudEvents)  │ │   │
│  │  │  • Leader election keys   │   │  • Complex aggregates          │ │   │
│  │  │  • Watch subscriptions    │   │  • Historical data             │ │   │
│  │  │                           │   │                                │ │   │
│  │  │  [Native Watch Mechanism] │   │  [Rich Query Capabilities]     │ │   │
│  │  └─────────────┬─────────────┘   └────────────────────────────────┘ │   │
│  │                │                                                     │   │
│  │                │ Watch Events                                        │   │
│  │                ▼                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│         ┌────────────────────┼────────────────────┐                        │
│         ▼                    ▼                    ▼                        │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────────────┐        │
│  │  SCHEDULER  │      │  RESOURCE   │      │   CLOUD PROVIDER    │        │
│  │  SERVICE    │      │  CONTROLLER │      │   SPI               │        │
│  │             │      │             │      │                     │        │
│  │ • Watch for │      │ • Watch for │      │ • AWS EC2 Adapter   │        │
│  │   PENDING   │      │   SCHEDULED │      │ • (Future: GCP/Az)  │        │
│  │ • Placement │      │ • Reconcile │      │                     │        │
│  │ • Queue Mgmt│      │ • Scale Up  │      │                     │        │
│  │ • Timeslots │      │ • Scale Down│      │                     │        │
│  │             │      │ • DRAINING  │      │                     │        │
│  │ [Leader     │      │ [Leader     │      │                     │        │
│  │  Election]  │      │  Election]  │      │                     │        │
│  └─────────────┘      └─────────────┘      └─────────────────────┘        │
│         │                    │                    │                        │
│         └────────────────────┼────────────────────┘                        │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CLOUDEVENTS BUS                                   │   │
│  │                   (cloud-streams)                                    │   │
│  │                                                                      │   │
│  │  [Persists events for audit/analytics - NOT primary write model]    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CML WORKERS (Data Plane)                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │ Worker 1    │  │ Worker 2    │  │ Worker N    │                  │   │
│  │  │ (Personal)  │  │ (Enterprise)│  │ (DRAINING)  │                  │   │
│  │  │             │  │             │  │             │                  │   │
│  │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │                  │   │
│  │  │ │Instance1│ │  │ │Instance3│ │  │ │Instance5│ │ ◀─ completing    │   │
│  │  │ └─────────┘ │  │ ├─────────┤ │  │ └─────────┘ │                  │   │
│  │  │ ┌─────────┐ │  │ │Instance4│ │  │             │ ◀─ no new        │   │
│  │  │ │Instance2│ │  │ └─────────┘ │  │             │    assignments   │   │
│  │  │ └─────────┘ │  │             │  │             │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ Artifact Storage │  │ Keycloak         │  │ OTEL Collector           │  │
│  │ (S3/MinIO)       │  │ (Auth)           │  │ (Traces/Metrics/Logs)    │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Storage Architecture Decision

> **See [ADR-005: Dual State Store Architecture](./adr/ADR-005-state-store-architecture.md) for full rationale.**

| Store | Purpose | Data Types | Key Feature |
|-------|---------|------------|-------------|
| **etcd** | State coordination | Instance states, worker states, port allocations, leader keys | Native watch mechanism |
| **MongoDB** | Spec/document storage | LabletDefinitions, WorkerTemplates, Audit events | Rich queries, schema flexibility |
| **Redis** | UI Session storage | User sessions (httpOnly cookies) | Fast, ephemeral |

**Why not just MongoDB?**

- MongoDB Change Streams have limitations (cursor timeout, resumption complexity)
- No built-in leader election primitives
- etcd's watch mechanism is more reliable for reactive state propagation

**Redis clarification:**

- Redis stores **UI session data** (user authentication state via httpOnly cookies)
- NOT used for Scheduler/Controller coordination (that's etcd)
- Could migrate to etcd, but Redis is simpler for session TTL management

---

## 2. Component Design

### 2.1 Control Plane API

**Responsibility:** Central gateway for all state operations, authentication, and real-time updates.

**Key Design Decision:** The Control Plane API is the **ONLY** component that writes to MongoDB. All other services (Scheduler, Resource Controller) read state and request mutations via the API.

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTROL PLANE API                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐ │
│  │   REST API     │    │   Event API    │    │   SSE Stream   │ │
│  │   Endpoints    │    │   (Webhooks)   │    │   (Real-time)  │ │
│  └───────┬────────┘    └───────┬────────┘    └───────┬────────┘ │
│          │                     │                     │          │
│          ▼                     ▼                     ▼          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    ADMISSION CONTROL                      │  │
│  │  • Authentication (Keycloak JWT)                          │  │
│  │  • Authorization (RBAC)                                   │  │
│  │  • Rate Limiting                                          │  │
│  │  • Request Validation                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│          │                     │                     │          │
│          ▼                     ▼                     ▼          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    COMMAND/QUERY BUS                      │  │
│  │                    (Neuroglia Mediator)                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    DOMAIN LAYER                           │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │  │
│  │  │ Lablet     │  │ Lablet     │  │ CMLWorker          │  │  │
│  │  │ Definition │  │ Instance   │  │ (Extended)         │  │  │
│  │  │ Aggregate  │  │ Aggregate  │  │ Aggregate          │  │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    EVENT PUBLISHER                        │  │
│  │                    (CloudEvents)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.1.1 API Endpoints

**LabletDefinition Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/definitions` | Create/register new definition |
| GET | `/api/v1/definitions` | List all definitions |
| GET | `/api/v1/definitions/{id}` | Get definition by ID |
| GET | `/api/v1/definitions/{id}/versions` | List all versions |
| GET | `/api/v1/definitions/{id}/versions/{version}` | Get specific version |
| POST | `/api/v1/definitions/{id}/sync` | Trigger artifact sync |
| DELETE | `/api/v1/definitions/{id}` | Soft-delete definition |

**LabletInstance Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/instances` | Create instance (reservation) |
| GET | `/api/v1/instances` | List instances (with filters) |
| GET | `/api/v1/instances/{id}` | Get instance details |
| POST | `/api/v1/instances/{id}/start` | Start stopped instance |
| POST | `/api/v1/instances/{id}/stop` | Stop running instance |
| POST | `/api/v1/instances/{id}/collect` | Trigger collection |
| DELETE | `/api/v1/instances/{id}` | Terminate instance |

**Worker Endpoints (Extended):**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/workers/{id}/capacity` | Get capacity details |
| GET | `/api/v1/workers/{id}/instances` | List instances on worker |
| GET | `/api/v1/workers/{id}/ports` | Get port allocations |

**Internal Endpoints (for Scheduler/Controller):**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/internal/instances/{id}/schedule` | Assign worker to instance |
| POST | `/api/internal/instances/{id}/allocate-ports` | Allocate ports |
| POST | `/api/internal/instances/{id}/transition` | Transition state |
| POST | `/api/internal/workers/scale-up` | Request new worker |
| POST | `/api/internal/workers/{id}/scale-down` | Stop/terminate worker |

---

### 2.2 Scheduler Service

**Responsibility:** Make placement decisions and manage the scheduling queue.

**Key Design Decision:** Stateless service that reads state via etcd watches and writes decisions via Control Plane API. Uses leader election for HA (see [ADR-006](./adr/ADR-006-scheduler-ha-coordination.md)).

```
┌─────────────────────────────────────────────────────────────────┐
│                     SCHEDULER SERVICE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  LEADER ELECTION (etcd)                   │  │
│  │     Only leader runs scheduling loop; standbys watch     │  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    SCHEDULING LOOP                        │  │
│  │   Triggered by: etcd watch + Periodic reconciliation (30s)│  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │                                    │
│            ┌───────────────┼───────────────┐                   │
│            ▼               ▼               ▼                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ PENDING      │  │ SCHEDULED    │  │ APPROACHING  │         │
│  │ QUEUE        │  │ QUEUE        │  │ TIMESLOTS    │         │
│  │ PROCESSOR    │  │ MONITOR      │  │ MONITOR      │         │
│  │              │  │              │  │              │         │
│  │ [etcd watch: │  │ [Verify      │  │ [35min lead  │         │
│  │  state=PEND] │  │  assignments]│  │  time check] │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                   │
│         ▼                 ▼                 ▼                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    PLACEMENT ENGINE                       │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │ 1. Filter: License Affinity                         │ │  │
│  │  │ 2. Filter: Resource Requirements                    │ │  │
│  │  │ 3. Filter: AMI Requirements                         │ │  │
│  │  │ 4. Filter: Available Capacity                       │ │  │
│  │  │ 5. Filter: Available Ports                          │ │  │
│  │  │ 6. Filter: NOT DRAINING (exclude draining workers)  │ │  │
│  │  │ 7. Score: Bin-Packing (prefer fuller workers)       │ │  │
│  │  │ 8. Select: Highest scoring worker                   │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  │                                                           │  │
│  │  Outcome:                                                 │  │
│  │  • Worker Found → Call API to schedule instance          │  │
│  │  • No Worker → Signal Resource Controller for scale-up   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.2.0 Scheduler High Availability

> **See [ADR-006: Scheduler HA Coordination](./adr/ADR-006-scheduler-ha-coordination.md) for full details.**

**How multiple schedulers coordinate:**

```python
class SchedulerService:
    """Scheduler with leader election."""

    def __init__(self, etcd_client, api_client, instance_id: str):
        self.etcd = etcd_client
        self.api = api_client
        self.instance_id = instance_id
        self.leader_key = "/ccm/scheduler/leader"
        self.is_leader = False

    async def start_async(self):
        """Start the scheduler service."""
        # Attempt to become leader
        self.is_leader = await self._campaign_for_leadership()

        if self.is_leader:
            # Start leadership maintenance and scheduling loop
            asyncio.create_task(self._maintain_leadership())
            asyncio.create_task(self._run_scheduling_loop())
        else:
            # Watch for leader changes
            asyncio.create_task(self._watch_leader())

    async def _campaign_for_leadership(self) -> bool:
        """Try to become leader via etcd lease."""
        lease = await self.etcd.lease(ttl=15)  # 15 second lease
        try:
            await self.etcd.put(
                self.leader_key,
                self.instance_id,
                lease=lease,
                prev_kv=False,
                create_only=True  # Only succeeds if key doesn't exist
            )
            self._lease = lease
            return True
        except KeyExistsError:
            return False

    async def _watch_leader(self):
        """Watch leader key, campaign when leader fails."""
        async for event in self.etcd.watch(self.leader_key):
            if event.type == EventType.DELETE:
                # Leader lost, try to take over
                self.is_leader = await self._campaign_for_leadership()
                if self.is_leader:
                    asyncio.create_task(self._maintain_leadership())
                    asyncio.create_task(self._run_scheduling_loop())
```

**Failover timeline:**

- Leader crashes → Lease expires in ~15 seconds → Standby detects via watch → Standby campaigns and wins → New leader starts scheduling

**Total failover time: ~15-20 seconds**

#### 2.2.1 Scheduling Algorithm

```python
def schedule_instance(instance: LabletInstance) -> SchedulingDecision:
    """
    Placement algorithm for LabletInstance.
    Returns assigned worker or scale-up request.
    """
    definition = get_definition(instance.definition_id)

    # Phase 1: Filter eligible workers
    candidates = []
    for worker in get_active_workers():
        if not matches_license_affinity(worker, definition):
            continue
        if not meets_resource_requirements(worker, definition):
            continue
        if not matches_ami_requirements(worker, definition):
            continue
        if not has_available_capacity(worker, definition):
            continue
        if not has_available_ports(worker, definition.port_count):
            continue
        candidates.append(worker)

    # Phase 2: No candidates - request scale-up
    if not candidates:
        return SchedulingDecision(
            action=ScaleUpRequired,
            worker_template=select_template(definition),
            reason="No worker with sufficient capacity"
        )

    # Phase 3: Score candidates (bin-packing)
    scored = []
    for worker in candidates:
        score = calculate_utilization_score(worker)  # Higher = fuller
        scored.append((worker, score))

    # Phase 4: Select best worker
    scored.sort(key=lambda x: x[1], reverse=True)
    selected_worker = scored[0][0]

    return SchedulingDecision(
        action=AssignWorker,
        worker_id=selected_worker.id,
        reason=f"Best fit with {scored[0][1]:.2f} utilization"
    )
```

#### 2.2.2 Timeslot Management

```
Timeline:
    NOW                      TIMESLOT_START            TIMESLOT_END
     │                            │                         │
     ▼                            ▼                         ▼
─────┼────────────────────────────┼─────────────────────────┼─────▶
     │                            │                         │
     │◄──── LEAD_TIME ────────────┤                         │
     │      (15 min buffer)       │                         │
     │                            │                         │
     │  ┌─────────────────────┐   │  ┌──────────────────┐  │
     │  │ INSTANTIATION       │   │  │ RUNNING          │  │
     │  │ (Import + Start)    │   │  │ (User Session)   │  │
     │  └─────────────────────┘   │  └──────────────────┘  │
```

The scheduler monitors approaching timeslots and triggers instantiation with `LEAD_TIME` buffer (default: 15 minutes to account for worker startup).

---

### 2.3 Resource Controller

**Responsibility:** Reconciliation loop, auto-scaling decisions, state synchronization.

**Key Design Decision:** Stateless service operating on a periodic reconciliation cycle. Detects drift between desired and actual state.

```
┌─────────────────────────────────────────────────────────────────┐
│                   RESOURCE CONTROLLER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 RECONCILIATION LOOP                       │  │
│  │                 (Every 30 seconds)                        │  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │                                    │
│            ┌───────────────┼───────────────┐                   │
│            ▼               ▼               ▼                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ INSTANCE     │  │ WORKER       │  │ CAPACITY     │         │
│  │ RECONCILER   │  │ RECONCILER   │  │ RECONCILER   │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                   │
│         ▼                 ▼                 ▼                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    STATE COMPARATOR                       │  │
│  │                                                           │  │
│  │  For each resource:                                       │  │
│  │  • Compare desired_state vs actual_state                  │  │
│  │  • Identify drift                                         │  │
│  │  • Generate corrective actions                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    ACTION EXECUTOR                        │  │
│  │                                                           │  │
│  │  • Scale-Up: Create worker via Cloud Provider SPI         │  │
│  │  • Scale-Down: Stop/Terminate idle workers                │  │
│  │  • Sync: Update state from CML API                        │  │
│  │  • Recover: Handle crashed workers/instances              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.3.1 Scale-Up Logic

> **See [ADR-008: Worker Draining State](./adr/ADR-008-worker-draining-state.md) for draining behavior.**

**Critical Timing Considerations:**

- **Worker bootup time**: 15-20 minutes (EC2 m5zn.metal + CML initialization)
- **Lablet instantiation time**: Up to 15 minutes (lab import + node startup)
- **Total lead time**: Up to 35 minutes before scheduled timeslot

```python
# Configurable timing parameters
WORKER_BOOTUP_DELAY_MINUTES = 20      # m5zn.metal EC2 + CML startup
LABLET_INSTANTIATION_DELAY_MINUTES = 15  # Lab import + node startup
TOTAL_LEAD_TIME_MINUTES = WORKER_BOOTUP_DELAY_MINUTES + LABLET_INSTANTIATION_DELAY_MINUTES


def check_scale_up_needed() -> list[ScaleUpAction]:
    """
    Determine if new workers are needed.
    Called by Resource Controller reconciliation loop.

    Must account for:
    1. Worker bootup delay (15-20 min for m5zn.metal)
    2. Lablet instantiation delay (up to 15 min)
    """
    actions = []

    # Get scheduled instances approaching timeslot
    # Use TOTAL_LEAD_TIME to account for both delays
    approaching = get_instances_approaching_timeslot(
        lead_time_minutes=TOTAL_LEAD_TIME_MINUTES  # ~35 minutes
    )

    for instance in approaching:
        if instance.worker_id is None:
            # Instance not yet assigned - scheduler couldn't place it
            definition = get_definition(instance.definition_id)
            template = select_worker_template(definition)

            # Check if scale-up already in progress for this template
            pending_workers = get_workers_in_state(
                template=template,
                states=[WorkerStatus.PENDING, WorkerStatus.PROVISIONING]
            )

            if not pending_workers:
                actions.append(ScaleUpAction(
                    template=template,
                    reason=f"Instance {instance.id} approaching timeslot with no capacity",
                    estimated_ready_time=datetime.now() + timedelta(minutes=WORKER_BOOTUP_DELAY_MINUTES)
                ))

    return actions
```

#### 2.3.2 Scale-Down Logic

> **IMPORTANT:** Workers should enter DRAINING state before scale-down to allow running instances to complete gracefully.

```python
SCALE_DOWN_GRACE_PERIOD_MINUTES = 30  # Don't scale down if work approaching


def check_scale_down_candidates() -> list[ScaleDownAction]:
    """
    Identify workers eligible for scale-down.

    Process:
    1. Find idle workers (no running instances)
    2. Check for upcoming scheduled work
    3. Transition to DRAINING (not immediate stop)
    4. DRAINING workers complete existing work, accept no new assignments
    5. When DRAINING worker is empty -> STOPPING -> STOPPED
    """
    actions = []

    for worker in get_workers_in_state(states=[WorkerStatus.RUNNING]):
        # Check if worker has any active instances
        active_instances = get_instances_on_worker(
            worker_id=worker.id,
            states=[
                InstanceState.RUNNING,
                InstanceState.COLLECTING,
                InstanceState.GRADING
            ]
        )

        if active_instances:
            continue  # Worker is active, cannot scale down

        # Check if worker has upcoming scheduled instances
        scheduled_instances = get_instances_on_worker(
            worker_id=worker.id,
            states=[
                InstanceState.SCHEDULED,
                InstanceState.INSTANTIATING
            ]
        )

        if scheduled_instances:
            continue  # Worker has pending work

        # Check approaching timeslots (any instance scheduled to this worker)
        approaching = get_approaching_instances_for_worker(
            worker_id=worker.id,
            lookahead_minutes=SCALE_DOWN_GRACE_PERIOD_MINUTES
        )

        if approaching:
            continue  # Work coming soon

        # Worker is idle - candidate for scale-down
        # Prefer DRAINING transition over immediate stop
        actions.append(ScaleDownAction(
            worker_id=worker.id,
            action=ScaleDownActionType.DRAIN,  # Start draining, not immediate stop
            reason="No running or scheduled instances"
        ))

    # Also check DRAINING workers that can be stopped
    for worker in get_workers_in_state(states=[WorkerStatus.DRAINING]):
        instances_on_worker = get_instances_on_worker(
            worker_id=worker.id,
            states=ACTIVE_INSTANCE_STATES
        )

        if not instances_on_worker:
            # DRAINING worker with no instances -> stop it
            actions.append(ScaleDownAction(
                worker_id=worker.id,
                action=ScaleDownActionType.STOP,
                reason="Draining complete, no remaining instances"
            ))

    return actions
```

#### 2.3.3 Worker State Machine with DRAINING

```
                                    ┌─────────────────┐
                                    │                 │
                                    ▼                 │
┌─────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────┐
│ PENDING │───▶│ PROVISIONING│───▶│ RUNNING  │───▶│ DRAINING │
└─────────┘    └─────────────┘    └──────────┘    └──────────┘
                                        │              │
                                        │              │ All instances
                                        │              │ completed
                                        ▼              ▼
                                  ┌──────────┐    ┌──────────┐
                                  │ STOPPING │◀───│ (empty)  │
                                  └──────────┘    └──────────┘
                                        │
                                        ▼
                                  ┌──────────┐
                                  │ STOPPED  │
                                  └──────────┘
                                        │
                                        ▼
                                  ┌────────────┐
                                  │ TERMINATED │
                                  └────────────┘
```

**DRAINING State Behavior:**

- Continues running existing LabletInstances
- Does NOT accept new instance assignments (Scheduler skips)
- Transitions to STOPPING when last instance terminates
- Has configurable timeout (default 4 hours) after which force-stop

---

### 2.4 Cloud Provider SPI

**Responsibility:** Abstract cloud-specific operations behind a common interface.

```
┌─────────────────────────────────────────────────────────────────┐
│                   CLOUD PROVIDER SPI                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 ICloudProviderAdapter                     │  │
│  │                 (Abstract Interface)                      │  │
│  │                                                           │  │
│  │  + create_instance(template) -> InstanceId                │  │
│  │  + start_instance(instance_id) -> None                    │  │
│  │  + stop_instance(instance_id) -> None                     │  │
│  │  + terminate_instance(instance_id) -> None                │  │
│  │  + get_instance_status(instance_id) -> Status             │  │
│  │  + get_instance_metrics(instance_id) -> Metrics           │  │
│  │  + list_instances(filters) -> list[Instance]              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            △                                    │
│                            │                                    │
│            ┌───────────────┼───────────────┐                   │
│            │               │               │                   │
│  ┌─────────┴────┐  ┌───────┴─────┐  ┌──────┴──────┐           │
│  │ AWS EC2      │  │ GCP Compute │  │ Azure VMs   │           │
│  │ Adapter      │  │ Adapter     │  │ Adapter     │           │
│  │ (Implemented)│  │ (Future)    │  │ (Future)    │           │
│  └──────────────┘  └─────────────┘  └─────────────┘           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Domain Model

### 3.1 Aggregate Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                        DOMAIN MODEL                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐         ┌────────────────────┐         │
│  │  LabletDefinition  │ 1     * │  LabletInstance    │         │
│  │  (Aggregate Root)  │────────▶│  (Aggregate Root)  │         │
│  │                    │         │                    │         │
│  │  • id              │         │  • id              │         │
│  │  • name            │         │  • definition_id   │         │
│  │  • version         │         │  • definition_ver  │         │
│  │  • lab_artifact_uri│         │  • worker_id       │─────┐   │
│  │  • resource_reqs   │         │  • state           │     │   │
│  │  • license_affinity│         │  • allocated_ports │     │   │
│  │  • port_template   │         │  • timeslot_start  │     │   │
│  │  • grading_rules   │         │  • timeslot_end    │     │   │
│  │  • warm_pool_depth │         │  • owner_id        │     │   │
│  └────────────────────┘         │  • grading_score   │     │   │
│                                 └────────────────────┘     │   │
│                                                            │   │
│                                          ┌─────────────────┘   │
│                                          │                     │
│                                          ▼ *                   │
│  ┌────────────────────┐         ┌────────────────────┐         │
│  │  WorkerTemplate    │ 1     * │  CMLWorker         │         │
│  │  (Value Object)    │────────▶│  (Aggregate Root)  │         │
│  │                    │         │  [EXTENDED]        │         │
│  │  • name            │         │                    │         │
│  │  • instance_type   │         │  • id              │         │
│  │  • capacity        │         │  • template_name   │         │
│  │  • license_type    │         │  • status          │         │
│  │  • ami_pattern     │         │  • capacity        │         │
│  │  • region          │         │  • allocated_cap   │         │
│  │  • port_range      │         │  • port_allocations│         │
│  └────────────────────┘         │  • instance_ids[]  │         │
│                                 └────────────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 LabletDefinition Aggregate

```python
@dataclass
class LabletDefinitionState(AggregateState[str]):
    """State for LabletDefinition aggregate."""

    id: str
    name: str
    version: str  # Semantic version

    # Artifact reference
    lab_artifact_uri: str  # S3/MinIO path
    lab_yaml_hash: str     # SHA-256 for change detection
    lab_yaml_cached: str | None  # Cached YAML content

    # Resource requirements
    resource_requirements: ResourceRequirements
    license_affinity: list[LicenseType]
    node_count: int

    # Port configuration
    port_template: PortTemplate  # Template with placeholders

    # Assessment integration
    grading_rules_uri: str | None
    max_duration_minutes: int

    # Warm pool
    warm_pool_depth: int

    # Ownership
    owner_notification: NotificationConfig | None
    created_by: str
    created_at: datetime


@dataclass
class ResourceRequirements:
    cpu_cores: int
    memory_gb: int
    storage_gb: int
    nested_virt: bool
    ami_requirements: list[AmiRequirement] | None


@dataclass
class PortTemplate:
    """Template for port allocation with placeholders."""
    ports: list[PortDefinition]

    # Example: [{"name": "serial_1", "protocol": "tcp"}, {"name": "vnc_1", "protocol": "tcp"}]


class LabletDefinition(AggregateRoot[LabletDefinitionState, str]):
    """LabletDefinition aggregate - immutable per version."""

    @staticmethod
    def create(
        name: str,
        version: str,
        lab_artifact_uri: str,
        resource_requirements: ResourceRequirements,
        license_affinity: list[LicenseType],
        port_template: PortTemplate,
        created_by: str,
        **kwargs
    ) -> "LabletDefinition":
        """Create a new LabletDefinition."""
        definition = LabletDefinition()
        definition.record_event(LabletDefinitionCreatedDomainEvent(
            aggregate_id=str(uuid4()),
            name=name,
            version=version,
            lab_artifact_uri=lab_artifact_uri,
            resource_requirements=resource_requirements,
            license_affinity=license_affinity,
            port_template=port_template,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            **kwargs
        ))
        return definition
```

### 3.3 LabletInstance Aggregate

```python
class LabletInstanceState(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    INSTANTIATING = "instantiating"
    RUNNING = "running"
    COLLECTING = "collecting"
    GRADING = "grading"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ARCHIVED = "archived"
    TERMINATED = "terminated"


@dataclass
class LabletInstanceState(AggregateState[str]):
    """State for LabletInstance aggregate."""

    id: str
    definition_id: str
    definition_version: str  # Pinned at creation

    # Assignment
    worker_id: str | None
    allocated_ports: dict[str, int] | None  # {"serial_1": 5041, "vnc_1": 5044}
    cml_lab_id: str | None  # Lab ID in CML after import

    # Lifecycle
    state: LabletInstanceState
    state_history: list[StateTransition]

    # Timeslot
    timeslot_start: datetime
    timeslot_end: datetime

    # Ownership
    owner_id: str
    reservation_id: str | None  # External reservation reference

    # Assessment
    grading_score: GradingScore | None

    # Timestamps
    created_at: datetime
    scheduled_at: datetime | None
    started_at: datetime | None
    terminated_at: datetime | None


class LabletInstance(AggregateRoot[LabletInstanceState, str]):
    """LabletInstance aggregate - runtime lifecycle."""

    def schedule(self, worker_id: str, allocated_ports: dict[str, int]) -> None:
        """Assign instance to worker with port allocation."""
        if self.state.state != LabletInstanceState.PENDING:
            raise InvalidStateTransition(f"Cannot schedule from {self.state.state}")

        self.record_event(LabletInstanceScheduledDomainEvent(
            aggregate_id=self.id(),
            worker_id=worker_id,
            allocated_ports=allocated_ports,
            scheduled_at=datetime.now(timezone.utc)
        ))

    def start_instantiation(self) -> None:
        """Begin lab import and startup."""
        if self.state.state != LabletInstanceState.SCHEDULED:
            raise InvalidStateTransition(f"Cannot instantiate from {self.state.state}")

        self.record_event(LabletInstanceInstantiatingDomainEvent(
            aggregate_id=self.id()
        ))

    def mark_running(self, cml_lab_id: str) -> None:
        """Mark instance as running after lab starts."""
        self.record_event(LabletInstanceRunningDomainEvent(
            aggregate_id=self.id(),
            cml_lab_id=cml_lab_id,
            started_at=datetime.now(timezone.utc)
        ))

    def start_collection(self) -> None:
        """Transition to collecting state."""
        if self.state.state != LabletInstanceState.RUNNING:
            raise InvalidStateTransition(f"Cannot collect from {self.state.state}")

        self.record_event(LabletInstanceCollectingDomainEvent(
            aggregate_id=self.id()
        ))

    def record_grading_result(self, score: GradingScore) -> None:
        """Record grading result and transition to stopping."""
        self.record_event(LabletInstanceGradedDomainEvent(
            aggregate_id=self.id(),
            score=score
        ))
```

### 3.4 CMLWorker Extensions

The existing `CMLWorker` aggregate needs extensions for capacity tracking:

```python
@dataclass
class WorkerCapacity:
    """Capacity specification for a worker."""
    cpu_cores: int
    memory_gb: int
    storage_gb: int
    max_nodes: int  # License-based limit


@dataclass
class PortAllocation:
    """Port allocation on a worker."""
    instance_id: str
    ports: dict[str, int]  # {"serial_1": 5041, "vnc_1": 5044}
    allocated_at: datetime


# Extensions to CMLWorkerState
class CMLWorkerState(AggregateState[str]):
    # ... existing fields ...

    # NEW: Capacity management
    template_name: str | None  # Reference to WorkerTemplate
    declared_capacity: WorkerCapacity
    allocated_capacity: WorkerCapacity  # Sum of running instances

    # NEW: Port management
    port_range_start: int  # 2000
    port_range_end: int    # 9999
    port_allocations: list[PortAllocation]

    # NEW: Instance tracking
    instance_ids: list[str]  # Currently assigned instances

    @property
    def available_capacity(self) -> WorkerCapacity:
        """Calculate remaining available capacity."""
        return WorkerCapacity(
            cpu_cores=self.declared_capacity.cpu_cores - self.allocated_capacity.cpu_cores,
            memory_gb=self.declared_capacity.memory_gb - self.allocated_capacity.memory_gb,
            storage_gb=self.declared_capacity.storage_gb - self.allocated_capacity.storage_gb,
            max_nodes=self.declared_capacity.max_nodes - self.allocated_capacity.max_nodes
        )

    @property
    def available_ports(self) -> int:
        """Calculate remaining available ports."""
        used_ports = sum(len(a.ports) for a in self.port_allocations)
        total_ports = self.port_range_end - self.port_range_start + 1
        return total_ports - used_ports
```

---

## 4. Data Flows

### 4.1 Reservation Request Flow

```
┌─────────┐          ┌───────────────┐          ┌───────────┐
│ Client  │          │ Control Plane │          │ Scheduler │
│         │          │     API       │          │  Service  │
└────┬────┘          └───────┬───────┘          └─────┬─────┘
     │                       │                        │
     │ POST /api/v1/instances│                        │
     │ {definition_id,       │                        │
     │  timeslot_start, ...} │                        │
     │──────────────────────▶│                        │
     │                       │                        │
     │                       │ Create Instance        │
     │                       │ (PENDING state)        │
     │                       │────────┐               │
     │                       │        │               │
     │                       │◀───────┘               │
     │                       │                        │
     │                       │ Emit: InstanceCreated  │
     │                       │───────────────────────▶│
     │                       │                        │
     │ 201 Created           │                        │
     │ {instance_id, state:  │                        │
     │  "pending"}           │                        │
     │◀──────────────────────│                        │
     │                       │                        │
     │                       │                        │ Scheduling
     │                       │                        │ Loop Runs
     │                       │                        │─────┐
     │                       │                        │     │ Find
     │                       │                        │     │ Worker
     │                       │                        │◀────┘
     │                       │                        │
     │                       │ POST /internal/schedule│
     │                       │ {instance_id, worker_id│
     │                       │  allocated_ports}      │
     │                       │◀───────────────────────│
     │                       │                        │
     │                       │ Update Instance        │
     │                       │ (SCHEDULED state)      │
     │                       │────────┐               │
     │                       │        │               │
     │                       │◀───────┘               │
     │                       │                        │
     │ SSE: InstanceScheduled│                        │
     │◀──────────────────────│                        │
     │                       │                        │
```

### 4.2 Instance Instantiation Flow

```
┌─────────┐      ┌───────────┐      ┌──────────┐      ┌──────────┐
│Resource │      │ Control   │      │ CML      │      │Artifact  │
│Controller      │ Plane API │      │ Worker   │      │Storage   │
└────┬────┘      └─────┬─────┘      └────┬─────┘      └────┬─────┘
     │                 │                 │                 │
     │ Reconcile Loop  │                 │                 │
     │ (Approaching    │                 │                 │
     │  Timeslot)      │                 │                 │
     │────────────────▶│                 │                 │
     │                 │                 │                 │
     │ Get Instance    │                 │                 │
     │◀────────────────│                 │                 │
     │                 │                 │                 │
     │ Get Definition  │                 │                 │
     │◀────────────────│                 │                 │
     │                 │                 │                 │
     │                 │                 │      Download   │
     │                 │                 │      Lab YAML   │
     │────────────────────────────────────────────────────▶│
     │                 │                 │                 │
     │◀─────────────────────────────────────Lab YAML──────│
     │                 │                 │                 │
     │ Rewrite YAML    │                 │                 │
     │ (Port mapping)  │                 │                 │
     │────────┐        │                 │                 │
     │        │        │                 │                 │
     │◀───────┘        │                 │                 │
     │                 │                 │                 │
     │ POST /internal/ │                 │                 │
     │ transition      │                 │                 │
     │ (INSTANTIATING) │                 │                 │
     │────────────────▶│                 │                 │
     │                 │                 │                 │
     │                 │ Import Lab YAML │                 │
     │                 │────────────────▶│                 │
     │                 │                 │                 │
     │                 │ Lab ID          │                 │
     │                 │◀────────────────│                 │
     │                 │                 │                 │
     │                 │ Start Lab       │                 │
     │                 │────────────────▶│                 │
     │                 │                 │                 │
     │                 │ Lab Started     │                 │
     │                 │◀────────────────│                 │
     │                 │                 │                 │
     │ POST /internal/ │                 │                 │
     │ transition      │                 │                 │
     │ (RUNNING)       │                 │                 │
     │────────────────▶│                 │                 │
     │                 │                 │                 │
     │                 │ Emit CloudEvent:│                 │
     │                 │ instance.running│                 │
     │                 │─────────────────│▶ (to Assessment)│
     │                 │                 │                 │
```

### 4.3 Port Rewriting Process

```python
def rewrite_lab_yaml(
    lab_yaml: str,
    port_template: PortTemplate,
    allocated_ports: dict[str, int]
) -> str:
    """
    Rewrite lab YAML with allocated ports.

    Template placeholders in smart_annotations:
      tag: serial:${PORT_SERIAL_1}

    Becomes:
      tag: serial:5041
    """
    import yaml

    lab_data = yaml.safe_load(lab_yaml)

    # Build placeholder -> port mapping
    port_map = {}
    for port_def in port_template.ports:
        placeholder = f"${{{port_def.name.upper()}}}"
        port_map[placeholder] = allocated_ports[port_def.name]

    # Rewrite smart_annotations
    for annotation in lab_data.get("smart_annotations", []):
        tag = annotation.get("tag", "")
        for placeholder, port in port_map.items():
            if placeholder in tag:
                annotation["tag"] = tag.replace(placeholder, str(port))
                annotation["label"] = annotation["label"].replace(placeholder, str(port))

    # Also rewrite node tags
    for node in lab_data.get("nodes", []):
        new_tags = []
        for tag in node.get("tags", []):
            for placeholder, port in port_map.items():
                tag = tag.replace(placeholder, str(port))
            new_tags.append(tag)
        node["tags"] = new_tags

    return yaml.dump(lab_data)
```

---

## 5. CloudEvents Schema

> **See [ADR-003: CloudEvents for External Integration](./adr/ADR-003-cloudevents-for-integration.md) for rationale.**

**Important:** CloudEvents are emitted for **external integration and audit** - they are NOT the primary persistence mechanism. State is persisted in etcd/MongoDB; events are a side-effect for subscribers.

### 5.1 Complete Event Catalog

#### 5.1.1 LabletDefinition Events

| Event Type | Trigger | Purpose |
|------------|---------|---------|
| `ccm.lablet.definition.created` | New definition registered | Notify consumers of new lab type |
| `ccm.lablet.definition.version.created` | New version detected | Version management, cache invalidation |
| `ccm.lablet.definition.deprecated` | Definition marked deprecated | Prevent new instances |

#### 5.1.2 LabletInstance Lifecycle Events (All States)

| Event Type | Trigger | Purpose |
|------------|---------|---------|
| `ccm.lablet.instance.pending` | Instance created | Audit: request received |
| `ccm.lablet.instance.scheduled` | Worker assigned | Audit: placement decision made |
| `ccm.lablet.instance.provisioning.started` | Lab import begins | Audit: instantiation starting |
| `ccm.lablet.instance.running` | Lab started successfully | **Assessment integration**: session ready |
| `ccm.lablet.instance.collecting.started` | Collection triggered | **Assessment integration**: begin collection |
| `ccm.lablet.instance.grading.started` | Grading in progress | **Assessment integration**: grading active |
| `ccm.lablet.instance.grading.completed` | Grading finished | **Assessment integration**: score available |
| `ccm.lablet.instance.stopping` | Stop initiated | Audit: teardown starting |
| `ccm.lablet.instance.stopped` | Lab stopped | Audit: lab inactive |
| `ccm.lablet.instance.archived` | Resources cleaned | Audit: ready for deletion |
| `ccm.lablet.instance.terminated` | Instance deleted | Audit: final state |

#### 5.1.3 Worker Lifecycle Events

| Event Type | Trigger | Purpose |
|------------|---------|---------|
| `ccm.worker.pending` | Scale-up initiated | Audit: worker requested |
| `ccm.worker.provisioning.started` | EC2 instance launching | Audit: cloud API called |
| `ccm.worker.running` | Worker ready for workload | Capacity management |
| `ccm.worker.draining` | Scale-down initiated | Capacity: no new assignments |
| `ccm.worker.stopping` | Worker shutdown started | Audit: EC2 stop in progress |
| `ccm.worker.stopped` | Worker stopped | Cost: compute paused |
| `ccm.worker.terminated` | Worker deleted | Audit: resources released |

#### 5.1.4 Scaling Events

| Event Type | Trigger | Purpose |
|------------|---------|---------|
| `ccm.scaling.up.requested` | Capacity shortage detected | Operations alerting |
| `ccm.scaling.up.completed` | New worker ready | Capacity confirmation |
| `ccm.scaling.down.requested` | Idle worker detected | Cost optimization tracking |
| `ccm.scaling.down.completed` | Worker stopped/terminated | Cost confirmation |

### 5.2 Event Payload Examples

```yaml
# ccm.lablet.instance.pending (NEW - was missing)
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.pending",
  "source": "ccm/api",
  "id": "evt-12345",
  "time": "2026-01-15T10:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "instance_id": "inst-abc123",
    "definition_id": "def-xyz789",
    "definition_version": "1.2.0",
    "owner_id": "user-456",
    "reservation_id": "res-789",
    "timeslot_start": "2026-01-15T11:00:00Z",
    "timeslot_end": "2026-01-15T12:00:00Z",
    "created_at": "2026-01-15T10:30:00Z"
  }
}

# ccm.lablet.instance.provisioning.started (NEW - was missing)
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.provisioning.started",
  "source": "ccm/controller",
  "id": "evt-12346",
  "time": "2026-01-15T10:35:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "worker_id": "worker-def456",
    "allocated_ports": {
      "serial_1": 5041,
      "vnc_1": 5044
    },
    "lab_yaml_hash": "sha256:abc123..."
  }
}

# ccm.lablet.instance.running
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.running",
  "source": "ccm/controller",
  "id": "evt-12347",
  "time": "2026-01-15T10:45:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "worker_id": "worker-def456",
    "worker_hostname": "worker-def456.internal",
    "cml_lab_id": "lab-ghi789",
    "allocated_ports": {
      "serial_1": 5041,
      "serial_2": 5042,
      "vnc_1": 5044
    },
    "started_at": "2026-01-15T10:45:00Z"
  }
}

# ccm.lablet.instance.collecting.started (NEW - was missing)
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.collecting.started",
  "source": "ccm/api",
  "id": "evt-12348",
  "time": "2026-01-15T11:50:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "triggered_by": "user-456",  // or "system" for auto-collection
    "collection_reason": "manual"  // or "timeslot_end", "assessment_request"
  }
}

# ccm.lablet.instance.grading.started (NEW - was missing)
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.grading.started",
  "source": "ccm/controller",
  "id": "evt-12349",
  "time": "2026-01-15T11:52:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "grading_engine_session_id": "grade-session-xyz"
  }
}

# ccm.lablet.instance.grading.completed
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.grading.completed",
  "source": "ccm/controller",
  "id": "evt-12350",
  "time": "2026-01-15T12:00:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "score": {
      "total": 85,
      "max": 100,
      "passed": true,
      "breakdown": [
        {"criterion": "Task 1", "points": 25, "max": 30},
        {"criterion": "Task 2", "points": 30, "max": 30},
        {"criterion": "Task 3", "points": 30, "max": 40}
      ]
    },
    "grading_duration_seconds": 120
  }
}

# ccm.lablet.instance.terminated
{
  "specversion": "1.0",
  "type": "ccm.lablet.instance.terminated",
  "source": "ccm/controller",
  "id": "evt-12355",
  "time": "2026-01-15T12:05:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "final_state": "archived",
    "grading_score": {
      "total": 85,
      "max": 100,
      "passed": true
    },
    "duration_minutes": 55
  }
}

# ccm.worker.draining (NEW - for scale-down visibility)
{
  "specversion": "1.0",
  "type": "ccm.worker.draining",
  "source": "ccm/controller",
  "id": "evt-worker-drain-1",
  "time": "2026-01-15T13:00:00Z",
  "data": {
    "worker_id": "worker-def456",
    "reason": "scale_down_idle",
    "running_instances_count": 2,
    "estimated_drain_completion": "2026-01-15T14:00:00Z"
  }
}
```

### 5.3 Events Consumed by CCM

```yaml
# assessment.collection.completed (from Assessment Platform)
{
  "specversion": "1.0",
  "type": "assessment.collection.completed",
  "source": "assessment-platform",
  "id": "evt-assess-collect-1",
  "time": "2026-01-15T11:51:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "collection_id": "coll-123",
    "artifacts_uri": "s3://bucket/collections/coll-123/"
  }
}

# assessment.grading.completed (from Grading Engine)
{
  "specversion": "1.0",
  "type": "assessment.grading.completed",
  "source": "grading-engine",
  "id": "evt-assess-789",
  "time": "2026-01-15T12:02:00Z",
  "data": {
    "instance_id": "inst-abc123",
    "score": {
      "total": 85,
      "max": 100,
      "breakdown": [
        {"criterion": "Task 1", "points": 25, "max": 30},
        {"criterion": "Task 2", "points": 30, "max": 30},
        {"criterion": "Task 3", "points": 30, "max": 40}
      ]
    },
    "passed": true
  }
}
```

---

## 6. Deployment Architecture

### 6.1 Component Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                    KUBERNETES CLUSTER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Ingress Controller                       │ │
│  └───────────────────────────┬────────────────────────────────┘ │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐     │
│  │ Control     │      │ Scheduler   │      │ Resource    │     │
│  │ Plane API   │      │ Service     │      │ Controller  │     │
│  │ (3 replicas)│      │ (2 replicas)│      │ (2 replicas)│     │
│  └──────┬──────┘      └─────────────┘      └─────────────┘     │
│         │             (Leader election)   (Leader election)    │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      etcd (State Store)                      ││
│  │                      (3-node cluster)                        ││
│  │  • Instance/Worker state  • Leader election  • Watches      ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    MongoDB (Spec Store)                      ││
│  │                    (3-node replica set)                      ││
│  │  • LabletDefinitions  • WorkerTemplates  • Audit events     ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Redis (UI Session Store)                  ││
│  │  • User authentication sessions (httpOnly cookies)          ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    cloud-streams (CloudEvents)               ││
│  │  • Event persistence for audit/analytics                    ││
│  │  • External integration (Assessment Platform)               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Keycloak │  │ S3/MinIO │  │ OTEL     │  │ Assessment    │   │
│  │          │  │          │  │ Collector│  │ Platform      │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Scaling Configuration

| Component | Min Replicas | Max Replicas | Scaling Metric |
|-----------|--------------|--------------|----------------|
| Control Plane API | 2 | 10 | CPU 70% |
| Scheduler Service | 2 | 5 | Custom (queue depth) |
| Resource Controller | 2 | 3 | N/A (leader election) |

---

## 7. Implementation Phases

### Phase 1: Foundation (Weeks 1-4)

- [ ] Define LabletDefinition aggregate and repository
- [ ] Define LabletInstance aggregate and repository
- [ ] Extend CMLWorker with capacity tracking
- [ ] Implement basic CRUD APIs
- [ ] Implement port allocation service

### Phase 2: Scheduling (Weeks 5-8)

- [ ] Implement Scheduler Service (basic placement)
- [ ] Implement timeslot management
- [ ] Implement lab YAML rewriting
- [ ] Implement instantiation flow
- [ ] Add SSE updates for instance state

### Phase 3: Auto-Scaling (Weeks 9-12)

- [ ] Implement Resource Controller
- [ ] Implement scale-up logic
- [ ] Implement scale-down logic
- [ ] Implement Cloud Provider SPI (AWS)
- [ ] Add worker template configuration

### Phase 4: Assessment Integration (Weeks 13-16)

- [ ] Implement CloudEvent publishing
- [ ] Implement CloudEvent consumption
- [ ] Integrate collection/grading states
- [ ] Add grading result handling

### Phase 5: Production Hardening (Weeks 17-20)

- [ ] Add comprehensive observability
- [ ] Implement warm pool (if needed)
- [ ] Performance testing
- [ ] Documentation
- [ ] UI integration

---

## 8. Architectural Decisions Record

All architectural decisions are documented in the [ADR folder](./adr/README.md).

### Current ADRs

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](./adr/ADR-001-api-centric-state-management.md) | API-Centric State Management | Accepted |
| [ADR-002](./adr/ADR-002-separate-scheduler-service.md) | Separate Scheduler Service | Accepted |
| [ADR-003](./adr/ADR-003-cloudevents-for-integration.md) | CloudEvents for External Integration | Accepted |
| [ADR-004](./adr/ADR-004-port-allocation-per-worker.md) | Port Allocation per Worker | Accepted |
| [ADR-005](./adr/ADR-005-state-store-architecture.md) | Dual State Store Architecture (etcd + MongoDB) | Proposed |
| [ADR-006](./adr/ADR-006-scheduler-ha-coordination.md) | Scheduler High Availability Coordination | Proposed |
| [ADR-007](./adr/ADR-007-worker-template-seeding.md) | Worker Template Seeding and Management | Accepted |
| [ADR-008](./adr/ADR-008-worker-draining-state.md) | Worker Draining State for Scale-Down | Proposed |

---

## 9. Assessment Integration: Pod Generation

> Based on the Grading Engine API schema (`docs/grading-engine_openapi.json`).

### 9.0 Integration Configuration

**Authentication:** JWT tokens from shared Keycloak instance (same IDP as CCM).

**Deployment:** Grading Engine can be deployed in the same docker-compose stack for development/testing.

```yaml
# docker-compose.yml (example addition)
services:
  grading-engine:
    image: grading-engine:latest
    environment:
      - KEYCLOAK_URL=http://keycloak:8080
      - KEYCLOAK_REALM=cml-cloud-manager
      - KEYCLOAK_CLIENT_ID=grading-engine
    depends_on:
      - keycloak
```

### 9.1 Pod Schema Mapping

The Grading Engine expects a **Pod** definition when assigning lab resources to an assessment session:

```json
// Grading Engine Pod Schema (confirmed)
{
  "id": "string",
  "devices": [
    {
      "label": "string",
      "hostname": "string",
      "collector": "string",
      "interfaces": [
        {
          "name": "string",
          "protocol": "string",  // ssh, telnet, console, vnc
          "host": "string",      // Worker IP/hostname
          "port": 5041,          // Allocated port
          "authentication": {},   // Credentials object
          "configuration": {}     // Protocol-specific config
        }
      ]
    }
  ]
}
```

### 9.2 CML Lab → Pod Mapping

When a LabletInstance reaches RUNNING state, CCM generates a Pod definition from:

1. **CML Lab YAML** (nodes with smart_annotations)
2. **Allocated Ports** (from Scheduler)
3. **Worker Details** (hostname/IP)

```python
def generate_pod_from_lablet(
    instance: LabletInstance,
    worker: CMLWorker,
    definition: LabletDefinition
) -> Pod:
    """
    Generate Grading Engine Pod from running LabletInstance.

    Mapping:
    - CML node → Pod device
    - smart_annotation serial:PORT → interface (protocol=console)
    - smart_annotation vnc:PORT → interface (protocol=vnc)
    """
    lab_yaml = yaml.safe_load(definition.lab_yaml_cached)

    devices = []
    for node in lab_yaml.get("nodes", []):
        device = Device(
            label=node["label"],
            hostname=node["label"],  # Or extract from node config
            collector="ccm",  # Collection agent identifier
            interfaces=[]
        )

        # Extract interfaces from node tags
        for tag in node.get("tags", []):
            if tag.startswith("serial:"):
                port = int(tag.split(":")[1])
                device.interfaces.append(DeviceInterface(
                    name=f"console-{node['label']}",
                    protocol="console",
                    host=worker.state.hostname,
                    port=port,
                    authentication={"type": "none"},  # CML console auth
                ))
            elif tag.startswith("vnc:"):
                port = int(tag.split(":")[1])
                device.interfaces.append(DeviceInterface(
                    name=f"vnc-{node['label']}",
                    protocol="vnc",
                    host=worker.state.hostname,
                    port=port,
                    authentication={"type": "vnc_password"},
                ))

        if device.interfaces:  # Only include nodes with external interfaces
            devices.append(device)

    return Pod(
        id=instance.id,
        devices=devices
    )
```

### 9.3 Pod Assignment Flow

```
CCM                              Grading Engine
 │                                    │
 │ Instance reaches RUNNING state     │
 │────────────────────────────────────│
 │                                    │
 │ Generate Pod from Lab YAML         │
 │────────┐                           │
 │        │                           │
 │◀───────┘                           │
 │                                    │
 │ POST /api/v1/sessions/{id}/parts/{partId}/pod
 │ { pod: {...} }                     │
 │───────────────────────────────────▶│
 │                                    │
 │         202 Accepted               │
 │◀───────────────────────────────────│
 │                                    │
 │ CloudEvent: ccm.lablet.instance.running
 │ { pod_assigned: true }             │
 │───────────────────────────────────▶│
```

---

## 10. Open Questions for Implementation

### Resolved

1. ~~**Warm Pool Priority:** Should warm pool implementation be deferred?~~
   → **Deferred** to later optimization phase

2. ~~**Worker Template Management:** Should templates be stored in MongoDB or configuration files?~~
   → **Both**: MongoDB aggregate seeded from config files (see [ADR-007](./adr/ADR-007-worker-template-seeding.md))

3. ~~**Multi-Region Strategy:** How to handle region-specific worker templates?~~
   → **Regional isolation**: One CCM deployment per region, no cross-region coordination

4. ~~**etcd vs MongoDB-only**: Should we prototype with MongoDB Change Streams first?~~
   → **No**, proceed with dual store (etcd + MongoDB) - see [ADR-005](./adr/ADR-005-state-store-architecture.md)

5. ~~**Drain timeout configuration**: Should drain timeout be per-worker-template or global?~~
   → **Per-template**: `drain_timeout_hours` attribute on WorkerTemplate (see [ADR-008](./adr/ADR-008-worker-draining-state.md))

6. ~~**Grading Engine integration**: Confirm Pod assignment API endpoint and authentication?~~
   → **Confirmed**: Device/Interface schema validated, JWT auth on shared Keycloak instance

7. ~~**Audit Log Retention:** How long should CloudEvents be retained?~~
   → **Minimum 3 months, maximum 1 year** (NFR-3.5.5)

8. ~~**Cost estimation**: Should terminated events include cost estimates?~~
   → **No**, cost estimation NOT included in event payload

### Open

None - all questions resolved.

---

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-15 | Architecture Team | Initial draft |
| 0.2.0 | 2026-01-15 | Architecture Team | Incorporated feedback: dual store architecture (etcd+MongoDB), worker DRAINING state, scale timing delays, separated ADRs to `/docs/architecture/adr/`, added intermediate CloudEvents, HA coordination with leader election, Pod generation for Grading Engine integration |
| 0.3.0 | 2026-01-16 | Architecture Team | Resolved all open questions: confirmed dual DB approach, drain timeout per-template with admin cancel + instance retry, Grading Engine JWT auth confirmed, audit retention 3mo-1yr, no cost in events |
