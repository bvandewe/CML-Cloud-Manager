# Phase 5: Production Hardening

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Duration** | Weeks 17-20 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |
| **Prerequisites** | [Phase 4](./phase-4-assessment.md) complete |

---

## 1. Phase Objectives

- Implement comprehensive observability (traces, metrics, logs)
- Conduct performance testing and optimization
- Create operational documentation and runbooks
- Integrate with UI (Bootstrap 5 SPA)
- Implement warm pool (optional, if needed)
- Prepare for production deployment

---

## 2. Task Breakdown

### Week 17: Observability

#### Task 5.1: OpenTelemetry Tracing (2 days)

**Files to Modify:**

```
src/main.py (add OTEL instrumentation)
src/application/services/*.py (add spans)
```

**Files to Create:**

```
src/infrastructure/observability/tracing.py
```

**Acceptance Criteria:**

- [ ] Traces for all API endpoints
- [ ] Traces for scheduling decisions
- [ ] Traces for instantiation flow
- [ ] Traces for CloudEvent publishing/consumption
- [ ] Correlation IDs across services
- [ ] Export to OTEL Collector

**Tracing Setup:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_tracing(settings: Settings) -> None:
    """Configure OpenTelemetry tracing."""
    provider = TracerProvider(resource=Resource.create({
        "service.name": "ccm",
        "service.version": settings.APP_VERSION,
    }))

    if settings.OTEL_EXPORTER_ENDPOINT:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(
                endpoint=settings.OTEL_EXPORTER_ENDPOINT
            ))
        )

    trace.set_tracer_provider(provider)


# Usage in services
tracer = trace.get_tracer(__name__)

class SchedulerService:
    async def _process_pending_instances(self):
        with tracer.start_as_current_span("scheduler.process_pending") as span:
            instances = await self._get_pending_instances()
            span.set_attribute("instance.count", len(instances))
            # ...
```

**Dependencies:** Prerequisites (OTEL Collector)

**Effort Estimate:** 2 days

---

#### Task 5.2: Prometheus Metrics (2 days)

**Files to Create:**

```
src/infrastructure/observability/metrics.py
src/api/middleware/metrics_middleware.py
```

**Acceptance Criteria:**

- [ ] Business metrics:
  - `ccm_lablet_instances_total` (counter by state)
  - `ccm_lablet_instances_active` (gauge)
  - `ccm_workers_total` (counter by state)
  - `ccm_workers_active` (gauge)
  - `ccm_scheduling_decisions_total` (counter)
  - `ccm_scaling_actions_total` (counter by action)
- [ ] Technical metrics:
  - `ccm_api_request_duration_seconds` (histogram)
  - `ccm_instantiation_duration_seconds` (histogram)
  - `ccm_scheduler_loop_duration_seconds` (histogram)
- [ ] Prometheus endpoint `/metrics`

**Metrics Definition:**

```python
from prometheus_client import Counter, Gauge, Histogram


# Business metrics
lablet_instances_total = Counter(
    "ccm_lablet_instances_total",
    "Total LabletInstances created",
    ["definition_id", "final_state"]
)

lablet_instances_active = Gauge(
    "ccm_lablet_instances_active",
    "Currently active LabletInstances",
    ["state", "worker_id"]
)

workers_active = Gauge(
    "ccm_workers_active",
    "Currently active workers",
    ["state", "template"]
)

scheduling_decisions = Counter(
    "ccm_scheduling_decisions_total",
    "Scheduling decisions made",
    ["action"]  # assign, scale_up, wait
)

scaling_actions = Counter(
    "ccm_scaling_actions_total",
    "Scaling actions taken",
    ["action", "template"]  # scale_up, drain, stop, terminate
)

# Technical metrics
api_request_duration = Histogram(
    "ccm_api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint", "status"]
)

