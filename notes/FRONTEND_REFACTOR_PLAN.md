## Frontend Refactor Plan (Workers UI)

### Assessment Summary

The current `workers.js` (~3.3K LOC) acts as a monolithic God module combining: state management, network requests, SSE wiring, rendering logic, modal lifecycle, caching (localStorage), timing/countdown, and formatting/templating. This produces:

1. High cognitive load & fragile coupling between concerns
2. Redundant network requests (multiple identical worker detail fetches)
3. Race conditions for metrics timing (countdown & last refreshed header not updating reliably)
4. Mixed sources of truth (localStorage, `workersData`, `currentWorkerDetails`, modal dataset, SSE payloads)
5. Single large HTML string templates hard to test, diff, or optimize
6. Side-effect heavy functions performing fetch + state mutation + DOM updates simultaneously
7. Lack of a centralized store or event-driven pattern for updates
8. No request deduplication; hydration logic triggers extra fetches
9. Repeated progress bar & threshold logic; duplicated conditional rendering

### Root Causes of Issues

| Problem | Cause |
|---------|-------|
| Triple worker detail requests | Fallback refetch, metrics hydration refetch, SSE-triggered metrics fetch using ID instead of existing snapshot |
| Countdown not updating | Start triggered before timing info persisted; no subscription model; overwrites / stale localStorage reads |
| Inconsistent utilization | Metrics section refetch hydrates missing utilization values ad-hoc, causing flicker and load |
| Hard to extend/test | Monolithic file prevents isolation of logic for unit tests |

### Guiding Principles

1. Single Source of Truth: In-memory store for workers & timing metadata
2. Explicit Data Flow: SSE -> normalize -> store update -> subscribed components re-render
3. Request Deduplication: Cache in-flight worker detail requests keyed by region + id
4. Separation of Concerns: Pure rendering functions; no hidden side-effects
5. Minimal LocalStorage Usage: Persist only durable preferences; ephemeral timing stays in memory
6. Progressive Refactor: Introduce store & dedup before deep componentization

### Phased Plan

Phase 1: Introduce `workerStore.js` (Map-based store, subscription API, inflight request dedup) and route all detail fetches through it. Remove fallback/hydration refetches.
Phase 2: Extract rendering concerns (overview panel, metrics panel, CML panel) into separate modules under `components/`.
Phase 3: Replace direct DOM mutation calls from SSE handlers with store updates + subscribed re-render functions.
Phase 4: Consolidate timing/countdown logic into a dedicated `metricsTiming.js` component that subscribes to store changes.
Phase 5: Remove localStorage timing dependency; store maintains timing; localStorage limited to user preferences (sorting/filtering).
Phase 6: Introduce TypeScript typings (Worker, WorkerTiming, SnapshotEvent) & unit tests (store updates, countdown calculations, dedup correctness).
Phase 7: Optimize template rendering (consider lightweight template helper or small view library) + accessibility (ARIA roles, focus management).

### Immediate Changes Implemented (Phase 1 Start)

1. Added `workerStore.js` with: workers map, timing map, active worker id, inflight promise dedup, subscription interface.
2. Replaced direct `workersApi.getWorkerDetails` calls with store-backed `fetchWorkerDetails`.
3. Removed fallback & metrics hydration refetch blocks to eliminate redundant requests.
4. SSE snapshot handler now upserts into store & updates timing metadata.

### Next Recommended Steps

1. Extract metrics rendering into `metricsPanel.js` (Phase 2)
2. Migrate countdown logic to a store-subscribed component and remove duplicated header update calls.
3. Introduce request reason logging (`reason=modal_open|sse_update|manual_refresh`) for monitoring.
4. Begin unit tests for store (dedup, upsert, timing) and countdown calculations.

### Rollback Strategy

All Phase 1 changes are additive or replace small call sites. If issues arise, revert `workerStore.js` and associated import patches; restore previous direct API calls.

### Acceptance Criteria for Phase 1

1. Opening worker modal triggers at most one worker detail fetch (unless genuinely stale).
2. SSE updates do not trigger additional worker detail fetches for the active worker.
3. Countdown & last refreshed header can access timing data via store (even if display logic pending full migration).

### Open Questions

1. Should timing metadata be sourced exclusively from backend snapshot to avoid UI drift? (Recommended: Yes)
2. Do we need partial vs full snapshot distinction for selective re-render? (Likely in Phase 3.)
3. Should metrics utilization fallback to previous values if missing in new snapshot? (Consider storing last-known metrics in store.)

### Reference Implementation Notes

- Store kept framework-agnostic (plain JS) for low coupling
- Dedup uses Map with key `${region}:${id}`; promise removed on completion/failure
- Upsert merges snapshot fields incrementally; extend later with diff logic if needed

---
Document maintained under version control to enable resumption after interruptions. Update with each completed phase.
