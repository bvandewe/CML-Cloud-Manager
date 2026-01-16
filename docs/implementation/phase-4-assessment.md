# Phase 4: Assessment Integration

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Duration** | Weeks 13-16 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |
| **Prerequisites** | [Phase 3](./phase-3-autoscaling.md) complete |

---

## 1. Phase Objectives

- Implement CloudEvent publishing for all lifecycle events
- Implement CloudEvent consumption (assessment.*.completed)
- Implement COLLECTING and GRADING states
- Implement grading result handling
- Implement Pod generation for Grading Engine
- Integration with external Assessment Platform

---

## 2. Task Breakdown

### Week 13: CloudEvent Publishing

#### Task 4.1: CloudEvents SDK Integration (1 day)

**Files to Create:**

```
src/integration/services/cloudevents_publisher.py
src/integration/models/cloud_event.py
tests/unit/integration/services/test_cloudevents_publisher.py
```

**Acceptance Criteria:**

- [ ] CloudEventsPublisher service using cloudevents SDK
- [ ] Configure sink URL from settings
- [ ] HTTP POST with CloudEvents format
- [ ] Retry logic with exponential backoff
- [ ] Async publishing (non-blocking)
- [ ] Unit tests with mocked HTTP

**Implementation:**

```python
from cloudevents.http import CloudEvent, to_structured


class CloudEventsPublisher:
    """Publishes CloudEvents to configured sink."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._sink_url = settings.CLOUDEVENTS_SINK_URL
        self._source = settings.CLOUDEVENTS_SOURCE
        self._http = http_client

    async def publish_async(
        self,
        event_type: str,
        data: dict,
        subject: str | None = None
    ) -> None:
        """Publish a CloudEvent to the sink."""
        if not self._sink_url:
            logger.debug(f"CloudEvents sink not configured, skipping {event_type}")
            return

        event = CloudEvent({
            "type": event_type,
            "source": self._source,
            "subject": subject,
            "datacontenttype": "application/json",
        }, data)

        headers, body = to_structured(event)
        await self._http.post(self._sink_url, headers=headers, content=body)
```

**Dependencies:** Prerequisites (cloudevents package)

**Effort Estimate:** 1 day

---

#### Task 4.2: Instance Lifecycle Event Publishers (2 days)

**Files to Create:**

```
src/application/services/instance_event_publisher.py
tests/unit/application/services/test_instance_event_publisher.py
```

**Acceptance Criteria:**

- [ ] Publish event on each instance state transition
- [ ] Event types per architecture spec:
  - `ccm.lablet.instance.pending`
  - `ccm.lablet.instance.scheduled`
  - `ccm.lablet.instance.provisioning.started`
  - `ccm.lablet.instance.running`
  - `ccm.lablet.instance.collecting.started`
  - `ccm.lablet.instance.grading.started`
  - `ccm.lablet.instance.grading.completed`
  - `ccm.lablet.instance.stopping`
  - `ccm.lablet.instance.stopped`
  - `ccm.lablet.instance.archived`
  - `ccm.lablet.instance.terminated`
- [ ] Include all required data per event schema
- [ ] Unit tests for each event type

**Integration with Domain Events:**

```python
class InstanceEventPublisher:
    """Publishes CloudEvents for instance state changes."""

    async def on_instance_state_changed(
        self,
        instance: LabletInstance,
        old_state: LabletInstanceState,
        new_state: LabletInstanceState
    ) -> None:
        """Called when instance state changes."""
        event_type = f"ccm.lablet.instance.{new_state.value}"

        data = {
            "instance_id": instance.id(),
            "definition_id": instance.state.definition_id,
            "definition_version": instance.state.definition_version,
            "previous_state": old_state.value,
            "new_state": new_state.value,
            "worker_id": instance.state.worker_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Add state-specific data
        if new_state == LabletInstanceState.RUNNING:
            data["allocated_ports"] = instance.state.allocated_ports
            data["cml_lab_id"] = instance.state.cml_lab_id

        await self._publisher.publish_async(event_type, data, subject=instance.id())
```

**Dependencies:** Task 4.1

**Effort Estimate:** 2 days

---

#### Task 4.3: Worker & Scaling Event Publishers (2 days)

**Files to Create:**

```
src/application/services/worker_event_publisher.py
src/application/services/scaling_event_publisher.py
tests/unit/application/services/test_worker_event_publisher.py
```

**Acceptance Criteria:**

- [ ] Worker lifecycle events:
  - `ccm.worker.pending`
  - `ccm.worker.provisioning.started`
  - `ccm.worker.running`
  - `ccm.worker.draining`
  - `ccm.worker.stopping`
  - `ccm.worker.stopped`
  - `ccm.worker.terminated`
- [ ] Scaling events:
  - `ccm.scaling.up.requested`
  - `ccm.scaling.up.completed`
  - `ccm.scaling.down.requested`
  - `ccm.scaling.down.completed`
