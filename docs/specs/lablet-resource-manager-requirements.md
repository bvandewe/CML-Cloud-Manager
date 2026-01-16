# Lablet Resource Manager - Requirements Specification

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-15 |
| **Last Updated** | 2026-01-15 |
| **Author** | Architecture Team |

---

## 1. Executive Summary

### 1.1 Vision

Transform CML Cloud Manager from an imperative EC2/CML management tool into a **Nearly Autonomous Lablet Resource Manager** with Kubernetes-like declarative resource management, intelligent scheduling, and auto-scaling capabilities.

### 1.2 Business Objectives

| Objective | Description | Success Metric |
|-----------|-------------|----------------|
| **Cost Optimization** | Minimize AWS compute costs through intelligent scheduling and auto-scaling | ≥30% reduction in idle worker time |
| **Scalability** | Support growing concurrent user base | Handle 1000+ concurrent LabletInstances |
| **Reliability** | Ensure exam/lab sessions are never disrupted | 99.9% session completion rate |
| **Automation** | Reduce manual intervention in resource management | ≥90% automated operations |

### 1.3 Scope

**In Scope:**

- Declarative LabletDefinition and LabletInstance lifecycle management
- Intelligent scheduling with time-windowed reservations
- Automatic Worker scaling (up/down) based on demand
- Integration with external assessment/grading systems
- Multi-license type support (Personal, Enterprise)
- CloudEvent-based integration for audit and assessment platforms

**Out of Scope (This Phase):**

- Multi-cloud provider support (AWS-only initially, SPI designed for future)
- Cross-region failover
- Real-time collaborative lab sessions
- Custom node definition management

---

## 2. Functional Requirements

### 2.1 LabletDefinition Management

#### FR-2.1.1: Definition CRUD Operations

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1.1a | System SHALL allow creation of LabletDefinitions via REST API | P0 |
| FR-2.1.1b | System SHALL store LabletDefinitions as immutable versioned aggregates | P0 |
| FR-2.1.1c | System SHALL support semantic versioning (MAJOR.MINOR.PATCH) | P0 |
| FR-2.1.1d | System SHALL auto-increment version on detected diff from artifact | P1 |
| FR-2.1.1e | System SHALL allow admin to override/rename version tags | P1 |

#### FR-2.1.2: Definition Attributes

A LabletDefinition SHALL include:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | UUID | Yes | Unique identifier |
| `name` | string | Yes | Human-readable name |
| `version` | semver | Yes | Semantic version (e.g., "1.2.3") |
| `lab_artifact_uri` | URI | Yes | S3/MinIO path to CML Lab YAML |
| `lab_yaml_hash` | string | Yes | SHA-256 of lab YAML content |
| `resource_requirements` | object | Yes | CPU, memory, storage needs |
| `license_affinity` | enum[] | Yes | Compatible license types |
| `node_count` | integer | Yes | Total nodes in lab topology |
| `port_template` | object | Yes | Port allocation template |
| `grading_rules_uri` | URI | No | Path to grading criteria |
| `warm_pool_depth` | integer | No | Pre-provisioned instance count |
| `max_duration_minutes` | integer | Yes | Maximum session duration |
| `owner_notification` | object | No | Contact info for crash notifications |
| `created_at` | datetime | Yes | Creation timestamp |
| `created_by` | string | Yes | Creator identity |

#### FR-2.1.3: Resource Requirements Schema

```yaml
resource_requirements:
  cpu_cores: 4          # Minimum CPU cores
  memory_gb: 8          # Minimum RAM in GB
  storage_gb: 50        # Minimum storage in GB
  nested_virt: true     # Requires nested virtualization
  ami_requirements:     # Optional AMI constraints
    - name_pattern: "CML-2.9.*"
    - min_version: "2.9.0"
```

#### FR-2.1.4: License Affinity

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1.4a | System SHALL support license types: `PERSONAL`, `ENTERPRISE`, `EVALUATION` | P0 |
| FR-2.1.4b | System SHALL validate node_count against license capacity at scheduling | P0 |
| FR-2.1.4c | Personal license: max 20 nodes | P0 |
| FR-2.1.4d | Enterprise license: unlimited nodes | P0 |

#### FR-2.1.5: Artifact Synchronization

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1.5a | System SHALL download lab YAML from S3/MinIO on demand | P0 |
| FR-2.1.5b | System SHALL detect changes via hash comparison | P0 |
| FR-2.1.5c | System SHALL prompt admin for version tag on detected diff | P1 |
| FR-2.1.5d | System SHALL cache downloaded artifacts locally | P2 |

---

### 2.2 LabletInstance Lifecycle

