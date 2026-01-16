# Testing Strategy

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |

---

## 1. Overview

This document defines the comprehensive testing strategy for the Lablet Resource Manager implementation across all phases.

### Testing Principles

1. **Test-Driven Development**: Write tests before implementation
2. **Layered Testing**: Unit → Integration → E2E pyramid
3. **Continuous Integration**: All tests run on every PR
4. **Coverage Targets**: Minimum 80% line coverage

---

## 2. Test Categories

### 2.1 Unit Tests

**Scope**: Individual functions, classes, and methods in isolation
**Framework**: pytest + pytest-asyncio
**Markers**: `@pytest.mark.unit`

**Target Coverage:**
| Layer | Target |
|-------|--------|
| Domain entities | 90% |
| Domain value objects | 95% |
| Application commands/queries | 85% |
| Application services | 85% |
| Utility functions | 90% |

**Example:**
```python
# tests/unit/domain/test_lablet_definition.py
@pytest.mark.unit
class TestLabletDefinition:
    def test_create_with_valid_topology(self):
        definition = LabletDefinition.create(
            name="test-definition",
            topology=TopologySpec(format=TopologyFormat.YAML, content="...")
        )
        assert definition.state.name == "test-definition"
        assert definition.state.status == LabletDefinitionStatus.DRAFT
    
    def test_create_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            LabletDefinition.create(name="", topology=...)
```

### 2.2 Integration Tests

**Scope**: Component interactions, database operations, external services
**Framework**: pytest + testcontainers (MongoDB, etcd, MinIO)
**Markers**: `@pytest.mark.integration`

**Target Coverage:**
| Component | Target |
|-----------|--------|
| Repositories | 80% |
| etcd state store | 85% |
| AWS client (mocked) | 80% |
| CML API client (mocked) | 80% |

**Example:**
```python
# tests/integration/test_lablet_definition_repository.py
@pytest.mark.integration
class TestLabletDefinitionRepository:
    @pytest.fixture
    async def repository(self, mongodb_container):
        db = get_test_database(mongodb_container)
        return MongoLabletDefinitionRepository(db)
    
    async def test_add_and_retrieve(self, repository):
        definition = LabletDefinition.create(name="test", topology=...)
        await repository.add_async(definition)
        
        retrieved = await repository.get_by_id_async(definition.id())
        assert retrieved.state.name == "test"
```

### 2.3 API Tests

**Scope**: REST API endpoints, authentication, authorization
**Framework**: pytest + httpx (TestClient)
**Markers**: `@pytest.mark.api`

**Target Coverage:**
| Endpoint Group | Target |
|----------------|--------|
| Definition CRUD | 85% |
| Instance CRUD | 85% |
| CloudEvents | 80% |
| Internal APIs | 80% |

**Example:**
```python
# tests/api/test_definitions_controller.py
@pytest.mark.api
class TestDefinitionsController:
    async def test_create_definition(self, client, auth_headers):
        response = await client.post(
            "/api/v1/definitions",
            json={"name": "test", "topology": {...}},
            headers=auth_headers
        )
        assert response.status_code == 201
        assert response.json()["name"] == "test"
    
    async def test_create_definition_unauthorized(self, client):
        response = await client.post("/api/v1/definitions", json={...})
        assert response.status_code == 401
```

### 2.4 End-to-End Tests

**Scope**: Full workflow scenarios, user journeys
**Framework**: pytest with Docker Compose test environment
**Markers**: `@pytest.mark.e2e`

**Target Coverage:**
| Workflow | Target |
|----------|--------|
| Lablet instantiation | 100% |
| Worker provisioning | 100% |
| Auto-scaling | 100% |
| Assessment integration | 100% |

**Example:**
```python
# tests/e2e/test_lablet_instantiation_workflow.py
@pytest.mark.e2e
class TestLabletInstantiationWorkflow:
    async def test_full_instantiation_lifecycle(self, e2e_environment):
        # Create definition
        definition = await create_definition(...)
        
        # Create scheduled request
        instance = await create_instance(
            definition_id=definition.id,
            timeslot_start=now() + timedelta(hours=1)
        )
        assert instance.state == "PENDING"
        
        # Wait for scheduling
        await wait_for_state(instance.id, "SCHEDULED")
        
        # Wait for instantiation
        await wait_for_state(instance.id, "RUNNING")
        
        # Verify lab created on worker
        worker = await get_worker(instance.worker_id)
        assert instance.lab_id in worker.labs
```

---

## 3. Test Infrastructure

### 3.1 Test Fixtures

**Shared fixtures in `conftest.py`:**
```python
# tests/conftest.py

@pytest.fixture(scope="session")
async def mongodb_container():
    """Spin up MongoDB container for integration tests."""
    with MongoDbContainer() as container:
        yield container

@pytest.fixture(scope="session")
async def etcd_container():
    """Spin up etcd container for integration tests."""
    with EtcdContainer() as container:
        yield container

@pytest.fixture
async def test_database(mongodb_container):
    """Get fresh database for each test."""
    client = AsyncIOMotorClient(mongodb_container.get_connection_url())
    db = client[f"test_{uuid4().hex[:8]}"]
    yield db
    await client.drop_database(db.name)

@pytest.fixture
async def etcd_client(etcd_container):
    """Get etcd client for tests."""
    return etcd3.client(
        host=etcd_container.get_container_host_ip(),
        port=etcd_container.get_exposed_port(2379)
    )

@pytest.fixture
async def test_app(test_database, etcd_client):
    """Create test application instance."""
    app = create_test_app(
        database=test_database,
        etcd_client=etcd_client
    )
    yield app

@pytest.fixture
async def client(test_app):
    """HTTP client for API tests."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client
```

