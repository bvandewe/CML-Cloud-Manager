# Refresh Worker Metrics Implementation Plan (Revised)

This revision aligns the plan with the CURRENT implementation and defines the delta required to meet the new requirements for asynchronous on‑demand metric refresh via scheduling & SSE broadcasting.

## Recent Simplifications (SSE-First Metadata)

The UI was refactored to remove REST-based worker list fetching and per-row enrichment calls.
It now relies exclusively on `worker.snapshot` SSE events for initial population and all subsequent
metadata and telemetry updates. Legacy functions `loadWorkers()` and `enrichWorkersTableMetrics()`
were deprecated or removed. A minimal placeholder remains only to avoid breaking existing call sites
during transition. This reduces HTTP chatter, eliminates duplication, and ensures a single
authoritative source of truth (aggregate → domain events → snapshot broadcast).

Implications:

- Worker list renders immediately as snapshots arrive; no API fallback unless snapshots fail to appear (lightweight UX message after ~5s).
- Metrics progress bars use values embedded in snapshot (fallback derivation from `cml_system_info` occurs server-side before broadcast).
- Future refresh mechanisms MUST update aggregate state so snapshot + metrics events remain consistent; UI will not parse refresh HTTP responses.
- Documentation updated to describe SSE-first model (see README section "SSE-First Worker Metadata").

## 1. Current State (As Implemented)

Already implemented components (verified in code):

1. `RefreshWorkerMetricsCommand` orchestrates EC2 status, CloudWatch metrics, and CML data (via `SyncWorkerEC2StatusCommand`, `CollectWorkerCloudWatchMetricsCommand`, `SyncWorkerCMLDataCommand`).
2. Recurrent `WorkerMetricsCollectionJob` polls metrics for all active workers at the configured interval (`WORKER_METRICS_POLL_INTERVAL`).
3. `WorkerMetricsService` encapsulates AWS collection logic used by the recurrent job (and indirectly the sub-commands).
4. Domain events (`CMLWorkerTelemetryUpdatedDomainEvent`, etc.) update the aggregate and trigger SSE broadcasts via handlers in `application/events/domain/cml_worker_events.py`.
5. SSE pipeline (`SSEEventRelay`) broadcasts `worker.metrics.updated`, `worker.status.updated`, etc.
6. OTEL gauges for CPU, memory, labs count, and status already updated inside the refresh command handler.
7. Worker aggregate root stores telemetry (CPU, memory, poll interval, next refresh, CML metadata, labs count, etc.).
8. Throttling of manual refresh via `WorkerRefreshThrottle` prevents rapid command repetition.

Outdated items in original plan (now incorrect):

- CQRS violation (controller bypassing mediator) – FIXED: controller dispatches command.
- Missing CML API integration – PARTIALLY FIXED: `SyncWorkerCMLDataCommand` and system info/labs licensing fields present.
- Background job “too many responsibilities” – Partially acceptable trade‑off; it now focuses on polling & updating aggregates. Still does persistence + telemetry but duplication with command logic can be reduced.
- OTEL metrics disconnected – FIXED; gauges set in command handler.

## 2. New Requirements Summary

1. UI triggers a new lightweight on‑demand command: `RequestWorkerMetricsRefreshCommand` (distinct from the full orchestration) per single worker.
2. Command MUST only proceed (schedule execution) if:
    - Worker is RUNNING.
    - No recurrent global metrics job will execute within 10 seconds for the same data set.
3. Command MUST NOT perform synchronous metrics collection; it schedules a one‑time immediate background job (unless imminent global job).
4. UI must receive SSE signal indicating whether refresh will execute or was skipped (e.g. `worker.refresh.requested` or `worker.refresh.skipped`).
5. All metric & metadata updates arrive via SSE only (UI now fully migrated; no synchronous HTTP payload dependency).
6. Recurrent global job continues to poll RUNNING workers and broadcasts metrics via the same SSE event types used by on‑demand refresh.
7. Both flows share the same refresh logic through an application service (single orchestration path) to avoid duplication.
8. Background job executes per worker refresh concurrently (existing semaphore logic remains for multi‑worker polling). For on‑demand single worker job, concurrency is trivial but reuse service.
9. All changes to worker state persisted through aggregate root operations (no bypass writes).

