# ADR-007: Worker Template Seeding and Management

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-01-15 |
| **Deciders** | Architecture Team |
| **Related ADRs** | [ADR-001](./ADR-001-api-centric-state-management.md) |

## Context

Worker Templates define the characteristics of CML Workers (instance type, capacity, license type, AMI pattern). These templates need to be:

1. Available on first deployment (seeded)
2. Configurable without code changes
3. Manageable via API for runtime updates

Options considered:

1. **Configuration files only** - Templates in YAML/JSON, immutable at runtime
2. **Database only** - Templates as aggregates, must be created via API
3. **Seeded + API managed** - Config files seed database, API for updates

## Decision

**Worker Templates are stored in MongoDB as aggregates AND seeded from configuration files on startup.**

- Configuration files define initial templates
- Database seeder HostedService creates templates on boot (if not exists)
- Templates manageable via API CRUD after seeding
- Database is source of truth at runtime

## Rationale

### Benefits

- **Operational simplicity**: Default templates available immediately
- **GitOps friendly**: Template definitions version-controlled
- **Runtime flexibility**: Admins can adjust without redeploy
- **Idempotent seeding**: Safe to restart multiple times

### Trade-offs

- Dual source (config + DB) requires clear precedence rules
- Must handle config vs DB drift

## Consequences

### Positive

- Zero-touch deployment with sensible defaults
- Production overrides without code changes
- Full audit trail of template changes

### Negative

- Config file changes don't auto-sync to DB (by design)
- Potential confusion about source of truth

## Implementation

### Configuration File Structure

```yaml
# config/worker_templates.yaml
templates:
  - name: "personal-standard"
    description: "Personal license worker for small labs"
    instance_type: "m5zn.metal"
    capacity:
      cpu_cores: 48
      memory_gb: 192
      storage_gb: 500
    license_type: "PERSONAL"
    max_nodes: 20
    ami_pattern: "CML-2.9.*"
    startup_time_minutes: 20
    port_range:
      start: 2000
      end: 9999

  - name: "enterprise-large"
    description: "Enterprise license worker for large labs"
    instance_type: "m5zn.metal"
    capacity:
      cpu_cores: 48
      memory_gb: 192
      storage_gb: 500
    license_type: "ENTERPRISE"
    max_nodes: 500
    ami_pattern: "CML-2.9.*"
    startup_time_minutes: 20
    port_range:
      start: 2000
      end: 9999
```

### Database Seeder HostedService

```python
class WorkerTemplateSeeder(HostedService):
    """Seeds worker templates from configuration on startup."""

    def __init__(
        self,
        template_repository: WorkerTemplateRepository,
        config_path: str = "config/worker_templates.yaml"
    ):
        self._repository = template_repository
        self._config_path = config_path

    async def start_async(self):
        """Seed templates on application startup."""
        templates = self._load_config()

        for template_config in templates:
            existing = await self._repository.get_by_name_async(
                template_config["name"]
            )

            if existing is None:
                # Create new template
                template = WorkerTemplate.create(**template_config)
                await self._repository.add_async(template)
                log.info(f"Seeded worker template: {template_config['name']}")
            else:
                log.debug(f"Template already exists: {template_config['name']}")

    def _load_config(self) -> list[dict]:
        """Load templates from YAML config."""
        with open(self._config_path) as f:
            config = yaml.safe_load(f)
        return config.get("templates", [])
```

### WorkerTemplate Aggregate

```python
@dataclass
class WorkerTemplateState(AggregateState[str]):
    id: str
    name: str
    description: str
    instance_type: str
    capacity: WorkerCapacity
    license_type: LicenseType
    max_nodes: int
    ami_pattern: str
    startup_time_minutes: int
    port_range_start: int
    port_range_end: int
    created_at: datetime
    updated_at: datetime
    is_seeded: bool  # True if created by seeder


class WorkerTemplate(AggregateRoot[WorkerTemplateState, str]):
    """Worker template aggregate."""

    @staticmethod
    def create(
        name: str,
        instance_type: str,
        capacity: dict,
        license_type: str,
        **kwargs
    ) -> "WorkerTemplate":
        template = WorkerTemplate()
        template.record_event(WorkerTemplateCreatedDomainEvent(
            aggregate_id=str(uuid4()),
            name=name,
            instance_type=instance_type,
            capacity=WorkerCapacity(**capacity),
            license_type=LicenseType(license_type),
            is_seeded=kwargs.get("is_seeded", False),
            **kwargs
        ))
        return template
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/templates` | List all worker templates |
| GET | `/api/v1/templates/{id}` | Get template by ID |
| POST | `/api/v1/templates` | Create new template |
| PUT | `/api/v1/templates/{id}` | Update template |
| DELETE | `/api/v1/templates/{id}` | Delete template (if no workers using) |

## Seeding Rules

1. **Create if not exists**: Seeder only creates, never updates
2. **Name is unique key**: Templates identified by name
3. **Manual edits preserved**: DB changes not overwritten by config
4. **Restart safe**: Multiple restarts don't duplicate

## Config vs DB Sync (Future Enhancement)

If needed, could add optional "force sync" mode:

- Compare config hash with stored hash
- Prompt admin or auto-update if drift detected
- Not implemented initially (YAGNI)