### 3.2 Mock Services

**AWS EC2 Client Mock:**
```python
# tests/mocks/aws_mock.py
class MockAwsEc2Client:
    def __init__(self):
        self.instances = {}
    
    async def create_instance_async(self, config):
        instance_id = f"i-{uuid4().hex[:8]}"
        self.instances[instance_id] = {
            "id": instance_id,
            "state": "running",
            **config
        }
        return instance_id
    
    async def get_instance_async(self, instance_id):
        return self.instances.get(instance_id)
```

**CML API Client Mock:**
```python
# tests/mocks/cml_mock.py
class MockCMLApiClient:
    def __init__(self):
        self.labs = {}
    
    async def create_lab_async(self, worker_url, lab_config):
        lab_id = str(uuid4())
        self.labs[lab_id] = {
            "id": lab_id,
            "state": "STOPPED",
            **lab_config
        }
        return lab_id
    
    async def start_lab_async(self, worker_url, lab_id):
        self.labs[lab_id]["state"] = "STARTED"
```

### 3.3 Test Data Factories

```python
# tests/factories.py
from factory import Factory, LazyAttribute, SubFactory

class TopologySpecFactory(Factory):
    class Meta:
        model = TopologySpec
    
    format = TopologyFormat.YAML
    content = LazyAttribute(lambda _: generate_sample_topology())

class LabletDefinitionFactory(Factory):
    class Meta:
        model = dict  # For creating via API
    
    name = LazyAttribute(lambda _: f"definition-{uuid4().hex[:8]}")
    topology = SubFactory(TopologySpecFactory)
    resource_requirements = {
        "cpu_cores": 4,
        "memory_gb": 8,
        "estimated_nodes": 5
    }
```

---

## 4. Test Organization

### 4.1 Directory Structure

```
tests/
├── conftest.py                     # Global fixtures
├── factories.py                    # Test data factories
├── mocks/                          # Mock services
│   ├── __init__.py
│   ├── aws_mock.py
│   └── cml_mock.py
├── unit/                           # Unit tests
│   ├── domain/
│   │   ├── test_lablet_definition.py
│   │   ├── test_lablet_instance.py
│   │   └── test_value_objects.py
│   ├── application/
│   │   ├── commands/
│   │   │   ├── test_create_definition_command.py
│   │   │   └── test_create_instance_command.py
│   │   └── services/
│   │       ├── test_scheduler_service.py
│   │       └── test_port_allocation_service.py
│   └── infrastructure/
│       └── test_etcd_state_store.py
├── integration/                    # Integration tests
│   ├── repositories/
│   │   ├── test_lablet_definition_repository.py
│   │   └── test_lablet_instance_repository.py
│   ├── services/
│   │   └── test_etcd_integration.py
│   └── migrations/
│       └── test_database_migrations.py
├── api/                            # API tests
│   ├── test_definitions_controller.py
│   ├── test_instances_controller.py
│   ├── test_cloudevents_receiver.py
│   └── test_internal_apis.py
├── e2e/                            # End-to-end tests
│   ├── test_instantiation_workflow.py
│   ├── test_scheduling_workflow.py
│   ├── test_autoscaling_workflow.py
│   └── test_assessment_workflow.py
└── performance/                    # Performance tests
    ├── test_scheduler_performance.py
    └── test_api_load.py
```

### 4.2 Naming Conventions

- Test files: `test_<module>.py`
- Test classes: `Test<ComponentName>`
- Test methods: `test_<scenario>_<expected_result>`

**Examples:**
```python
test_create_definition_with_valid_topology_succeeds
test_create_definition_with_empty_name_raises_validation_error
test_scheduler_reconcile_assigns_pending_instances
```

---

## 5. Phase-Specific Testing

### 5.1 Phase 1: Foundation

**Focus Areas:**
- Domain entity creation and validation
- Repository CRUD operations
- API endpoint functionality
- Port allocation correctness

**Test Counts:**
| Category | Tests |
|----------|-------|
| Unit | ~100 |
| Integration | ~40 |
| API | ~30 |

### 5.2 Phase 2: Scheduling

**Focus Areas:**
- Scheduler reconciliation loops
- Worker selection algorithms
- State machine transitions
- Leader election behavior

**Test Counts:**
| Category | Tests |
|----------|-------|
| Unit | ~80 |
| Integration | ~50 |
| API | ~20 |

### 5.3 Phase 3: Auto-Scaling

**Focus Areas:**
- Scale-up trigger conditions
- Scale-down with DRAINING
- Resource controller reconciliation
- Concurrent operation handling

