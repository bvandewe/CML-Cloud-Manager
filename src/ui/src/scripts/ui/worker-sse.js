// Worker SSE handlers module
// Extracted from workers.js to reduce file size and isolate realtime logic.

import sseClient from '../services/sse-client.js';
import { showToast } from './notifications.js';
import * as bootstrap from 'bootstrap';

/**
 * Initialize all worker-related SSE handlers.
 * @param {Object} deps
 * @param {Function} deps.upsertWorkerSnapshot
 * @param {Function} deps.updateWorkerMetrics
 * @param {Function} deps.updateTiming
 * @param {Function} deps.getCurrentWorkerDetails - () => currentWorkerDetails object
 * @param {Function} deps.onLabsTabShouldReload - callback to reload labs tab
 */
export function initWorkerSSE({ upsertWorkerSnapshot, updateWorkerMetrics, updateTiming, getCurrentWorkerDetails, onLabsTabShouldReload }) {
    console.log('[worker-sse] Registering SSE handlers');

    // Debounce map for labs reload per worker
    const labsReloadTimers = new Map();
    const scheduleLabsReload = workerId => {
        if (!workerId) return;
        if (labsReloadTimers.has(workerId)) {
            clearTimeout(labsReloadTimers.get(workerId));
        }
        const t = setTimeout(() => {
            labsReloadTimers.delete(workerId);
            try {
                onLabsTabShouldReload && onLabsTabShouldReload();
            } catch (e) {
                console.error('[worker-sse] labs reload error', e);
            }
        }, 200); // short debounce to coalesce rapid events
        labsReloadTimers.set(workerId, t);
    };

    // Full snapshot (authoritative)
    sseClient.on('worker.snapshot', msg => {
        const data = msg.data || msg;
        if (!data || !data.worker_id) return;
        const nowIso = new Date().toISOString();
        const snapshot = {
            id: data.worker_id,
            name: data.name,
            aws_region: data.region,
            status: data.status,
            service_status: data.service_status,
            instance_type: data.instance_type,
            aws_instance_id: data.aws_instance_id,
            public_ip: data.public_ip,
            private_ip: data.private_ip,
            aws_tags: data.aws_tags || {},
            ami_id: data.ami_id,
            ami_name: data.ami_name,
            ami_description: data.ami_description,
            ami_creation_date: data.ami_creation_date,
            https_endpoint: data.https_endpoint,
            license_status: data.license_status,
            cml_version: data.cml_version,
            cml_ready: data.cml_ready,
            cml_uptime_seconds: data.cml_uptime_seconds,
            cml_labs_count: data.cml_labs_count,
            cpu_utilization: data.cpu_utilization ?? data.cloudwatch_cpu_utilization,
            memory_utilization: data.memory_utilization ?? data.cloudwatch_memory_utilization,
            storage_utilization: data.storage_utilization ?? data.cloudwatch_storage_utilization,
            poll_interval: data.poll_interval,
            next_refresh_at: data.next_refresh_at,
            created_at: data.created_at,
            updated_at: data.updated_at || nowIso,
            terminated_at: data.terminated_at,
            _reason: data._reason || 'snapshot',
        };
        upsertWorkerSnapshot(snapshot);
        if (snapshot.poll_interval && snapshot.next_refresh_at) {
            updateTiming(snapshot.id, {
                poll_interval: snapshot.poll_interval,
                next_refresh_at: snapshot.next_refresh_at,
                last_refreshed_at: nowIso,
            });
        }
    });

    // Metrics updated
    sseClient.on('worker.metrics.updated', data => {
        const timestamp = new Date().toISOString();
        console.log(`[SSE] [${timestamp}] Worker metrics updated:`, {
            worker_id: data.worker_id,
            cpu_utilization: data.cpu_utilization,
            memory_utilization: data.memory_utilization,
            poll_interval: data.poll_interval,
            next_refresh_at: data.next_refresh_at,
            has_timing_info: !!(data.poll_interval && data.next_refresh_at),
        });
        if (data.worker_id) {
            updateWorkerMetrics(data.worker_id, {
                cpu_utilization: data.cpu_utilization ?? data.cloudwatch_cpu_utilization,
                memory_utilization: data.memory_utilization ?? data.cloudwatch_memory_utilization,
                storage_utilization: data.storage_utilization ?? data.cloudwatch_storage_utilization,
            });
            if (data.next_refresh_at || data.poll_interval) {
                updateTiming(data.worker_id, {
                    poll_interval: data.poll_interval || 300,
                    next_refresh_at: data.next_refresh_at || new Date(Date.now() + (data.poll_interval || 300) * 1000).toISOString(),
                    last_refreshed_at: new Date().toISOString(),
                });
            }
        }
    });

    // Labs updated
    sseClient.on('worker.labs.updated', data => {
        console.log('[SSE] Worker labs updated:', data);
        if (data.worker_id) {
            // Update worker snapshot with labs count so store emit triggers table/card re-render
            const labsCount = data.labs_synced ?? data.labs_count ?? null;
            const snapshot = { id: data.worker_id };
            if (labsCount !== null) snapshot.cml_labs_count = labsCount;
            snapshot.updated_at = new Date().toISOString();
            snapshot._reason = 'labs_updated_sse';
            upsertWorkerSnapshot(snapshot);
        }
        const current = getCurrentWorkerDetails();
        if (current && current.id === data.worker_id) {
            // Always schedule a reload for current worker; will no-op if tab later opened.
            scheduleLabsReload(current.id);
            const detailsModalEl = document.getElementById('workerDetailsModal');
            const isDetailsOpen = detailsModalEl && detailsModalEl.classList.contains('show');
            const labsTabBtn = document.getElementById('labs-tab');
            const labsPanel = document.getElementById('labs-panel');
            const labsActive = (labsTabBtn && labsTabBtn.classList.contains('active')) || (labsPanel && labsPanel.classList.contains('active'));
            if (isDetailsOpen && labsActive) {
                console.log('[SSE] Immediate labs reload (active tab)');
                scheduleLabsReload(current.id);
            }
        }
    });

    // Status updated (use new_status, include transition initiation timestamp for timers)
    sseClient.on('worker.status.updated', data => {
        console.log('[SSE] Worker status updated:', data);
        if (data.worker_id) {
            const update = { id: data.worker_id, status: data.new_status || data.status };
            if (data.transition_initiated_at) {
                if ((data.new_status || data.status) === 'pending') {
                    update.start_initiated_at = data.transition_initiated_at;
                } else if ((data.new_status || data.status) === 'stopping') {
                    update.stop_initiated_at = data.transition_initiated_at;
                }
            }
            upsertWorkerSnapshot(update);
        }
    });

    // Worker created (seed minimal snapshot promptly)
    sseClient.on('worker.created', data => {
        console.log('[SSE] Worker created:', data);
        if (data.worker_id) {
            upsertWorkerSnapshot({
                id: data.worker_id,
                status: data.status || 'pending',
                name: data.name,
                aws_region: data.region,
                instance_type: data.instance_type,
                created_at: data.created_at,
            });
        }
    });

    // Worker terminated
    sseClient.on('worker.terminated', data => {
        console.log('[SSE] Worker terminated:', data);
        if (data.worker_id) upsertWorkerSnapshot({ id: data.worker_id, status: 'terminated', terminated_at: new Date().toISOString() });
        const current = getCurrentWorkerDetails();
        if (current && current.id === data.worker_id) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('workerDetailsModal'));
            if (modal) modal.hide();
        }
    });

    // Refresh requested
    sseClient.on('worker.refresh.requested', data => {
        console.log('[SSE] Worker refresh requested:', data);
        const etaSec = data.eta_seconds || 1;
        showToast(`Metrics refresh scheduled for worker (ETA: ${etaSec}s)`, 'info');
    });

    // Refresh skipped
    sseClient.on('worker.refresh.skipped', data => {
        console.log('[SSE] Worker refresh skipped:', data);
        const reason = data.reason || 'unknown';
        const etaSec = data.seconds_until_next;
        let message = `Refresh skipped: ${reason}`;
        if (etaSec) message += ` (retry in ${etaSec}s)`;
        showToast(message, 'warning');
    });

    // Worker data refreshed - reload worker from DB
    sseClient.on('worker.data.refreshed', async data => {
        console.log('[SSE] Worker data refreshed, reloading from DB:', data);
        if (data.worker_id) {
            try {
                // Fetch fresh worker data from DB
                const { getWorkerDetails } = await import('../api/workers.js');
                // Worker region needed - get from existing snapshot
                const existingCard = document.querySelector(`[data-worker-id="${data.worker_id}"]`);
                if (existingCard) {
                    const region = existingCard.dataset.workerRegion || 'us-east-1';
                    const workerDetails = await getWorkerDetails(region, data.worker_id);

                    // Update snapshot with fresh data from DB
                    upsertWorkerSnapshot({
                        id: workerDetails.id,
                        name: workerDetails.name,
                        aws_region: workerDetails.aws_region,
                        status: workerDetails.status,
                        service_status: workerDetails.service_status,
                        instance_type: workerDetails.instance_type,
                        aws_instance_id: workerDetails.aws_instance_id,
                        public_ip: workerDetails.public_ip,
                        private_ip: workerDetails.private_ip,
                        ami_id: workerDetails.ami_id,
                        ami_name: workerDetails.ami_name,
                        ami_description: workerDetails.ami_description,
                        ami_creation_date: workerDetails.ami_creation_date,
                        https_endpoint: workerDetails.https_endpoint,
                        license_status: workerDetails.license_status,
                        cml_version: workerDetails.cml_version,
                        cml_ready: workerDetails.cml_ready,
                        cml_uptime_seconds: workerDetails.cml_uptime_seconds,
                        cml_labs_count: workerDetails.cml_labs_count,
                        cpu_utilization: workerDetails.cpu_utilization,
                        memory_utilization: workerDetails.memory_utilization,
                        storage_utilization: workerDetails.storage_utilization,
                        poll_interval: workerDetails.poll_interval,
                        next_refresh_at: workerDetails.next_refresh_at,
                        created_at: workerDetails.created_at,
                        updated_at: workerDetails.updated_at,
                        terminated_at: workerDetails.terminated_at,
                        _reason: 'data_refreshed',
                    });
                    console.log(`[SSE] Worker ${data.worker_id} data reloaded from DB`);
                }
            } catch (error) {
                console.error('[SSE] Failed to reload worker data:', error);
            }
        }
    });

    // Worker imported - same as data refreshed (will auto-trigger refresh)
    sseClient.on('worker.imported', async data => {
        console.log('[SSE] Worker imported, will receive snapshot shortly:', data);
        // Snapshot is already broadcasted by event handler, no need to refetch
        // The worker.data.refreshed event will come after the scheduled refresh completes
    });

    console.log('[worker-sse] Handlers registered');
}

/**
 * Setup SSE connection status badge updates
 */
export function setupSSEStatusIndicator() {
    const container = document.getElementById('sse-connection-status');
    if (!container) return;
    const update = status => {
        let cls = 'bg-secondary';
        let text = 'Realtime: ' + status;
        switch (status) {
            case 'connected':
                cls = 'bg-success';
                text = 'Realtime: connected';
                break;
            case 'reconnecting':
                cls = 'bg-warning text-dark';
                text = 'Realtime: reconnecting';
                break;
            case 'disconnected':
                cls = 'bg-danger';
                text = 'Realtime: disconnected';
                break;
            case 'error':
                cls = 'bg-danger';
                text = 'Realtime: error';
                break;
            default:
                cls = 'bg-secondary';
        }
        container.innerHTML = `<span class="badge ${cls}">${text}</span>`;
    };
    sseClient.onStatus(update);
}
