# Migration Strategy

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |

---

## 1. Overview

This document outlines the strategy for integrating the Lablet Resource Manager features into the existing CML Cloud Manager codebase while maintaining backward compatibility.

### Principles

1. **Additive Changes**: New features extend, not replace, existing functionality
2. **Backward Compatibility**: Existing APIs and UIs continue to work
3. **Feature Flags**: Gradual rollout of new capabilities
4. **Zero Downtime**: Migrations executed without service interruption

---

## 2. Database Migrations

### 2.1 MongoDB Collections (New)

**New Collections:**

```
lablet_definitions    # LabletDefinition aggregates
lablet_instances      # LabletInstance aggregates
worker_templates      # WorkerTemplate configuration
scaling_audit_events  # Scaling decision audit log
```

**Migration Script:**

```python
# migrations/001_lablet_collections.py
async def upgrade(db: AsyncIOMotorDatabase):
    """Create collections for Lablet Resource Manager."""

    # Create lablet_definitions collection
    await db.create_collection("lablet_definitions")
    await db.lablet_definitions.create_index("state.name")
    await db.lablet_definitions.create_index([
        ("state.name", 1),
        ("state.version", 1)
    ], unique=True)

    # Create lablet_instances collection
    await db.create_collection("lablet_instances")
    await db.lablet_instances.create_index("state.state")
    await db.lablet_instances.create_index("state.worker_id")
    await db.lablet_instances.create_index("state.definition_id")
    await db.lablet_instances.create_index([
        ("state.state", 1),
        ("state.timeslot_start", 1)
    ])

    # Create worker_templates collection
    await db.create_collection("worker_templates")
    await db.worker_templates.create_index("state.name", unique=True)

    # Create scaling_audit_events collection
    await db.create_collection("scaling_audit_events")
    await db.scaling_audit_events.create_index("timestamp")
    await db.scaling_audit_events.create_index([
        ("timestamp", 1)
    ], expireAfterSeconds=365*24*60*60)  # 1 year TTL


async def downgrade(db: AsyncIOMotorDatabase):
    """Remove Lablet Resource Manager collections."""
    await db.drop_collection("lablet_definitions")
    await db.drop_collection("lablet_instances")
    await db.drop_collection("worker_templates")
    await db.drop_collection("scaling_audit_events")
```

### 2.2 CMLWorker Collection (Extensions)

**Modified Fields on `cml_workers` collection:**

```python
# migrations/002_cml_worker_extensions.py
async def upgrade(db: AsyncIOMotorDatabase):
    """Add capacity tracking fields to CMLWorker."""

    # Add default values for existing workers
    await db.cml_workers.update_many(
        {"state.template_name": {"$exists": False}},
        {"$set": {
            "state.template_name": None,
            "state.declared_capacity": {
                "cpu_cores": 48,
                "memory_gb": 192,
                "storage_gb": 500,
                "max_nodes": 20  # Default to Personal license limit
            },
            "state.allocated_capacity": {
                "cpu_cores": 0,
                "memory_gb": 0,
                "storage_gb": 0,
                "max_nodes": 0
            },
            "state.port_range_start": 2000,
            "state.port_range_end": 9999,
            "state.port_allocations": [],
            "state.lablet_instance_ids": []
        }}
    )

    # Add index for capacity queries
    await db.cml_workers.create_index([
        ("state.status", 1),
        ("state.template_name", 1)
    ])


async def downgrade(db: AsyncIOMotorDatabase):
    """Remove capacity tracking fields (optional - can keep for compatibility)."""
    pass  # Fields are additive, no need to remove
```

### 2.3 Migration Execution

**Run migrations on startup:**

```python
# src/main.py
async def run_migrations(db: AsyncIOMotorDatabase):
    """Run database migrations on startup."""
    from migrations import get_pending_migrations

    for migration in get_pending_migrations(db):
        logger.info(f"Running migration: {migration.name}")
        await migration.upgrade(db)
        await db.migrations.insert_one({
            "name": migration.name,
            "applied_at": datetime.now(timezone.utc)
        })
```

---

## 3. API Compatibility

### 3.1 Existing APIs (Unchanged)

The following APIs remain unchanged:

```
/api/v1/workers/*        # CMLWorker management
/api/v1/labs/*           # Lab operations (via CML API)
/api/auth/*              # Authentication
/api/events/stream       # SSE events
```

### 3.2 New APIs (Additive)

New APIs for Lablet Resource Manager:

```
/api/v1/definitions/*    # LabletDefinition management
/api/v1/instances/*      # LabletInstance management
/api/v1/events           # CloudEvents receiver
/api/internal/*          # Internal scheduler/controller APIs
```

### 3.3 API Versioning

All new APIs use `/api/v1/` prefix. If breaking changes needed in future:

- Introduce `/api/v2/` for new version
- Maintain `/api/v1/` for backward compatibility
- Deprecation notice with timeline

---

## 4. Configuration Migration

### 4.1 New Settings

**Add to Settings class (with defaults):**