## 3. Gap Analysis (Delta Work)

Missing to meet new requirements:

- Distinct request/schedule command (`RequestWorkerMetricsRefreshCommand`).
- One‑time scheduled job type for single-worker manual refresh (`OnDemandWorkerMetricsRefreshJob`).
- SSE events for refresh ACK/skip (currently only metrics/status events exist).
- Unification: a shared orchestration function/service extracted from synchronous command handler logic so both OnDemand job and recurrent job reuse identical code path.
- Controller endpoint adjustment: return scheduling decision only (stop returning aggregated metrics payload).
- Frontend: adapt `workersApi.refreshWorker` to treat response as acknowledgement and rely solely on SSE updates.

## 4. Revised Architectural Objectives

Objective A: Asynchronous manual refresh (low latency) – schedule & respond quickly.
Objective B: Single orchestration core – no logic drift between command vs job.
Objective C: Event-first UI – all state deltas via SSE; HTTP only for control plane actions.
Objective D: Clear event taxonomy – distinguish request outcome events from metrics update events.

## 5. Proposed Components

### 5.1 New Command: RequestWorkerMetricsRefreshCommand

Responsibilities:

- Validate worker existence & RUNNING status.
- Check throttle & imminent global job window (≤10s).
- If skipped → emit SSE `worker.refresh.skipped` with reason and next expected time.
- If accepted → schedule `OnDemandWorkerMetricsRefreshJob` immediately (run_at ≈ now) then emit `worker.refresh.requested` SSE.
- Return lightweight HTTP 200 `{ scheduled: true|false, reason?, eta_seconds? }`.

### 5.2 One-Time Job: OnDemandWorkerMetricsRefreshJob

Responsibilities:

- Execute shared orchestration (same as current RefreshWorkerMetricsCommand logic) for a single worker.
- Persist aggregate changes (domain events fire → existing `worker.metrics.updated`).
- Include trace attributes `refresh.trigger=on_demand`.

### 5.3 Shared Orchestration Service

Create `WorkerMetricsOrchestrator` service (or extend `WorkerMetricsService`) with method `refresh_full(worker_id, include_cml: bool = True)` performing:

1. Sync EC2 status.
2. Collect CloudWatch metrics (if running).
3. Sync CML data (if running & endpoint available).
4. Update aggregate + record telemetry (emits domain events).

Command handler & jobs delegate to this method.

### 5.4 SSE Event Extensions

Add two new broadcasts (no new domain events needed – can be application events):

- `worker.refresh.requested` → { worker_id, requested_at, eta_seconds }
- `worker.refresh.skipped` → { worker_id, skipped_at, reason, seconds_until_next }.

These fire inside the request command handler (using `SSEEventRelay` directly, not domain events).
Metrics updates remain via existing domain telemetry event → `worker.metrics.updated`.

## 6. Flow Diagrams (Conceptual)

On-Demand Request:
UI Button → POST /refresh-async → RequestWorkerMetricsRefreshCommand → (schedule or skip) → SSE (requested|skipped) → Background Job → Orchestrator → Aggregate updates → Domain telemetry event → SSE `worker.metrics.updated`.

Global Polling:
APScheduler triggers WorkerMetricsCollectionJob → For each RUNNING worker (concurrent) → Orchestrator → Aggregate updates → Domain telemetry event → SSE `worker.metrics.updated`.

## 7. Detailed Logic & Edge Cases

| Check | Outcome | Action |
|-------|---------|--------|
| Worker not found | 404 | Return error (no SSE) |
| Worker not running | Skip | SSE `worker.refresh.skipped` reason=not_running |
| Global job in ≤10s | Skip | SSE `worker.refresh.skipped` reason=background_imminent |
| Throttled by min interval | Skip | SSE `worker.refresh.skipped` reason=rate_limited, retry_after |
| Already scheduled on-demand job pending | Skip | SSE `worker.refresh.skipped` reason=already_scheduled |
| Accept | Schedule immediate job | SSE `worker.refresh.requested` |

Idempotent scheduling: deterministic job ID `on_demand_refresh_<worker_id>`; if job exists with next_run_time within threshold → treat as already_scheduled.

