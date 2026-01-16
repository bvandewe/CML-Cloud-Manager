# Risk Register

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |

---

## 1. Risk Assessment Matrix

| Impact | Low (1) | Medium (2) | High (3) |
|--------|---------|------------|----------|
| **High (3)** | 3 | 6 | 9 |
| **Medium (2)** | 2 | 4 | 6 |
| **Low (1)** | 1 | 2 | 3 |

**Risk Score = Likelihood × Impact**

- **Low (1-2):** Monitor, no immediate action
- **Medium (3-4):** Mitigate, plan contingency
- **High (6-9):** Critical, requires active mitigation

---

## 2. Technical Risks

### R-001: etcd Operational Complexity

| Attribute | Value |
|-----------|-------|
| **Category** | Infrastructure |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Risk Score** | 6 (High) |
| **Phase** | 1-5 |

**Description:**
etcd requires specialized operational knowledge. Cluster management, backup/restore, and troubleshooting are different from MongoDB/Redis.

**Mitigation Strategies:**
1. Consider managed etcd service (AWS EKS etcd, Azure CosmosDB etcd API)
2. Create comprehensive operational runbooks (Task 5.6)
3. Training session for operations team
4. Automated backup procedures
5. Monitoring dashboards with alerting

**Contingency:**
If etcd proves too complex, evaluate MongoDB Change Streams as fallback (trade-off: less reliable watches).

---

### R-002: Worker Startup Time (15-20 minutes)

| Attribute | Value |
|-----------|-------|
| **Category** | Performance |
| **Likelihood** | High (3) |
| **Impact** | Medium (2) |
| **Risk Score** | 6 (High) |
| **Phase** | 3 |

**Description:**
m5zn.metal EC2 instances take 15-20 minutes to start and initialize CML. This limits elasticity and requires predictive scaling.

**Mitigation Strategies:**
1. Predictive scaling based on scheduled timeslots
2. Maintain minimum warm capacity (configurable)
3. Pre-scale based on historical patterns
4. Consider keeping stopped workers (faster restart ~5min)
5. Implement warm pool for high-demand definitions

**Contingency:**
Accept longer lead times; communicate expected wait times to users.

---

### R-003: CML API Reliability

| Attribute | Value |
|-----------|-------|
| **Category** | Integration |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | 2 |

**Description:**
CML API may timeout or return errors during lab import/start operations. Network issues between CCM and workers can cause failures.

**Mitigation Strategies:**
1. Implement retry logic with exponential backoff
2. Circuit breaker pattern for repeated failures
3. Timeout configuration per operation type
4. Health checks before operations
5. Detailed error logging for troubleshooting

**Contingency:**
Manual recovery procedures documented in runbooks.

---

### R-004: State Synchronization (etcd ↔ MongoDB)

| Attribute | Value |
|-----------|-------|
| **Category** | Data Integrity |
| **Likelihood** | Low (1) |
| **Impact** | High (3) |
| **Risk Score** | 3 (Medium) |
| **Phase** | 1-2 |

**Description:**
Dual storage architecture (etcd for state, MongoDB for specs) introduces potential for inconsistency.

**Mitigation Strategies:**
1. Clear data ownership per ADR-005
2. MongoDB as source of truth for aggregates
3. etcd only for coordination state
4. Reconciliation on startup
5. Monitoring for state drift

**Contingency:**
Reconciliation job to fix inconsistencies; manual intervention procedures.

---

### R-005: Leader Election Failures

| Attribute | Value |
|-----------|-------|
| **Category** | High Availability |
| **Likelihood** | Low (1) |
| **Impact** | High (3) |
| **Risk Score** | 3 (Medium) |
| **Phase** | 2-3 |

**Description:**
Leader election for Scheduler/Controller could fail or cause split-brain scenarios.

**Mitigation Strategies:**
1. Use proven etcd lease mechanism
2. Short lease TTL (15s) for fast failover
3. Idempotent operations (safe to replay)
4. Fencing tokens for operations
5. Comprehensive testing of failover scenarios

**Contingency:**
Manual leadership override via admin API.

---

### R-006: Port Allocation Conflicts

| Attribute | Value |
|-----------|-------|
| **Category** | Concurrency |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | 1 |

**Description:**
Concurrent port allocations could lead to conflicts if not properly synchronized.

