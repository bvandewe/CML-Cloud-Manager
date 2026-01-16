# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the CML Cloud Manager's Lablet Resource Manager expansion.

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](./ADR-001-api-centric-state-management.md) | API-Centric State Management | Accepted | 2026-01-15 |
| [ADR-002](./ADR-002-separate-scheduler-service.md) | Separate Scheduler Service | Accepted | 2026-01-15 |
| [ADR-003](./ADR-003-cloudevents-for-integration.md) | CloudEvents for External Integration | Accepted | 2026-01-15 |
| [ADR-004](./ADR-004-port-allocation-per-worker.md) | Port Allocation per Worker | Accepted | 2026-01-15 |
| [ADR-005](./ADR-005-state-store-architecture.md) | Dual State Store Architecture (etcd + MongoDB) | Accepted | 2026-01-16 |
| [ADR-006](./ADR-006-scheduler-ha-coordination.md) | Scheduler High Availability Coordination | Accepted | 2026-01-16 |
| [ADR-007](./ADR-007-worker-template-seeding.md) | Worker Template Seeding and Management | Accepted | 2026-01-15 |
| [ADR-008](./ADR-008-worker-draining-state.md) | Worker Draining State for Scale-Down | Accepted | 2026-01-16 |

## Status Definitions

| Status | Meaning |
|--------|---------|
| **Proposed** | Under discussion, not yet approved |
| **Accepted** | Decision made and should be followed |
| **Superseded** | Replaced by another ADR |
| **Deprecated** | No longer relevant |

## ADR Template

When creating new ADRs, use this template:

```markdown
# ADR-NNN: Title

| Attribute | Value |
|-----------|-------|
| **Status** | Proposed |
| **Date** | YYYY-MM-DD |
| **Deciders** | Team/Person |
| **Related ADRs** | Links to related ADRs |

## Context

What is the issue that we're seeing that is motivating this decision or change?

## Decision

What is the change that we're proposing and/or doing?

## Rationale

Why is this decision being made? What alternatives were considered?

## Consequences

### Positive
- What becomes easier or possible?

### Negative
- What becomes harder or impossible?

### Risks
- What could go wrong?

## Implementation Notes

Technical details, code examples, configuration.
```

## Dependency Graph

```
ADR-001 (API-Centric)
    ├── ADR-002 (Scheduler) ─────┐
    │       └── ADR-006 (HA) ◄───┤
    │                            │
    └── ADR-005 (State Store) ◄──┘
            └── ADR-006 (HA)

ADR-003 (CloudEvents)
    └── ADR-004 (Ports)

ADR-007 (Templates) ← standalone

ADR-008 (Draining)
    └── ADR-002 (Scheduler)
```
