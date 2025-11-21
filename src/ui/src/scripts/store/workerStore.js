/**
 * workerStore.js
 * Central in-memory store for worker data, timing metadata, and request deduplication.
 *
 * MIGRATION NOTE: Now publishes to EventBus in addition to legacy listeners.
 * Legacy subscribe() maintained for backward compatibility during migration.
 */

import * as workersApi from '../api/workers.js';
import { eventBus, EventTypes } from '../core/EventBus.js';

const state = {
    workers: new Map(), // id -> worker object
    timing: new Map(), // id -> { pollInterval, nextRefreshAt, lastRefreshedAt }
    activeWorkerId: null,
    listeners: new Set(), // Legacy listeners (will be removed)
    inflight: new Map(), // key: region:id -> promise
};

function emit() {
    console.log('[workerStore] emit() called - notifying', state.listeners.size, 'legacy listeners');
    console.log('[workerStore] Current state:', {
        workerCount: state.workers.size,
        workers: Array.from(state.workers.values()).map(w => ({
            id: w.id,
            name: w.name,
            license_status: w.license_status,
            cml_license_info: w.cml_license_info,
        })),
    });

    // Legacy listener support (backward compatibility)
    state.listeners.forEach(fn => {
        try {
            fn(state);
        } catch (e) {
            console.error('[workerStore] listener error', e);
        }
    });
}

// Legacy subscription API (backward compatibility)
export function subscribe(fn) {
    state.listeners.add(fn);
    return () => state.listeners.delete(fn);
}

export function setActiveWorker(id) {
    state.activeWorkerId = id;
    emit();
}

export function getActiveWorker() {
    return state.workers.get(state.activeWorkerId) || null;
}

export function getWorker(id) {
    return state.workers.get(id) || null;
}

export function getAllWorkers() {
    return Array.from(state.workers.values());
}

export function upsertWorkerSnapshot(snapshot) {
    if (!snapshot || !snapshot.id) return;
    const existing = state.workers.get(snapshot.id) || {};
    const isNew = !existing.id;

    console.log('[workerStore] upsertWorkerSnapshot called:', {
        id: snapshot.id,
        isNew,
        license_status: snapshot.license_status,
        cml_license_info: snapshot.cml_license_info,
        existing_license_status: existing.license_status,
        existing_cml_license_info: existing.cml_license_info,
    });

    // Merge snapshot into existing, allowing null to overwrite (clears stale data)
    // Only skip undefined values to preserve existing data when snapshot is partial
    const merged = { ...existing };
    Object.entries(snapshot).forEach(([k, v]) => {
        if (v !== undefined) {
            merged[k] = v; // Allow null to overwrite
        }
    });

    console.log('[workerStore] After merge:', {
        id: merged.id,
        license_status: merged.license_status,
        cml_license_info: merged.cml_license_info,
    });

    state.workers.set(snapshot.id, merged);

    // Publish to EventBus
    if (isNew) {
        eventBus.emit(EventTypes.WORKER_CREATED, merged);
    } else {
        eventBus.emit(EventTypes.WORKER_SNAPSHOT, merged);
    }

    // Legacy emit (backward compatibility)
    emit();
}

// Specialized update for metrics-only SSE events
export function updateWorkerMetrics(id, metrics) {
    if (!id) return;
    const existing = state.workers.get(id) || { id };
    const updated = { ...existing, ...metrics };
    state.workers.set(id, updated);

    // Publish to EventBus
    eventBus.emit(EventTypes.WORKER_METRICS_UPDATED, {
        worker_id: id,
        ...metrics,
    });

    // Legacy emit (backward compatibility)
    emit();
}

export function removeWorker(id) {
    if (!id) return;
    const worker = state.workers.get(id);
    state.workers.delete(id);
    state.timing.delete(id);
    if (state.activeWorkerId === id) state.activeWorkerId = null;

    // Publish to EventBus
    if (worker) {
        eventBus.emit(EventTypes.WORKER_DELETED, { worker_id: id, worker });
    }

    // Legacy emit (backward compatibility)
    emit();
}

export function updateTiming(id, { poll_interval, next_refresh_at, last_refreshed_at }) {
    if (!id) return;
    state.timing.set(id, {
        pollInterval: poll_interval,
        nextRefreshAt: next_refresh_at,
        lastRefreshedAt: last_refreshed_at,
        updatedAt: new Date().toISOString(),
    });
    emit();
}

export function getTiming(id) {
    return state.timing.get(id) || null;
}

export async function fetchWorkerDetails(region, id, options = {}) {
    const key = `${region}:${id}`;
    // Determine if we already have a fully populated worker
    if (!options.force) {
        const existing = state.workers.get(id);
        if (existing) {
            const detailFields = ['ami_id', 'ami_name', 'ami_creation_date', 'created_at', 'cml_license_info'];
            const hasDetails = detailFields.some(f => existing[f] !== undefined && existing[f] !== null);
            if (existing.detailsLoaded || hasDetails) {
                return existing; // sufficient detail; skip network
            }
        }
    }
    // Deduplicate in-flight requests
    if (state.inflight.has(key)) {
        return state.inflight.get(key);
    }
    const promise = workersApi
        .getWorkerDetails(region, id)
        .then(worker => {
            // Normalize potential timing fields
            if (worker.cloudwatch_poll_interval && !worker.poll_interval) {
                worker.poll_interval = worker.cloudwatch_poll_interval;
            }
            if (worker.cloudwatch_next_refresh_at && !worker.next_refresh_at) {
                worker.next_refresh_at = worker.cloudwatch_next_refresh_at;
            }
            worker.detailsLoaded = true;
            upsertWorkerSnapshot(worker);
            if (worker.poll_interval && worker.next_refresh_at) {
                updateTiming(worker.id, {
                    poll_interval: worker.poll_interval,
                    next_refresh_at: worker.next_refresh_at,
                    last_refreshed_at: worker.cloudwatch_last_collected_at || new Date().toISOString(),
                });
            }
            return worker;
        })
        .catch(err => {
            console.error('[workerStore] fetchWorkerDetails error', { region, id, err });
            throw err;
        })
        .finally(() => {
            state.inflight.delete(key);
        });
    state.inflight.set(key, promise);
    return promise;
}

export function getStateSnapshot() {
    return {
        activeWorkerId: state.activeWorkerId,
        workersCount: state.workers.size,
        timingCount: state.timing.size,
        inflightCount: state.inflight.size,
    };
}

// Debug helper
export function logStoreSnapshot(label = 'store') {
    const snapshot = getStateSnapshot();
    console.log(`[workerStore] ${label}`, snapshot);
}

// TEST-ONLY: reset store state (used by unit tests)
export function __resetStoreForTests() {
    state.workers.clear();
    state.timing.clear();
    state.inflight.clear();
    state.activeWorkerId = null;
}
