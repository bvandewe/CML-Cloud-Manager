# Resource Controller Service

The Resource Controller is responsible for reconciliation, auto-scaling, and cloud provider operations.

## Responsibilities

- Reconciliation loop for workers and instances
- Auto-scaling (scale-up and scale-down decisions)
- Worker lifecycle management (including DRAINING state)
- Cloud Provider SPI for infrastructure operations (AWS EC2)
- State synchronization with CML workers

## Architecture

```
application/
    commands/       # Controller commands
    queries/        # State queries
    services/       # Controller service, reconcilers
    dtos/           # Data transfer objects
domain/
    entities/       # Controller domain entities
    repositories/   # Repository interfaces
    events/         # Domain events
integration/
    repositories/   # etcd state store implementation
    services/       # Control Plane API client
    providers/      # Cloud Provider SPI (AWS EC2 adapter)
infrastructure/    # Technical adapters
```

## Key Components

### Reconciliation Loop

Runs every 30 seconds to detect and correct drift between desired and actual state:

```python
class ControllerService:
    async def _reconcile(self):
        await self._reconcile_instances()
        await self._reconcile_workers()
        await self._reconcile_capacity()
```

### Cloud Provider SPI

Abstraction layer for cloud infrastructure operations:

```python
class CloudProviderInterface(ABC):
    @abstractmethod
    async def create_instance(self, template: WorkerTemplate) -> str: ...

    @abstractmethod
    async def terminate_instance(self, instance_id: str) -> None: ...

    @abstractmethod
    async def get_instance_status(self, instance_id: str) -> str: ...
```

Currently implemented:

- **AWS EC2 Adapter** - For m5zn.metal instances running CML

### Scale-Up Logic

Triggered when scheduler cannot place an instance:

1. Receive scale-up request (from Scheduler or detected in reconciliation)
2. Select appropriate WorkerTemplate
3. Provision new EC2 instance via Cloud Provider SPI
4. Track worker through PENDING → PROVISIONING → RUNNING

### Scale-Down Logic

Triggered when workers are idle:

1. Detect idle workers (no running or scheduled instances)
2. Transition to DRAINING (no new assignments accepted)
3. Wait for existing instances to complete
4. When empty: DRAINING → STOPPING → STOPPED → TERMINATED

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ETCD_HOST` | etcd server host | `localhost` |
| `ETCD_PORT` | etcd server port | `2379` |
| `CONTROL_PLANE_API_URL` | Control Plane API URL | `http://localhost:8080` |
| `CONTROLLER_INSTANCE_ID` | Unique instance ID | Auto-generated |
| `LEADER_LEASE_TTL` | Leader lease TTL in seconds | `15` |
| `RECONCILE_INTERVAL` | Reconciliation interval in seconds | `30` |
| `AWS_ACCESS_KEY_ID` | AWS access key | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - |
| `AWS_REGION` | AWS region | `us-east-1` |

## Development

```bash
# Install dependencies
make install

# Run locally (requires etcd and Control Plane API)
make run

# Run tests
make test
```

## Health Check

The service exposes a health endpoint at `/health` for container orchestration.