**Test Counts:**
| Category | Tests |
|----------|-------|
| Unit | ~60 |
| Integration | ~40 |
| E2E | ~20 |

### 5.4 Phase 4: Assessment

**Focus Areas:**
- CloudEvent processing
- Grading Engine pod generation
- External system integration
- Event correlation

**Test Counts:**
| Category | Tests |
|----------|-------|
| Unit | ~50 |
| Integration | ~30 |
| E2E | ~15 |

### 5.5 Phase 5: Production

**Focus Areas:**
- Performance under load
- Observability correctness
- Security verification
- Full workflow E2E

**Test Counts:**
| Category | Tests |
|----------|-------|
| E2E | ~30 |
| Performance | ~10 |
| Security | ~20 |

---

## 6. Continuous Integration

### 6.1 CI Pipeline Stages

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: poetry install
      - name: Run unit tests
        run: make test-unit
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  integration-tests:
    runs-on: ubuntu-latest
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017
      etcd:
        image: quay.io/coreos/etcd:v3.5.9
        ports:
          - 2379:2379
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: make test-integration

  api-tests:
    runs-on: ubuntu-latest
    needs: [unit-tests]
    steps:
      - uses: actions/checkout@v4
      - name: Run API tests
        run: make test-api

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [integration-tests, api-tests]
    steps:
      - uses: actions/checkout@v4
      - name: Start services
        run: docker compose up -d
      - name: Wait for services
        run: make wait-for-services
      - name: Run E2E tests
        run: make test-e2e
```

### 6.2 Test Commands

```makefile
# Makefile additions
test-unit:
	PYTHONPATH=src pytest tests/unit -v -m unit --cov=src --cov-report=xml

test-integration:
	PYTHONPATH=src pytest tests/integration -v -m integration

test-api:
	PYTHONPATH=src pytest tests/api -v -m api

test-e2e:
	PYTHONPATH=src pytest tests/e2e -v -m e2e --timeout=300

test-all:
	PYTHONPATH=src pytest tests -v --cov=src --cov-report=html

test-coverage:
	PYTHONPATH=src pytest tests -v --cov=src --cov-report=html --cov-fail-under=80
```

### 6.3 Coverage Requirements

| Phase | Minimum Coverage |
|-------|-----------------|
| Phase 1 | 80% |
| Phase 2 | 82% |
| Phase 3 | 82% |
| Phase 4 | 83% |
| Phase 5 | 85% |

---

## 7. Performance Testing

### 7.1 Load Testing

**Tool:** Locust or k6

**Scenarios:**
```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class LabletUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def list_definitions(self):
        self.client.get("/api/v1/definitions")
    
    @task(2)
    def get_definition(self):
        self.client.get("/api/v1/definitions/test-def")
    
    @task(1)
    def create_instance(self):
        self.client.post("/api/v1/instances", json={...})
```

**Targets:**
| Metric | Target |
|--------|--------|
| API response time (p95) | < 200ms |
| Scheduler reconcile (1000 instances) | < 5s |
| Controller reconcile (100 workers) | < 10s |

### 7.2 Stress Testing

**Scenarios:**
- 1000 concurrent instance requests
- 100 simultaneous worker provisioning
- Scheduler leader failover under load

### 7.3 Chaos Testing

**Tools:** Chaos Monkey, Litmus

**Scenarios:**
- etcd leader failure
- MongoDB connection loss
- Worker instance termination
- Network partition between scheduler and workers

---

## 8. Security Testing

### 8.1 Authentication Tests

```python
# tests/security/test_authentication.py
class TestAuthentication:
    async def test_api_requires_authentication(self, client):
        response = await client.get("/api/v1/definitions")
        assert response.status_code == 401
    
    async def test_expired_token_rejected(self, client):
        expired_token = generate_expired_jwt()
        response = await client.get(
            "/api/v1/definitions",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
```

### 8.2 Authorization Tests

```python
# tests/security/test_authorization.py
class TestAuthorization:
    async def test_admin_can_create_definition(self, client, admin_token):
        response = await client.post(
            "/api/v1/definitions",
            json={...},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
    
    async def test_viewer_cannot_create_definition(self, client, viewer_token):
        response = await client.post(
            "/api/v1/definitions",
            json={...},
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert response.status_code == 403
```

### 8.3 Input Validation Tests

```python
# tests/security/test_input_validation.py
class TestInputValidation:
    @pytest.mark.parametrize("payload", [
        {"name": "<script>alert('xss')</script>"},
        {"name": "a" * 10000},
        {"topology": {"format": "INVALID"}},
    ])
    async def test_rejects_malicious_input(self, client, auth_headers, payload):
        response = await client.post(
            "/api/v1/definitions",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code in [400, 422]
```

---

## 9. Test Reporting

### 9.1 Coverage Reports

- HTML reports generated by pytest-cov
- XML reports uploaded to Codecov
- Badge in README showing current coverage

### 9.2 Test Results Dashboard

- GitHub Actions summary
- Test timing trends
- Flaky test detection

### 9.3 Performance Reports

- Locust HTML reports
- Grafana dashboards for long-running tests
- Regression alerts

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
