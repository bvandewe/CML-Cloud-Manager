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

        console.log('[SSE] worker.snapshot received:', {
            worker_id: data.worker_id,
            license_status: data.license_status,
            cml_license_info: data.cml_license_info,
            cml_system_health_is_licensed: data.cml_system_health?.is_licensed,
            _reason: data._reason,
        });

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
            cml_license_info: data.cml_license_info,
            cml_system_health: data.cml_system_health,
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

        console.log('[SSE] Calling upsertWorkerSnapshot with:', {
            id: snapshot.id,
            license_status: snapshot.license_status,
            cml_license_info: snapshot.cml_license_info,
            cml_system_health: snapshot.cml_system_health,
        });

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

    // Worker data refreshed
    sseClient.on('worker.data.refreshed', data => {
        console.log('[SSE] Worker data refreshed:', data);
        // Snapshot is already broadcasted by event handler with complete worker data
        // The worker.snapshot event will update the UI automatically
        // This event is just for user feedback (e.g., showing a toast notification)
    });

    // Worker imported - same as data refreshed (will auto-trigger refresh)
    sseClient.on('worker.imported', async data => {
        console.log('[SSE] Worker imported, will receive snapshot shortly:', data);
        // Snapshot is already broadcasted by event handler, no need to refetch
        // The worker.data.refreshed event will come after the scheduled refresh completes
    });

    // License registration started
    sseClient.on('worker.license.registration.started', data => {
        console.log('[SSE] License registration started:', data);
        const workerId = data.worker_id;
        if (workerId) {
            // Mark worker as having license operation in progress
            updateWorkerMetrics(workerId, { license_operation_in_progress: true });
        }
    });

    // License registration completed
    sseClient.on('worker.license.registration.completed', data => {
        console.log('[SSE] License registration completed:', data);
        const workerId = data.worker_id;
        if (workerId) {
            // Clear operation flag and update license status
            updateWorkerMetrics(workerId, {
                license_operation_in_progress: false,
                license_status: 'registered',
            });

            // Snapshot is already broadcasted by event handler, no need to refetch
            // The worker.snapshot event will update the UI with complete data
        }
    });

    // License registration failed
    sseClient.on('worker.license.registration.failed', data => {
        console.log('[SSE] License registration failed:', data);
        const workerId = data.worker_id;
        if (workerId) {
            updateWorkerMetrics(workerId, { license_operation_in_progress: false });
        }
    });

    // License deregistered
    sseClient.on('worker.license.deregistered', data => {
        console.log('[SSE] License deregistered:', data);
        const workerId = data.worker_id;
        if (workerId) {
            updateWorkerMetrics(workerId, {
                license_status: 'unregistered',
            });

            // Snapshot is already broadcasted by event handler, no need to refetch
            // The worker.snapshot event will update the UI with complete data including license_status
        }
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
