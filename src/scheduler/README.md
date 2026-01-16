# Scheduler Service

The Scheduler Service is responsible for placement decisions and managing the scheduling queue for LabletInstances.

## Responsibilities

- Watch for PENDING LabletInstances via etcd
- Execute placement algorithm (filter → score → select)
- Manage timeslot reservations
- Signal Resource Controller when scale-up is needed
- Leader election for high availability

## Architecture

```
application/
    commands/       # Scheduling commands
    queries/        # State queries
    services/       # Scheduler service, placement engine
    dtos/           # Data transfer objects
domain/
    entities/       # Scheduling domain entities
    repositories/   # Repository interfaces
    events/         # Domain events
integration/
    repositories/   # etcd state store implementation
    services/       # Control Plane API client
infrastructure/    # Technical adapters
```

## Key Components

### Leader Election

Uses etcd leases for leader election. Only the leader runs the scheduling loop:

```python
class SchedulerService:
    async def start_async(self):
        self.is_leader = await self._campaign_for_leadership()
        if self.is_leader:
            asyncio.create_task(self._run_scheduling_loop())
```

### Placement Algorithm

1. **Filter Phase**: License affinity, resource requirements, AMI, capacity, ports, NOT DRAINING
2. **Score Phase**: Bin-packing (prefer fuller workers)
3. **Select Phase**: Highest scoring worker

### Timeslot Management

Monitors approaching timeslots and triggers instantiation with lead time buffer (default: 35 minutes to account for worker bootup + lab instantiation).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ETCD_HOST` | etcd server host | `localhost` |
| `ETCD_PORT` | etcd server port | `2379` |
| `CONTROL_PLANE_API_URL` | Control Plane API URL | `http://localhost:8080` |
| `SCHEDULER_INSTANCE_ID` | Unique instance ID | Auto-generated |
| `LEADER_LEASE_TTL` | Leader lease TTL in seconds | `15` |
| `RECONCILE_INTERVAL` | Reconciliation interval in seconds | `30` |

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