#### FR-2.2.1: Instance States

```
┌─────────┐    ┌───────────┐    ┌───────────────┐    ┌─────────┐
│ PENDING │───▶│ SCHEDULED │───▶│ INSTANTIATING │───▶│ RUNNING │
└─────────┘    └───────────┘    └───────────────┘    └─────────┘
                                                          │
                                                          ▼
┌────────────┐    ┌─────────┐    ┌───────────┐    ┌────────────┐
│ TERMINATED │◀───│ ARCHIVED│◀───│  STOPPED  │◀───│  STOPPING  │
└────────────┘    └─────────┘    └───────────┘    └────────────┘
                       ▲               ▲
                       │               │
                  ┌─────────┐    ┌───────────┐
                  │ GRADING │◀───│ COLLECTING│
                  └─────────┘    └───────────┘
```

| State | Description | Transitions To |
|-------|-------------|----------------|
| `PENDING` | Instance requested, awaiting scheduling | `SCHEDULED`, `TERMINATED` |
| `SCHEDULED` | Assigned to worker, awaiting timeslot | `INSTANTIATING`, `TERMINATED` |
| `INSTANTIATING` | Lab importing/starting on worker | `RUNNING`, `TERMINATED` |
| `RUNNING` | Lab active, user can interact | `COLLECTING`, `STOPPING` |
| `COLLECTING` | Gathering evidence from lab nodes | `GRADING`, `STOPPING` |
| `GRADING` | External grading engine processing | `STOPPING` |
| `STOPPING` | Lab stopping on worker | `STOPPED` |
| `STOPPED` | Lab stopped, resources held | `ARCHIVED`, `RUNNING` |
| `ARCHIVED` | Results stored, ready for cleanup | `TERMINATED` |
| `TERMINATED` | All resources released | (terminal) |

#### FR-2.2.2: Instance Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | UUID | Yes | Unique identifier |
| `definition_id` | UUID | Yes | Reference to LabletDefinition |
| `definition_version` | semver | Yes | Pinned definition version |
| `worker_id` | UUID | No | Assigned worker (null until scheduled) |
| `state` | enum | Yes | Current lifecycle state |
| `allocated_ports` | map | No | Port allocations (serial, vnc, etc.) |
| `timeslot_start` | datetime | Yes | Requested start time |
| `timeslot_end` | datetime | Yes | Maximum end time |
| `owner_id` | string | Yes | Requestor identity |
| `reservation_id` | UUID | No | Associated exam/session reservation |
| `grading_score` | object | No | Final grading result |
| `created_at` | datetime | Yes | Request timestamp |
| `started_at` | datetime | No | Actual start timestamp |
| `terminated_at` | datetime | No | Termination timestamp |

#### FR-2.2.3: Instance Operations

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.2.3a | System SHALL create instance via reservation request | P0 |
| FR-2.2.3b | System SHALL assign instance to worker with sufficient capacity | P0 |
| FR-2.2.3c | System SHALL allocate unique ports per instance on assigned worker | P0 |
| FR-2.2.3d | System SHALL rewrite lab YAML with allocated ports at instantiation | P0 |
| FR-2.2.3e | System SHALL import rewritten lab YAML to CML worker | P0 |
| FR-2.2.3f | System SHALL start lab after successful import | P0 |
| FR-2.2.3g | System SHALL track instance state transitions via domain events | P0 |

#### FR-2.2.4: Port Allocation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.2.4a | System SHALL allocate ports from range 2000-9999 per worker | P0 |
| FR-2.2.4b | System SHALL prevent port conflicts across instances on same worker | P0 |
| FR-2.2.4c | System SHALL rewrite `smart_annotations.tag` values with allocated ports | P0 |
| FR-2.2.4d | System SHALL release ports when instance reaches TERMINATED state | P0 |
| FR-2.2.4e | System SHALL track port allocations per worker | P0 |

**Port Rewriting Example:**

Template (in LabletDefinition):

```yaml
smart_annotations:
  - tag: serial:${PORT_SERIAL_1}
  - tag: vnc:${PORT_VNC_1}
```

Instantiated (per LabletInstance):

```yaml
smart_annotations:
  - tag: serial:5041
  - tag: vnc:5044
```

---

### 2.3 Scheduling & Reservations

#### FR-2.3.1: Reservation Request

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.3.1a | System SHALL accept reservation requests with timeslot specification | P0 |
| FR-2.3.1b | System SHALL support "ASAP" scheduling (earliest available) | P0 |
| FR-2.3.1c | System SHALL support future-dated scheduling | P0 |
| FR-2.3.1d | System SHALL queue reservations when no capacity available | P0 |
| FR-2.3.1e | System SHALL NOT preempt running instances for new reservations | P0 |