## 8. Implementation Steps (Revised)

1. Create `RequestWorkerMetricsRefreshCommand` + handler.
2. Add SSE broadcasts inside handler for request outcome.
3. Add `OnDemandWorkerMetricsRefreshJob` (@backgroundjob scheduled) using run_at wrapper.
4. Extract orchestration logic from existing `RefreshWorkerMetricsCommandHandler` into `WorkerMetricsOrchestrator` (command handler becomes a thin shim calling orchestrator; recurrent job updated similarly).
5. Refactor `RefreshWorkerMetricsCommandHandler` to optionally operate in “direct” mode (for backward compatibility) but mark synchronous path deprecated.
6. Update controller: add `/refresh-async` endpoint invoking new command; deprecate synchronous response fields (or keep legacy endpoint temporarily).
7. Update frontend: change refresh button to call `/refresh-async`; stop parsing metrics from HTTP response; listen only to SSE events for updates.
8. Extend `WorkerRefreshThrottle` to track pending scheduled job state (optional) OR rely solely on APScheduler job presence.
9. Add integration tests: request command scheduling + SSE emitted; job execution triggers telemetry SSE; skip conditions.
10. Update documentation (README, notes) and changelog.

## 9. Data & State Integrity

All writes continue through aggregate root (no direct DB field manipulation). Domain events originate from aggregate changes; SSE broadcast for request/skip is orthogonal and does not mutate state.

## 10. Observability Enhancements

- Add trace attribute `refresh.mode=on_demand|recurrent`.
- Add counter `cml.worker.refresh.requests` with labels (mode, outcome, reason?).
- Include scheduling latency: time from request command to metrics updated event (frontend can measure with timestamps).

## 11. Backward Compatibility Strategy

- Keep existing `/refresh` synchronous endpoint for a short deprecation period; mark response field `deprecated=true`.
- Frontend feature flag (or version check) to switch to async endpoint once backend changes deployed.

## 12. Testing Strategy (Updated)

Unit:

- Orchestrator logic (mock sub-commands or AWS/CML clients).
- Request command decision matrix (throttle, imminent job, not running).

Integration:

- End-to-end async refresh (HTTP → schedule → job run → SSE metrics).
- Recurrent job multi-worker concurrency and SSE broadcast count.

Frontend Manual:

- Press Refresh: immediate SSE request event; later metrics update event with new telemetry.
- Edge: pressing twice rapidly triggers rate_limited skip SSE.
- Edge: request just before global job → skip SSE reason=background_imminent.

## 13. Event Taxonomy (Final)

| Event | Source | Purpose |
|-------|--------|---------|
| worker.refresh.requested | command handler | Acknowledges accepted scheduled refresh |
| worker.refresh.skipped | command handler | Explains why refresh not scheduled |
| worker.metrics.updated | domain telemetry event | Delivers new metrics & timing info |
| worker.status.updated | domain status event | Status lifecycle changes |
| worker.created / terminated | domain | Lifecycle notifications |

## 14. Success Criteria (Revised)

1. Asynchronous endpoint returns within <100ms under normal load.
2. Refresh request always yields at least one SSE (requested or skipped) within 1s.
3. Metrics SSE arrives for accepted requests within configurable timeout (e.g. 15s) unless failed.
4. No duplicated refresh logic across command/job – single orchestrator.
5. Aggregate root remains sole persistence path; domain events fire for all metric changes.
6. No synchronous metrics payload dependency in UI.

## 15. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Lost SSE while scheduling | UI lacks feedback | Add client timeout & fallback poll |
| Job scheduling race conditions | Duplicate jobs | Deterministic job ID + existence check |
| Increased complexity | Maintenance overhead | Central orchestration service & clear docs |
| User confusion during transition | UX inconsistency | Deprecation notice + consistent toasts |

## 16. Documentation Updates

Update:

- This plan file (done).
- `CHANGELOG.md` (feature: async worker metric refresh).
- `README.md` (explain event-driven refresh model).
- `notes/` add `ASYNC_WORKER_REFRESH_DESIGN.md` (optional) with sequence diagrams.

---
This revised plan reflects current implementation status and enumerates only the necessary delta to achieve the new asynchronous, SSE-first refresh workflow.