- [ ] Unit tests for each event type

**Dependencies:** Task 4.1

**Effort Estimate:** 2 days

---

### Week 14: CloudEvent Consumption

#### Task 4.4: CloudEvent Consumer Service (2 days)

**Files to Create:**

```
src/api/controllers/cloudevents_controller.py
src/application/services/cloudevent_handler.py
tests/integration/test_cloudevent_consumption.py
```

**Acceptance Criteria:**

- [ ] HTTP endpoint for receiving CloudEvents
- [ ] Parse and validate CloudEvent format
- [ ] Route to appropriate handler by event type
- [ ] Idempotent processing (deduplication)
- [ ] Integration tests

**Endpoint:**

```python
@router.post("/api/v1/events")
async def receive_cloudevent(request: Request):
    """Receive CloudEvents from external systems."""
    event = from_http(request.headers, await request.body())

    await handler.handle_async(event)

    return Response(status_code=202)
```

**Dependencies:** Task 4.1

**Effort Estimate:** 2 days

---

#### Task 4.5: Assessment Event Handlers (2 days)

**Files to Create:**

```
src/application/services/assessment_event_handler.py
src/application/commands/complete_collection_command.py
src/application/commands/complete_grading_command.py
tests/unit/application/services/test_assessment_event_handler.py
```

**Acceptance Criteria:**

- [ ] Handle `assessment.collection.completed` event
  - Transition instance to GRADING state
- [ ] Handle `assessment.grading.completed` event
  - Store grading score
  - Transition instance to STOPPING state
- [ ] Validate event data
- [ ] Error handling for invalid events
- [ ] Unit tests for handlers

**Handler Implementation:**

```python
class AssessmentEventHandler:
    """Handles events from Assessment Platform."""

    async def handle_collection_completed(
        self,
        event_data: dict
    ) -> None:
        """Handle assessment.collection.completed event."""
        instance_id = event_data["instance_id"]

        command = TransitionInstanceCommand(
            instance_id=instance_id,
            target_state=LabletInstanceState.GRADING
        )
        await self._mediator.execute_async(command)

    async def handle_grading_completed(
        self,
        event_data: dict
    ) -> None:
        """Handle assessment.grading.completed event."""
        instance_id = event_data["instance_id"]
        score = GradingScore.from_dict(event_data["score"])

        command = CompleteGradingCommand(
            instance_id=instance_id,
            score=score
        )
        await self._mediator.execute_async(command)
```

**Dependencies:** Task 4.4

**Effort Estimate:** 2 days

---

#### Task 4.6: Event Deduplication (1 day)

**Files to Create:**

```
src/application/services/event_deduplication_service.py
tests/unit/application/services/test_event_deduplication.py
```

**Acceptance Criteria:**

- [ ] Track processed event IDs
- [ ] Store in etcd with TTL (e.g., 24 hours)
- [ ] Skip duplicate events
- [ ] Unit tests

**Implementation:**

```python
class EventDeduplicationService:
    """Prevents duplicate event processing."""

    async def is_processed(self, event_id: str) -> bool:
        """Check if event was already processed."""
        key = f"/ccm/events/processed/{event_id}"
        return await self._etcd.get(key) is not None

    async def mark_processed(self, event_id: str, ttl_hours: int = 24) -> None:
        """Mark event as processed with TTL."""
        key = f"/ccm/events/processed/{event_id}"
        await self._etcd.put(key, "1", ttl=ttl_hours * 3600)
```

**Dependencies:** Task 4.4

**Effort Estimate:** 1 day

---

### Week 15: Collection & Grading States

#### Task 4.7: Collection Trigger Command (2 days)

**Files to Create:**

```
src/application/commands/trigger_collection_command.py
src/application/services/collection_service.py
tests/unit/application/services/test_collection_service.py
```

**Acceptance Criteria:**

- [ ] POST /api/v1/instances/{id}/collect endpoint
- [ ] Transition instance to COLLECTING state
- [ ] Call external Assessment API to initiate collection
- [ ] Handle collection errors
- [ ] Unit tests

**Collection Flow:**

```python
class CollectionService:
    """Triggers collection for LabletInstance."""

    async def trigger_collection_async(
        self,
        instance_id: str,
        triggered_by: str,
        reason: str = "manual"
    ) -> OperationResult[None]:
        """
        Trigger collection for an instance.

        1. Validate instance is in RUNNING state
        2. Transition to COLLECTING
        3. Call Assessment Platform API
        4. Publish ccm.lablet.instance.collecting.started event
        """
        instance = await self._repo.get_by_id_async(instance_id)

        if instance.state.state != LabletInstanceState.RUNNING:
            return self.bad_request("Instance must be RUNNING to collect")

        # Transition state
        instance.start_collection()
        await self._repo.update_async(instance)

        # Call Assessment Platform
        await self._assessment_client.trigger_collection(
            instance_id=instance_id,
            cml_lab_id=instance.state.cml_lab_id,
            worker_hostname=await self._get_worker_hostname(instance)
        )

        # Publish event
        await self._event_publisher.publish_collection_started(instance, triggered_by, reason)

        return self.accepted(None)
```