#### FR-2.3.2: Scheduling Algorithm

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.3.2a | Scheduler SHALL evaluate license affinity constraints | P0 |
| FR-2.3.2b | Scheduler SHALL evaluate resource requirements | P0 |
| FR-2.3.2c | Scheduler SHALL prefer workers with existing capacity (bin-packing) | P1 |
| FR-2.3.2d | Scheduler SHALL trigger scale-up when no suitable worker exists | P0 |
| FR-2.3.2e | Scheduler SHALL respect AMI requirements in definition | P1 |

#### FR-2.3.3: Scheduling Constraints

```
SCHEDULE(instance) WHERE:
  worker.license_type IN instance.definition.license_affinity
  AND worker.available_capacity >= instance.definition.resource_requirements
  AND worker.available_nodes >= instance.definition.node_count
  AND worker.ami MATCHES instance.definition.ami_requirements
  AND worker.available_ports >= instance.definition.port_count
```

---

### 2.4 Worker Capacity Management

#### FR-2.4.1: Capacity Model

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.4.1a | Worker capacity SHALL include: CPU cores, memory GB, storage GB | P0 |
| FR-2.4.1b | Worker capacity SHALL include: license type, max node count | P0 |
| FR-2.4.1c | Worker capacity SHALL be declared via Worker Template | P0 |
| FR-2.4.1d | Worker utilization SHALL be measured via CloudWatch + CML API | P0 |
| FR-2.4.1e | Available capacity = Declared capacity - Allocated capacity | P0 |

#### FR-2.4.2: Worker Template

```yaml
worker_template:
  name: "enterprise-large"
  instance_type: "m5zn.metal"
  capacity:
    cpu_cores: 48
    memory_gb: 192
    storage_gb: 500
  license_type: "ENTERPRISE"
  max_nodes: 500  # Enterprise = unlimited, but practical limit
  ami_pattern: "CML-2.9.*"
  region: "us-east-1"
  port_range:
    start: 2000
    end: 9999
```

#### FR-2.4.3: Capacity Tracking

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.4.3a | System SHALL track allocated capacity per running instance | P0 |
| FR-2.4.3b | System SHALL update available capacity on instance state changes | P0 |
| FR-2.4.3c | System SHALL track allocated ports per worker | P0 |
| FR-2.4.3d | System SHALL expose capacity metrics via API and SSE | P0 |

---

### 2.5 Auto-Scaling

#### FR-2.5.1: Scale-Up Triggers

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.5.1a | System SHALL scale up when scheduled instances approach timeslot with no capacity | P0 |
| FR-2.5.1b | System SHALL scale up when pending queue exceeds threshold | P1 |
| FR-2.5.1c | System SHALL select appropriate worker template based on pending requirements | P0 |
| FR-2.5.1d | System SHALL account for worker startup time (≤15 minutes) in scheduling | P0 |

#### FR-2.5.2: Scale-Down Triggers

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.5.2a | System SHALL scale down workers with no running instances | P0 |
| FR-2.5.2b | System SHALL scale down workers with no approaching scheduled instances | P0 |
| FR-2.5.2c | System SHALL prefer stopping over terminating (faster restart) | P1 |
| FR-2.5.2d | System SHALL consolidate instances to minimize running workers | P1 |

#### FR-2.5.3: Scaling Constraints

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.5.3a | System SHALL NOT scale down workers with active instances | P0 |
| FR-2.5.3b | System SHALL honor minimum warm capacity (configurable) | P1 |
| FR-2.5.3c | System SHALL log all scaling decisions for audit | P0 |

---

### 2.6 Assessment Integration

#### FR-2.6.1: Collection Process

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.6.1a | System SHALL expose API to trigger collection for an instance | P0 |
| FR-2.6.1b | System SHALL transition instance to COLLECTING state | P0 |
| FR-2.6.1c | System SHALL call external assessment API to initiate collection | P0 |
| FR-2.6.1d | Collection SHALL gather text output from lab node consoles | P0 |

#### FR-2.6.2: Grading Process

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.6.2a | System SHALL transition to GRADING after collection completes | P0 |
| FR-2.6.2b | External grading engine SHALL emit CloudEvent with score report | P0 |
| FR-2.6.2c | System SHALL receive and store grading results | P0 |
| FR-2.6.2d | System SHALL transition to STOPPING after grading completes | P0 |

#### FR-2.6.3: CloudEvent Integration

**Events Emitted by CCM:**

