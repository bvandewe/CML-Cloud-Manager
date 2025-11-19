/**
 * workerStore.js
 * Central in-memory store for worker data, timing metadata, and request deduplication.
 */

import * as workersApi from '../api/workers.js';

const state = {
    workers: new Map(), // id -> worker object
    timing: new Map(), // id -> { pollInterval, nextRefreshAt, lastRefreshedAt }
    activeWorkerId: null,
    listeners: new Set(),
    inflight: new Map(), // key: region:id -> promise
};

function emit() {
    state.listeners.forEach(fn => {
        try {
            fn(state);
        } catch (e) {
            console.error('[workerStore] listener error', e);
        }
    });
}

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
    // Only overwrite with defined values to avoid erasing detailed data with undefined
    const merged = { ...existing };
    Object.entries(snapshot).forEach(([k, v]) => {
        if (v !== undefined && v !== null) {
            merged[k] = v;
        }
    });
    state.workers.set(snapshot.id, merged);
    emit();
}

// Specialized update for metrics-only SSE events
export function updateWorkerMetrics(id, metrics) {
    if (!id) return;
    const existing = state.workers.get(id) || { id };
    state.workers.set(id, { ...existing, ...metrics });
    emit();
}

export function removeWorker(id) {
    if (!id) return;
    state.workers.delete(id);
    state.timing.delete(id);
    if (state.activeWorkerId === id) state.activeWorkerId = null;
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
