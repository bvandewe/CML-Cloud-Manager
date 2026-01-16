# ADR-004: Port Allocation per Worker

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-01-15 |
| **Deciders** | Architecture Team |
| **Related ADRs** | [ADR-001](./ADR-001-api-centric-state-management.md) |

## Context

Each CML Lab node requires external TCP ports for console access (serial, VNC). The sample lab shows ports defined via `smart_annotations.tag` (e.g., `serial:5041`, `vnc:5044`).

When multiple LabletInstances run on the same Worker, port conflicts must be prevented.

Options considered:

1. **Global port allocation** - Central service assigns globally unique ports
2. **Per-worker allocation** - Each worker manages its own port range
3. **Dynamic NAT** - Use port forwarding/NAT to map internal to external ports

## Decision

**Ports are allocated from a per-worker range (2000-9999), not globally unique.**

Each Worker maintains its own port allocation table. Ports are reused across Workers since they have different IP addresses.

## Rationale

### Benefits

- **Simplicity**: No cross-worker coordination needed
- **Scalability**: Port allocation is local to worker
- **No Central Bottleneck**: Workers don't contend for global port pool
- **Sufficient Range**: 8000 ports per worker supports many instances

### Trade-offs

- Port numbers not globally unique (debugging may require worker context)
- Maximum ~8000 ports per worker (practical limit ~400-800 instances)

## Consequences

### Positive

- Simple implementation
- No distributed consensus for port allocation
- Each worker is independent

### Negative

- Log analysis requires worker context for port correlation
- Port exhaustion possible if single worker overloaded

## Implementation Notes

### Port Allocation Algorithm

```python
class PortAllocator:
    def __init__(self, start: int = 2000, end: int = 9999):
        self.start = start
        self.end = end
        self.allocated: set[int] = set()

    def allocate(self, count: int) -> list[int]:
        """Allocate N contiguous or best-effort ports."""
        ports = []
        for port in range(self.start, self.end + 1):
            if port not in self.allocated:
                ports.append(port)
                self.allocated.add(port)
                if len(ports) == count:
                    break
        if len(ports) < count:
            raise PortExhausted(f"Only {len(ports)} of {count} ports available")
        return ports

    def release(self, ports: list[int]) -> None:
        """Release previously allocated ports."""
        for port in ports:
            self.allocated.discard(port)
```

### Lab YAML Rewriting

Template placeholders in LabletDefinition:

```yaml
smart_annotations:
  - tag: serial:${PORT_SERIAL_1}
  - tag: vnc:${PORT_VNC_1}
nodes:
  - tags:
      - serial:${PORT_SERIAL_1}
```

Rewritten at instantiation:

```yaml
smart_annotations:
  - tag: serial:5041
  - tag: vnc:5044
nodes:
  - tags:
      - serial:5041
```

### Worker State Extension

```python
@dataclass
class PortAllocation:
    instance_id: str
    ports: dict[str, int]  # {"serial_1": 5041, "vnc_1": 5044}
    allocated_at: datetime

class CMLWorkerState:
    port_range_start: int = 2000
    port_range_end: int = 9999
    port_allocations: list[PortAllocation] = []
```