**Mitigation Strategies:**
1. etcd transactions for atomic allocation
2. Compare-and-swap semantics
3. Bitmap-based allocation for efficiency
4. Port validation before use
5. Automatic conflict detection and retry

**Contingency:**
Force release and re-allocate ports.

---

### R-007: Lab YAML Format Variations

| Attribute | Value |
|-----------|-------|
| **Category** | Integration |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | 2 |

**Description:**
Lab YAML files may have variations in format that break the rewriting logic.

**Mitigation Strategies:**
1. Extensive test fixtures with real lab YAMLs
2. Graceful error handling
3. YAML validation before and after rewriting
4. ruamel.yaml for format preservation
5. Logging of rewrite operations

**Contingency:**
Manual YAML fixing; skip problematic sections with warnings.

---

### R-008: Assessment Platform Integration Failures

| Attribute | Value |
|-----------|-------|
| **Category** | Integration |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | 4 |

**Description:**
Assessment Platform may be unavailable or return errors during collection/grading.

**Mitigation Strategies:**
1. Retry logic with exponential backoff
2. Circuit breaker pattern
3. Async event-based communication
4. State machine allows manual intervention
5. Timeout handling

**Contingency:**
Manual grading fallback; instance can be terminated without grading.

---

## 3. Schedule Risks

### R-009: Scope Creep

| Attribute | Value |
|-----------|-------|
| **Category** | Schedule |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | All |

**Description:**
Additional requirements or changes during implementation could extend timeline.

**Mitigation Strategies:**
1. Clear phase boundaries and acceptance criteria
2. Change control process
3. Feature flags for incremental release
4. Prioritize P0 requirements
5. Regular stakeholder alignment

**Contingency:**
Defer P1/P2 features to future releases.

---

### R-010: Learning Curve

| Attribute | Value |
|-----------|-------|
| **Category** | Schedule |
| **Likelihood** | Medium (2) |
| **Impact** | Low (1) |
| **Risk Score** | 2 (Low) |
| **Phase** | 1-2 |

**Description:**
Team may need time to learn etcd operations and patterns.

**Mitigation Strategies:**
1. Pair programming for knowledge sharing
2. Spike tasks for complex areas
3. Documentation as you go
4. External training if needed

**Contingency:**
Buffer time built into estimates.

---

## 4. Operational Risks

### R-011: Cost Overruns (AWS)

| Attribute | Value |
|-----------|-------|
| **Category** | Operations |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Risk Score** | 4 (Medium) |
| **Phase** | 3 |

**Description:**
m5zn.metal instances are expensive. Poor scaling decisions could increase costs.

**Mitigation Strategies:**
1. Aggressive scale-down of idle workers
2. Cost monitoring and alerting
3. Budget limits in AWS
4. Reserved instances for baseline
5. Spot instances for burst (if viable)

**Contingency:**
Emergency manual scale-down procedure.

---

### R-012: Data Loss (etcd)

| Attribute | Value |
|-----------|-------|
| **Category** | Operations |
| **Likelihood** | Low (1) |
| **Impact** | High (3) |
| **Risk Score** | 3 (Medium) |
| **Phase** | All |

**Description:**
etcd cluster failure could lose coordination state.

**Mitigation Strategies:**
1. 3-node etcd cluster (quorum)
2. Regular snapshots (every 30 min)
3. Off-site backup storage
4. Tested restore procedures
5. State reconstruction from MongoDB

**Contingency:**
Restore from backup; reconcile with MongoDB.

---

## 5. Risk Summary

| Risk ID | Risk | Score | Status |
|---------|------|-------|--------|
| R-001 | etcd Operational Complexity | 6 | Active |
| R-002 | Worker Startup Time | 6 | Active |
| R-003 | CML API Reliability | 4 | Active |
| R-004 | State Synchronization | 3 | Active |
| R-005 | Leader Election Failures | 3 | Active |
| R-006 | Port Allocation Conflicts | 4 | Active |
| R-007 | Lab YAML Format Variations | 4 | Active |
| R-008 | Assessment Integration | 4 | Active |
| R-009 | Scope Creep | 4 | Active |
| R-010 | Learning Curve | 2 | Active |
| R-011 | Cost Overruns | 4 | Active |
| R-012 | Data Loss | 3 | Active |

---

## 6. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
