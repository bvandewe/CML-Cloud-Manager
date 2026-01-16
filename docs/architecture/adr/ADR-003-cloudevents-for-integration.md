# ADR-003: CloudEvents for External Integration

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-01-15 |
| **Deciders** | Architecture Team |
| **Related ADRs** | [ADR-004](./ADR-004-port-allocation-per-worker.md) |

## Context

CCM must integrate with external systems:

- **Assessment Platform**: Trigger collection, receive grading results
- **Audit/Compliance**: Track all state changes for regulatory requirements
- **Billing/Metering**: Future integration for usage-based billing

We need a standardized event format for this communication.

Options considered:

1. **REST webhooks** - Direct HTTP callbacks to external systems
2. **CloudEvents** - CNCF standard event format via cloud-streams
3. **Message queues** - RabbitMQ/SQS with custom payloads
4. **gRPC streaming** - Bidirectional streaming to subscribers

## Decision

**Use CloudEvents (via Neuroglia cloud-streams) for all external system communication.**

All domain events are published as CloudEvents to the cloud-streams bus. External systems subscribe to relevant event types.

## Rationale

### Benefits

- **Vendor Neutral**: CNCF standard, no lock-in to specific message broker
- **Existing Support**: Neuroglia framework already supports CloudEvents
- **Decoupling**: CCM doesn't need to know about consumer internals
- **Extensibility**: New consumers can subscribe without CCM changes
- **Audit Trail**: Events naturally provide audit log when persisted

### Trade-offs

- Eventual consistency (events are async)
- Event schema versioning must be managed
- Debugging async flows more complex than sync calls

## Consequences

### Positive

- Clean integration boundaries
- Natural fit with event-driven architecture
- Audit log "for free" by persisting events

### Negative

- Must handle event ordering and idempotency
- Schema evolution requires careful planning

## Event Catalog

### Events Emitted by CCM

| Event Type | Trigger | Data |
|------------|---------|------|
| `ccm.lablet.definition.created` | New definition registered | definition_id, name, version |
| `ccm.lablet.definition.version.created` | New version detected | definition_id, old_version, new_version |
| `ccm.lablet.instance.pending` | Instance requested | instance_id, definition_id, owner_id |
| `ccm.lablet.instance.scheduled` | Worker assigned | instance_id, worker_id, allocated_ports |
| `ccm.lablet.instance.provisioning.started` | Lab import started | instance_id, worker_id |
| `ccm.lablet.instance.running` | Lab started successfully | instance_id, cml_lab_id |
| `ccm.lablet.instance.collecting.started` | Collection triggered | instance_id |
| `ccm.lablet.instance.grading.started` | Grading in progress | instance_id |
| `ccm.lablet.instance.grading.completed` | Grading finished | instance_id, score |
| `ccm.lablet.instance.stopping` | Stop initiated | instance_id |
| `ccm.lablet.instance.stopped` | Lab stopped | instance_id |
| `ccm.lablet.instance.terminated` | Resources released | instance_id, final_state |
| `ccm.worker.scaling.up` | New worker starting | worker_id, template_name |
| `ccm.worker.scaling.down` | Worker stopping | worker_id, reason |
| `ccm.worker.draining` | Worker entering drain mode | worker_id |

### Events Consumed by CCM

| Event Type | Source | Action |
|------------|--------|--------|
| `assessment.collection.completed` | Assessment Platform | Transition to GRADING |
| `assessment.grading.completed` | Grading Engine | Store score, transition to STOPPING |

## Implementation Notes

- Use `@cloudevent` decorator for domain events (existing Neuroglia pattern)
- Persist events to cloud-streams for durability
- External systems query cloud-streams API for missed events
- Consider dead-letter queue for failed deliveries