instantiation_duration = Histogram(
    "ccm_instantiation_duration_seconds",
    "LabletInstance instantiation duration",
    ["definition_id"]
)
```

**Dependencies:** None

**Effort Estimate:** 2 days

---

#### Task 5.3: Structured Logging (1 day)

**Files to Modify:**

```
src/main.py (configure logging)
src/application/services/*.py (add structured fields)
```

**Files to Create:**

```
src/infrastructure/observability/logging.py
```

**Acceptance Criteria:**

- [ ] JSON formatted logs in production
- [ ] Correlation ID in all log entries
- [ ] Standard fields: timestamp, level, service, trace_id
- [ ] Contextual fields: instance_id, worker_id, user_id
- [ ] Log level configurable via settings

**Logging Configuration:**

```python
import structlog


def configure_logging(settings: Settings) -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.LOG_FORMAT == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper())
        ),
    )


# Usage
logger = structlog.get_logger()

async def schedule_instance(instance_id: str):
    logger.info(
        "scheduling_instance",
        instance_id=instance_id,
        definition_id=instance.state.definition_id
    )
```

**Dependencies:** None

**Effort Estimate:** 1 day

---

### Week 18: Performance Testing

#### Task 5.4: Load Testing Setup (2 days)

**Files to Create:**

```
tests/performance/locustfile.py
tests/performance/scenarios/
tests/performance/README.md
```

**Acceptance Criteria:**

- [ ] Locust load testing framework setup
- [ ] Scenarios:
  - Create 100 instances concurrently
  - Schedule 50 instances to 10 workers
  - Query instances with pagination
- [ ] Performance baseline documented
- [ ] CI integration for regression testing

**Locust Scenario:**

```python
from locust import HttpUser, task, between


class LabletAPIUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def create_instance(self):
        self.client.post("/api/v1/instances", json={
            "definition_id": "test-def-1",
            "timeslot_start": "2026-01-20T10:00:00Z",
            "timeslot_end": "2026-01-20T12:00:00Z",
            "owner_id": f"user-{self.user_id}"
        })

    @task(5)
    def list_instances(self):
        self.client.get("/api/v1/instances?page=1&size=50")

    @task(2)
    def get_instance(self):
        self.client.get(f"/api/v1/instances/{self.instance_id}")
```

**Dependencies:** All core features complete

**Effort Estimate:** 2 days

---

#### Task 5.5: Performance Optimization (3 days)

**Files to Modify:**

```
src/integration/repositories/*.py (query optimization)
src/application/services/*.py (caching, batching)
```

**Acceptance Criteria:**

- [ ] API response time p95 < 500ms (NFR-3.1.1)
- [ ] Scheduling decision time < 5s (NFR-3.1.2)
- [ ] Instantiation time < 3 min (NFR-3.1.3)
- [ ] Support 1000+ concurrent instances (NFR-3.1.4)
- [ ] MongoDB indexes optimized
- [ ] etcd key structure optimized

**Optimization Areas:**

```python
# MongoDB index optimization
# Add to repository initialization
await collection.create_index([
    ("state.state", 1),
    ("state.timeslot_start", 1)
], name="instance_scheduling_idx")

await collection.create_index([
    ("state.worker_id", 1),
    ("state.state", 1)
], name="instance_worker_state_idx")

# Query optimization: Use projection
async def list_instances_async(self, filters, page, size):
    cursor = self._collection.find(
        filters,
        projection={"state.lab_yaml_cached": 0}  # Exclude large field
    ).skip((page - 1) * size).limit(size)

    return await cursor.to_list(length=size)

# Batching for etcd watches
async def batch_update_states(self, updates: list[tuple[str, str]]):
    """Batch state updates for efficiency."""
    async with self._etcd.txn() as txn:
        for instance_id, state in updates:
            txn.put(f"/ccm/instances/{instance_id}/state", state)
```

**Dependencies:** Task 5.4

**Effort Estimate:** 3 days

---

### Week 19: Documentation & UI

#### Task 5.6: Operational Runbooks (2 days)

**Files to Create:**

```
docs/operations/runbooks/
docs/operations/runbooks/scheduler-troubleshooting.md
docs/operations/runbooks/scaling-operations.md
docs/operations/runbooks/etcd-operations.md
docs/operations/runbooks/instance-recovery.md
```

**Acceptance Criteria:**

- [ ] Scheduler troubleshooting runbook
- [ ] Scaling operations runbook
- [ ] etcd cluster operations runbook
- [ ] Instance recovery procedures
- [ ] Alerting thresholds defined

**Runbook Template:**

```markdown
# Runbook: Scheduler Troubleshooting

## Symptoms
- Instances stuck in PENDING state
- Scheduler not making placement decisions

## Diagnosis
1. Check scheduler leader status
2. Check etcd connectivity
3. Check worker availability

## Resolution Steps
1. ...
2. ...

## Escalation
If unresolved after 30 minutes, escalate to...
```

**Dependencies:** None

**Effort Estimate:** 2 days

---

#### Task 5.7: API Documentation (1 day)

**Files to Modify:**

```
src/api/controllers/*.py (enhance docstrings)
```

**Files to Create:**

```
docs/api/lablet-api-guide.md
```

**Acceptance Criteria:**

- [ ] OpenAPI spec complete and accurate
- [ ] API guide with examples
- [ ] Authentication instructions
- [ ] Error response documentation
- [ ] Rate limiting documentation

**Dependencies:** All API endpoints complete

**Effort Estimate:** 1 day

---

#### Task 5.8: UI Integration - Instance Management (2 days)

**Files to Create:**

```
src/ui/src/js/pages/lablet-instances.js
src/ui/src/js/components/instance-card.js
src/ui/src/js/components/instance-state-badge.js
```

**Acceptance Criteria:**

- [ ] Instance list view with filtering
- [ ] Instance detail view
- [ ] State badge with color coding
- [ ] Real-time updates via SSE
- [ ] Create instance form
- [ ] Terminate instance action

**UI Component:**

```javascript
// Instance state badge component
class InstanceStateBadge extends HTMLElement {
    static get observedAttributes() {
        return ['state'];
    }

    attributeChangedCallback(name, oldValue, newValue) {
        if (name === 'state') {
            this.render(newValue);
        }
    }

    render(state) {
        const colors = {
            'pending': 'secondary',
            'scheduled': 'info',
            'instantiating': 'warning',
            'running': 'success',
            'collecting': 'primary',
            'grading': 'primary',
            'stopping': 'warning',
            'stopped': 'secondary',
            'terminated': 'dark'
        };

        this.innerHTML = `
            <span class="badge bg-${colors[state] || 'secondary'}">
                ${state.toUpperCase()}
            </span>
        `;
    }
}

customElements.define('instance-state-badge', InstanceStateBadge);
```

**Dependencies:** Phase 1-4 APIs complete

**Effort Estimate:** 2 days

---

#### Task 5.9: UI Integration - Definition Management (1 day)

**Files to Create:**

```
src/ui/src/js/pages/lablet-definitions.js
src/ui/src/js/components/definition-card.js
```

**Acceptance Criteria:**

- [ ] Definition list view
- [ ] Definition detail view with versions
- [ ] Create definition form
- [ ] Sync artifact action

**Dependencies:** Task 5.8

**Effort Estimate:** 1 day

---

### Week 20: Final Integration & Release Prep

#### Task 5.10: End-to-End Integration Tests (2 days)

**Files to Create:**

```
tests/e2e/test_full_lifecycle.py
tests/e2e/test_scaling_scenarios.py
tests/e2e/test_assessment_flow.py
```

**Acceptance Criteria:**

- [ ] Full instance lifecycle test (create → terminate)
- [ ] Multi-instance scheduling test
- [ ] Scale-up/down scenario test
- [ ] Assessment integration test
- [ ] All E2E tests pass in CI

**Dependencies:** All features complete

**Effort Estimate:** 2 days

---

#### Task 5.11: Security Review (1 day)

**Files to Review:**

```
src/api/controllers/*.py
src/api/dependencies.py
src/application/services/*.py
```

**Acceptance Criteria:**

- [ ] All endpoints require authentication
- [ ] RBAC enforced appropriately
- [ ] Input validation complete
- [ ] No sensitive data in logs
- [ ] Secrets properly managed
- [ ] Security checklist completed

**Dependencies:** All features complete

**Effort Estimate:** 1 day

---

#### Task 5.12: Release Documentation (1 day)

**Files to Create/Update:**

```
CHANGELOG.md (update)
README.md (update)
docs/deployment/production-checklist.md
docs/deployment/upgrade-guide.md
```

**Acceptance Criteria:**

- [ ] CHANGELOG updated with all new features
- [ ] README reflects new capabilities
- [ ] Production deployment checklist
- [ ] Upgrade guide from previous version
- [ ] Release notes drafted

**Dependencies:** All features complete

**Effort Estimate:** 1 day

---

#### Task 5.13: Warm Pool Implementation (Optional, 2 days)

**Files to Create:**

```
src/application/services/warm_pool_service.py
src/application/jobs/warm_pool_replenishment_job.py
tests/unit/application/services/test_warm_pool_service.py
```

**Acceptance Criteria:**

- [ ] Maintain warm pool per LabletDefinition
- [ ] Pre-import labs in STOPPED state
- [ ] Start warm lab instead of importing new
- [ ] Replenish pool after consumption
- [ ] Configurable pool depth per definition

**Note:** This task is optional and should be implemented only if performance testing (Task 5.5) indicates instantiation time is a bottleneck.

**Dependencies:** All core features complete

**Effort Estimate:** 2 days (if needed)

---

## 3. Dependencies Graph

```
Week 17                 Week 18                 Week 19                 Week 20
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 5.1│            │ Task 5.4│            │ Task 5.6│            │Task 5.10│
│ Tracing │            │ Load    │            │ Runbooks│            │ E2E     │
│         │            │ Testing │            │         │            │ Tests   │
└────┬────┘            └────┬────┘            └─────────┘            └────┬────┘
     │                      │                      │                      │
     ▼                      ▼                      │                      │
┌─────────┐            ┌─────────┐            ┌────┴────┐            ┌────┴────┐
│ Task 5.2│            │ Task 5.5│            │ Task 5.7│            │Task 5.11│
│ Metrics │            │ Perf    │            │ API Docs│            │ Security│
│         │            │ Optim   │            │         │            │ Review  │
└────┬────┘            └─────────┘            └─────────┘            └────┬────┘
     │                                             │                      │
     ▼                                             ▼                      │
┌─────────┐                                  ┌─────────┐            ┌────┴────┐
│ Task 5.3│                                  │ Task 5.8│            │Task 5.12│
│ Logging │                                  │ UI Inst │            │ Release │
│         │                                  │ Mgmt    │            │ Docs    │
└─────────┘                                  └────┬────┘            └─────────┘
                                                  │
                                             ┌────┴────┐            ┌─────────┐
                                             │ Task 5.9│            │Task 5.13│
                                             │ UI Defn │            │Warm Pool│
                                             │ Mgmt    │            │(Optional│
                                             └─────────┘            └─────────┘
```

---

## 4. Test Coverage Requirements

| Component | Unit Tests | Integration Tests | Target Coverage |
|-----------|------------|-------------------|-----------------|
| Tracing | - | Yes | N/A |
| Metrics | Yes | Yes | ≥80% |
| Logging | - | Yes | N/A |
| Performance | - | Yes (load tests) | N/A |
| UI Components | - | Yes (E2E) | ≥70% |

---

## 5. Phase 5 Acceptance Criteria

### Functional

- [ ] All traces visible in Jaeger/OTEL backend
- [ ] Prometheus metrics scraped successfully
- [ ] Grafana dashboards functional
- [ ] UI shows instance and definition management
- [ ] All E2E tests pass

### Non-Functional

- [ ] API response time p95 < 500ms under load
- [ ] System handles 1000+ concurrent instances
- [ ] No memory leaks under sustained load
- [ ] Graceful degradation under overload

### Documentation

- [ ] Operational runbooks complete
- [ ] API documentation complete
- [ ] Deployment guide complete
- [ ] CHANGELOG updated

### Release Readiness

- [ ] Security review passed
- [ ] Performance benchmarks met
- [ ] All tests passing in CI
- [ ] Release notes drafted

---

## 6. Risks & Mitigations (Phase 5 Specific)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Performance issues at scale | High | Medium | Early load testing, profiling |
| UI complexity | Medium | Low | Use existing Bootstrap patterns |
| Documentation gaps | Medium | Medium | Dedicated documentation time |
| Security vulnerabilities | High | Low | Security review, penetration testing |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