**Dependencies:** Phase 1 Instance state machine

**Effort Estimate:** 2 days

---

#### Task 4.8: Grading Result Handler (1 day)

**Files to Create:**

```
src/application/commands/record_grading_result_command.py
tests/unit/application/commands/test_record_grading_result_command.py
```

**Acceptance Criteria:**

- [ ] Store grading score on instance
- [ ] Transition to STOPPING state
- [ ] Validate score data
- [ ] Unit tests

**Implementation:**

```python
@dataclass
class RecordGradingResultCommand(Command[OperationResult[None]]):
    instance_id: str
    score: GradingScore


class RecordGradingResultCommandHandler(CommandHandler[...]):
    async def handle_async(self, request, ct=None):
        instance = await self._repo.get_by_id_async(request.instance_id, ct)

        if instance is None:
            return self.not_found("Instance", request.instance_id)

        if instance.state.state != LabletInstanceState.GRADING:
            return self.bad_request("Instance must be in GRADING state")

        instance.record_grading_result(request.score)
        await self._repo.update_async(instance, ct)

        return self.ok(None)
```

**Dependencies:** Task 4.5

**Effort Estimate:** 1 day

---

#### Task 4.9: Auto-Stop After Grading (1 day)

**Files to Modify:**

```
src/application/services/instance_reconciler.py (extend)
```

**Acceptance Criteria:**

- [ ] Detect instances in STOPPING state after grading
- [ ] Stop lab on CML worker
- [ ] Transition to STOPPED then ARCHIVED
- [ ] Release resources
- [ ] Unit tests

**Dependencies:** Task 4.8

**Effort Estimate:** 1 day

---

### Week 16: Pod Generation & Integration

#### Task 4.10: Pod Generation Service (2 days)

**Files to Create:**

```
src/application/services/pod_generation_service.py
src/application/models/grading_pod.py
tests/unit/application/services/test_pod_generation_service.py
```

**Acceptance Criteria:**

- [ ] Generate Pod from running LabletInstance
- [ ] Map CML nodes to Pod devices
- [ ] Map smart_annotations to interfaces (serial:, vnc:)
- [ ] Include worker hostname and allocated ports
- [ ] Validate against Grading Engine schema
- [ ] Unit tests with sample lab YAMLs

**Pod Generation:**

```python
@dataclass
class DeviceInterface:
    name: str
    protocol: str  # console, vnc, ssh, telnet
    host: str
    port: int
    authentication: dict
    configuration: dict = field(default_factory=dict)


@dataclass
class Device:
    label: str
    hostname: str
    collector: str
    interfaces: list[DeviceInterface]


@dataclass
class Pod:
    id: str
    devices: list[Device]


class PodGenerationService:
    """Generates Grading Engine Pod from LabletInstance."""

    def generate_pod(
        self,
        instance: LabletInstance,
        definition: LabletDefinition,
        worker: CMLWorker
    ) -> Pod:
        """
        Generate Pod definition for Grading Engine.

        Mapping:
        - CML node → Device
        - smart_annotation serial:PORT → interface (protocol=console)
        - smart_annotation vnc:PORT → interface (protocol=vnc)
        """
        lab_yaml = yaml.safe_load(definition.state.lab_yaml_cached)

        devices = []
        for node in lab_yaml.get("nodes", []):
            interfaces = self._extract_interfaces(
                node,
                instance.state.allocated_ports,
                worker.state.public_ip or worker.state.private_ip
            )

            if interfaces:
                devices.append(Device(
                    label=node["label"],
                    hostname=node["label"],
                    collector="ccm",
                    interfaces=interfaces
                ))

        return Pod(id=instance.id(), devices=devices)
```

**Dependencies:** Phase 1 aggregates

**Effort Estimate:** 2 days

---

#### Task 4.11: Assessment Platform Client (2 days)

**Files to Create:**

```
src/integration/services/assessment_platform_client.py
tests/integration/test_assessment_platform_client.py
```

**Acceptance Criteria:**

- [ ] HTTP client for Assessment Platform API
- [ ] Authentication via JWT (shared Keycloak)
- [ ] Methods:
  - `trigger_collection(instance_id, ...)`
  - `assign_pod(session_id, part_id, pod)`
- [ ] Retry logic and error handling
- [ ] Integration tests with mocked API

**Implementation:**