```python
class Settings(ApplicationSettings):
    # Existing settings...

    # Lablet Resource Manager (Phase 1+)
    LABLET_ENABLED: bool = False  # Feature flag

    # etcd Configuration
    ETCD_HOST: str = "localhost"
    ETCD_PORT: int = 2379
    ETCD_USERNAME: str | None = None
    ETCD_PASSWORD: str | None = None

    # Artifact Storage
    ARTIFACT_STORAGE_ENDPOINT: str = "http://localhost:9000"
    ARTIFACT_STORAGE_BUCKET: str = "lablet-artifacts"

    # Scheduler
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_RECONCILE_INTERVAL: int = 30

    # Resource Controller
    CONTROLLER_ENABLED: bool = False

    # CloudEvents
    CLOUDEVENTS_SINK_URL: str | None = None
```

### 4.2 Feature Flag Rollout

**Phase 1: Foundation**

```python
LABLET_ENABLED=true  # Enable new collections, APIs
SCHEDULER_ENABLED=false
CONTROLLER_ENABLED=false
```

**Phase 2: Scheduling**

```python
LABLET_ENABLED=true
SCHEDULER_ENABLED=true  # Enable scheduler
CONTROLLER_ENABLED=false
```

**Phase 3: Auto-Scaling**

```python
LABLET_ENABLED=true
SCHEDULER_ENABLED=true
CONTROLLER_ENABLED=true  # Enable controller
```

---

## 5. CMLWorker Integration

### 5.1 Dual Usage Model

CMLWorker can be used in two modes:

**Legacy Mode (existing functionality):**

- Manual worker provisioning
- Direct lab operations via UI
- No capacity tracking
- No scheduling integration

**Lablet Mode (new functionality):**

- Automatic worker provisioning via templates
- LabletInstance scheduling
- Capacity tracking
- Port allocation

### 5.2 Worker Detection

Workers can be identified by mode:

```python
def is_lablet_managed(worker: CMLWorker) -> bool:
    """Check if worker is managed by Lablet Resource Manager."""
    return worker.state.template_name is not None


def get_worker_mode(worker: CMLWorker) -> str:
    """Get worker management mode."""
    if worker.state.template_name:
        return "lablet"
    return "legacy"
```

### 5.3 Gradual Migration Path

1. **Existing workers**: Continue to work in legacy mode
2. **New workers via templates**: Automatically in lablet mode
3. **Migration option**: Convert legacy → lablet by assigning template
4. **No forced migration**: Legacy mode supported indefinitely

---

## 6. UI Migration

### 6.1 Existing UI (Preserved)

Current UI pages remain functional:

- Worker dashboard
- Worker details
- Labs view
- System settings

### 6.2 New UI Pages (Additive)

New pages for Lablet features:

- Lablet Definitions
- Lablet Instances
- Capacity Dashboard (optional)

### 6.3 UI Feature Detection

UI adapts based on feature flags:

```javascript
// Fetch feature flags from API
const features = await fetch('/api/v1/features').then(r => r.json());

// Conditionally render navigation
if (features.lablet_enabled) {
    showNavItem('Lablet Definitions', '/definitions');
    showNavItem('Lablet Instances', '/instances');
}

// Show capacity info on worker cards
if (features.lablet_enabled) {
    workerCard.showCapacityIndicator();
}
```

---

## 7. Rollback Strategy

### 7.1 Feature Flag Rollback

Immediate rollback by disabling features:

```bash
# Disable all Lablet features
LABLET_ENABLED=false
SCHEDULER_ENABLED=false
CONTROLLER_ENABLED=false
```

### 7.2 Database Rollback

**Not recommended** - data loss risk. If needed:

1. Stop application
2. Run `downgrade()` migrations
3. Restart with features disabled

### 7.3 Graceful Degradation

If Lablet features fail:

1. Existing worker management continues
2. Direct lab operations unaffected
3. Scheduled instances stay in current state
4. Manual intervention possible

---

## 8. Testing Strategy

### 8.1 Backward Compatibility Tests

```python
# tests/compatibility/test_legacy_apis.py
class TestLegacyAPICompatibility:
    """Ensure existing APIs work unchanged."""

    async def test_worker_crud_unchanged(self):
        # Create worker via existing API
        response = await client.post("/api/v1/workers", json={...})
        assert response.status_code == 201

        # Verify worker has new fields with defaults
        worker = response.json()
        assert worker["template_name"] is None
        assert worker["declared_capacity"] is not None

    async def test_lab_operations_unchanged(self):
        # Lab operations via existing API
        response = await client.get(f"/api/v1/workers/{worker_id}/labs")
        assert response.status_code == 200
```

### 8.2 Migration Tests

```python
# tests/migrations/test_migrations.py
class TestMigrations:
    """Test database migrations."""

    async def test_upgrade_preserves_data(self):
        # Create legacy worker
        await db.cml_workers.insert_one({...})

        # Run migration
        await upgrade(db)

        # Verify data preserved + new fields added
        worker = await db.cml_workers.find_one({})
        assert worker["state"]["name"] == "test-worker"  # Preserved
        assert worker["state"]["declared_capacity"] is not None  # Added
```

---

## 9. Communication Plan

### 9.1 Internal Communication

- Architecture review meeting before Phase 1
- Weekly status updates during implementation
- Demo sessions at phase completion

### 9.2 Documentation Updates

- README.md updated with new features
- CHANGELOG.md entries per phase
- Migration guide for operators
- API documentation for integrators

### 9.3 User Communication

- Release notes for each phase
- Feature announcement (if external users)
- Deprecation notices (if any)

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
