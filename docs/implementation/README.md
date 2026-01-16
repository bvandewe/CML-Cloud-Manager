# Lablet Resource Manager - Implementation Plan

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Last Updated** | 2026-01-16 |
| **Author** | Architecture Team |
| **Related** | [Requirements](../specs/lablet-resource-manager-requirements.md), [Architecture](../architecture/lablet-resource-manager-architecture.md) |

---

## 1. Executive Summary

This implementation plan transforms the CML Cloud Manager into a **Lablet Resource Manager** with Kubernetes-like declarative resource management, intelligent scheduling, and auto-scaling capabilities.

**Timeline:** 20 weeks (5 phases of 4 weeks each)

**Key Deliverables:**

- Declarative LabletDefinition and LabletInstance lifecycle management
- Intelligent scheduling with time-windowed reservations
- Automatic Worker scaling (up/down) based on demand
- CloudEvent-based integration for assessment/grading systems

---

## 2. Phase Overview

| Phase | Name | Duration | Key Outcomes |
|-------|------|----------|--------------|
| [Phase 1](./phase-1-foundation.md) | Foundation | Weeks 1-4 | Domain models, basic CRUD APIs, port allocation |
| [Phase 2](./phase-2-scheduling.md) | Scheduling | Weeks 5-8 | Scheduler service, timeslot management, instantiation |
| [Phase 3](./phase-3-autoscaling.md) | Auto-Scaling | Weeks 9-12 | Resource Controller, scale up/down, DRAINING |
| [Phase 4](./phase-4-assessment.md) | Assessment Integration | Weeks 13-16 | CloudEvents, grading integration, Pod generation |
| [Phase 5](./phase-5-production.md) | Production Hardening | Weeks 17-20 | Observability, performance, documentation |

---

## 3. Prerequisites

See [Prerequisites & Environment Setup](./prerequisites.md) for detailed setup instructions.

**Summary:**

- etcd cluster (dev: single node, prod: 3-node)
- Python etcd client library (`etcd3-py` or `aioetcd3`)
- S3/MinIO for lab artifact storage
- Updated Docker Compose for local development

---

## 4. Architecture Decisions

All architectural decisions are documented in [/docs/architecture/adr/](../architecture/adr/README.md):

| ADR | Title | Impact on Implementation |
|-----|-------|--------------------------|
| ADR-001 | API-Centric State Management | Control Plane API is single writer to MongoDB |
| ADR-002 | Separate Scheduler Service | Scheduler as independent service with leader election |
| ADR-003 | CloudEvents for Integration | External integration via CloudEvents bus |
| ADR-004 | Port Allocation per Worker | Port allocation service in Phase 1 |
| ADR-005 | Dual State Store (etcd + MongoDB) | etcd for state/watches, MongoDB for specs |
| ADR-006 | Scheduler HA via Leader Election | Leader election using etcd leases |
| ADR-007 | Worker Template Seeding | Templates seeded from config files |
| ADR-008 | Worker Draining State | DRAINING state for graceful scale-down |

---

## 5. Risk Register

See [Risk Register](./risk-register.md) for detailed risk analysis and mitigation strategies.

**Top Risks:**

1. **etcd Operational Complexity** - Mitigate with managed etcd or thorough runbooks
2. **Worker Startup Time (15-20 min)** - Mitigate with predictive scaling, warm capacity
3. **CML API Reliability** - Mitigate with retry logic, circuit breakers
4. **State Synchronization** - Mitigate with clear ownership (etcd vs MongoDB)

---

## 6. Migration Strategy

See [Migration Strategy](./migration-strategy.md) for backward compatibility approach.

**Principles:**

- Existing CMLWorker functionality preserved
- New LabletInstance features additive
- Feature flags for gradual rollout
- No breaking changes to existing APIs

---

## 7. Definition of Done

### Per-Task DoD

- [ ] Code implemented following Neuroglia patterns
- [ ] Unit tests with ≥80% coverage
- [ ] Integration tests for external dependencies
- [ ] Documentation updated (docstrings, README)
- [ ] Code review approved
- [ ] No regressions in existing functionality

### Per-Phase DoD

- [ ] All phase tasks completed
- [ ] Phase-specific acceptance criteria met
- [ ] Performance benchmarks validated
- [ ] Security review completed
- [ ] Deployment documentation updated

---

## 8. Document Index

### Phase Documents

- [Prerequisites & Environment Setup](./prerequisites.md)
- [Phase 1: Foundation](./phase-1-foundation.md)
- [Phase 2: Scheduling](./phase-2-scheduling.md)
- [Phase 3: Auto-Scaling](./phase-3-autoscaling.md)
- [Phase 4: Assessment Integration](./phase-4-assessment.md)
- [Phase 5: Production Hardening](./phase-5-production.md)

### Supporting Documents

- [Risk Register](./risk-register.md)
- [Migration Strategy](./migration-strategy.md)
- [Testing Strategy](./testing-strategy.md)

---

## 9. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