```python
class AssessmentPlatformClient:
    """Client for Assessment Platform API."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self._base_url = settings.ASSESSMENT_PLATFORM_URL
        self._http = http_client

    async def assign_pod(
        self,
        session_id: str,
        part_id: str,
        pod: Pod
    ) -> None:
        """Assign Pod to assessment session."""
        url = f"{self._base_url}/api/v1/sessions/{session_id}/parts/{part_id}/pod"

        response = await self._http.post(
            url,
            json={"pod": asdict(pod)},
            headers=await self._get_auth_headers()
        )
        response.raise_for_status()

    async def trigger_collection(
        self,
        instance_id: str,
        cml_lab_id: str,
        worker_hostname: str
    ) -> None:
        """Trigger collection for instance."""
        url = f"{self._base_url}/api/v1/collections"

        response = await self._http.post(
            url,
            json={
                "instance_id": instance_id,
                "cml_lab_id": cml_lab_id,
                "worker_hostname": worker_hostname
            },
            headers=await self._get_auth_headers()
        )
        response.raise_for_status()
```

**Dependencies:** Prerequisites (Keycloak)

**Effort Estimate:** 2 days

---

#### Task 4.12: Assessment Integration Tests (1 day)

**Files to Create:**

```
tests/integration/test_assessment_e2e.py
```

**Acceptance Criteria:**

- [ ] End-to-end test: RUNNING → COLLECTING → GRADING → STOPPED
- [ ] CloudEvent publishing verified
- [ ] CloudEvent consumption verified
- [ ] Pod generation verified
- [ ] All tests pass in CI

**Dependencies:** All Phase 4 tasks

**Effort Estimate:** 1 day

---

## 3. Dependencies Graph

```
Week 13                 Week 14                 Week 15                 Week 16
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌─────────┐
│ Task 4.1│──────────▶│ Task 4.4│            │ Task 4.7│            │Task 4.10│
│CloudEvts│            │ Consumer│            │Collect  │            │ Pod Gen │
│ SDK     │            │ Service │            │ Trigger │            │ Service │
└────┬────┘            └────┬────┘            └────┬────┘            └─────────┘
     │                      │                      │                      │
     ▼                      ▼                      │                      │
┌─────────┐            ┌─────────┐            ┌────┴────┐            ┌─────────┐
│ Task 4.2│            │ Task 4.5│            │ Task 4.8│            │Task 4.11│
│ Instance│            │ Assess  │            │ Grading │            │ Assess  │
│ Events  │            │ Handlers│            │ Result  │            │ Client  │
└────┬────┘            └────┬────┘            └────┬────┘            └────┬────┘
     │                      │                      │                      │
     ▼                      ▼                      ▼                      │
┌─────────┐            ┌─────────┐            ┌─────────┐            ┌────┴────┐
│ Task 4.3│            │ Task 4.6│            │ Task 4.9│            │Task 4.12│
│ Worker  │            │ Dedup   │            │Auto-Stop│            │ Integ   │
│ Events  │            │ Service │            │         │            │ Tests   │
└─────────┘            └─────────┘            └─────────┘            └─────────┘
```

---

## 4. Test Coverage Requirements

| Component | Unit Tests | Integration Tests | Target Coverage |
|-----------|------------|-------------------|-----------------|
| CloudEvents Publisher | Yes | - | ≥85% |
| Instance Event Publisher | Yes | - | ≥90% |
| CloudEvent Handler | Yes | Yes | ≥85% |
| Assessment Handlers | Yes | - | ≥90% |
| Collection Service | Yes | - | ≥85% |
| Pod Generation | Yes | - | ≥95% |
| Assessment Client | Yes | Yes (mocked) | ≥80% |

---

## 5. Phase 4 Acceptance Criteria

### Functional

- [ ] CloudEvents published for all instance state transitions
- [ ] CloudEvents published for worker lifecycle events
- [ ] CloudEvents received and processed from Assessment Platform
- [ ] COLLECTING state triggers assessment collection
- [ ] GRADING state receives and stores score
- [ ] Pod generated correctly from running instance
- [ ] Pod assigned to Assessment Platform session

### Non-Functional

- [ ] CloudEvent publishing non-blocking (< 100ms)
- [ ] Event deduplication prevents reprocessing
- [ ] Assessment API calls retry on failure
- [ ] All events conform to CloudEvents spec 1.0

### Documentation

- [ ] CloudEvents schema documented
- [ ] Assessment integration guide
- [ ] Event flow diagrams updated
- [ ] Troubleshooting for event issues

---

## 6. Risks & Mitigations (Phase 4 Specific)

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Assessment Platform unavailable | Medium | Medium | Retry logic, circuit breaker |
| Event ordering issues | Medium | Low | Event timestamps, idempotent handlers |
| Pod schema mismatch | High | Low | Schema validation, versioning |
| Keycloak token expiry | Low | Medium | Token refresh before expiry |

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