| Event Type | Trigger | Consumers |
|------------|---------|-----------|
| `ccm.lablet.instance.created` | Instance created | Assessment, Audit |
| `ccm.lablet.instance.running` | Lab started | Assessment |
| `ccm.lablet.instance.collecting` | Collection started | Assessment |
| `ccm.lablet.instance.terminated` | Resources released | Audit, Billing |
| `ccm.worker.scaled.up` | New worker started | Audit |
| `ccm.worker.scaled.down` | Worker stopped | Audit |

**Events Consumed by CCM:**

| Event Type | Source | Action |
|------------|--------|--------|
| `assessment.collection.completed` | Assessment Platform | Transition to GRADING |
| `assessment.grading.completed` | Grading Engine | Store score, transition to STOPPING |

---

### 2.7 Warm Pool (Pre-Provisioning)

#### FR-2.7.1: Warm Lablet Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.7.1a | System SHALL maintain warm pool per LabletDefinition (if configured) | P2 |
| FR-2.7.1b | Warm pool = labs imported and stopped (not started) | P2 |
| FR-2.7.1c | System SHALL start warm lab instead of importing new | P2 |
| FR-2.7.1d | System SHALL replenish warm pool after consumption | P2 |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-3.1.1 | API response time (p95) | < 500ms | P0 |
| NFR-3.1.2 | Scheduling decision time | < 5s | P0 |
| NFR-3.1.3 | Instance instantiation time | < 3min (excl. worker startup) | P0 |
| NFR-3.1.4 | Concurrent instances supported | ≥ 1000 | P0 |
| NFR-3.1.5 | Concurrent workers per region | ≥ 100 | P0 |

### 3.2 Availability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-3.2.1 | API availability | 99.9% | P0 |
| NFR-3.2.2 | Scheduler availability | 99.9% | P0 |
| NFR-3.2.3 | Recovery Time Objective (RTO) | < 2 minutes | P0 |
| NFR-3.2.4 | No single point of failure for control plane | Required | P0 |

### 3.3 Scalability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-3.3.1 | Horizontal scaling for API | Required | P0 |
| NFR-3.3.2 | Horizontal scaling for Scheduler | Required | P0 |
| NFR-3.3.3 | Worker startup time tolerance | ≤ 15 minutes | P0 |

### 3.4 Security

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-3.4.1 | All API endpoints require authentication | P0 |
| NFR-3.4.2 | RBAC for definition/instance operations | P0 |
| NFR-3.4.3 | Audit logging for all state changes | P0 |
| NFR-3.4.4 | Secrets (AWS credentials) encrypted at rest | P0 |

### 3.5 Observability

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-3.5.1 | OpenTelemetry traces for all operations | P0 |
| NFR-3.5.2 | Prometheus metrics for business KPIs | P0 |
| NFR-3.5.3 | Structured logging with correlation IDs | P0 |
| NFR-3.5.4 | Real-time SSE dashboard | P0 |
| NFR-3.5.5 | Audit log retention: minimum 3 months, maximum 1 year | P0 |

### 3.6 Maintainability

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-3.6.1 | Cloud Provider abstraction via SPI | P1 |
| NFR-3.6.2 | Configuration-driven worker templates | P0 |
| NFR-3.6.3 | Feature flags for gradual rollout | P2 |

---

## 4. Constraints & Assumptions

### 4.1 Constraints

| ID | Constraint |
|----|------------|
| C-1 | AWS m5zn.metal instances required (nested virtualization) |
| C-2 | Worker startup time: up to 15 minutes |
| C-3 | CML licenses are tied to individual workers |
| C-4 | Port range 2000-9999 per worker |
| C-5 | Initial deployment: AWS only (SPI for future multi-cloud) |

### 4.2 Assumptions

| ID | Assumption |
|----|------------|
| A-1 | External assessment platform provides REST API |
| A-2 | Grading engine emits CloudEvents |
| A-3 | Lab YAML artifacts managed externally in S3/MinIO |
| A-4 | Users book reservations in advance (not purely on-demand) |
| A-5 | Region isolation acceptable (no cross-region failover) |

---

## 5. Glossary

| Term | Definition |
|------|------------|
| **LabletDefinition** | Immutable, versioned template for a lab environment |
| **LabletInstance** | Runtime instance of a LabletDefinition on a Worker |
| **Worker** | AWS EC2 instance running CML (compute node) |
| **Timeslot** | Reserved time window for a LabletInstance |
| **Warm Pool** | Pre-provisioned (imported, stopped) labs for fast startup |
| **Capacity** | Available compute resources on a Worker |
| **License Affinity** | Constraint matching definitions to compatible license types |

---

## 6. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-15 | Architecture Team | Initial draft |
