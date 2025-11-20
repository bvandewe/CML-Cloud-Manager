// worker-monitoring.js
// Worker-specific monitoring tab logic

import { escapeHtml } from '../components/escape.js';
import { formatDate, getRelativeTime } from '../utils/dates.js';
import { getActiveWorker } from '../store/workerStore.js';
import { sseClient } from '../services/sse-client.js';

/**
 * Helper to format date with full timestamp and relative time tooltip
 * @param {string} dateString - ISO date string
 * @returns {string} HTML with formatted timestamp and info icon with relative time tooltip
 */
function formatDateWithRelative(dateString) {
    if (!dateString) return '<span class="text-muted">Never</span>';
    try {
        const date = new Date(dateString);
        const formatted = formatDate(dateString);
        const relative = getRelativeTime(date);
        const uniqueId = `date-tooltip-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        return `${formatted} <i class="bi bi-info-circle text-muted date-tooltip-icon"
                data-bs-toggle="tooltip"
                data-bs-placement="top"
                data-bs-title="${relative}"
                data-tooltip-id="${uniqueId}"
                style="cursor: help;"></i>`;
    } catch (e) {
        return dateString;
    }
}

/**
 * Render the monitoring tab with worker-specific monitoring data
 * @param {Object} worker - Worker object with monitoring fields
 */
export function renderMonitoringTab(worker) {
    const monitoringContent = document.getElementById('worker-details-monitoring');
    if (!monitoringContent) return;

    if (!worker) {
        monitoringContent.innerHTML = `
            <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle"></i> Worker data not available
            </div>`;
        return;
    }

    // Format all date fields upfront
    const lastActivity = formatDateWithRelative(worker.last_activity_at);
    const lastCheck = formatDateWithRelative(worker.last_activity_check_at);
    const nextCheck = formatDateWithRelative(worker.next_idle_check_at);
    const targetPause = formatDateWithRelative(worker.target_pause_at);
    const lastPaused = formatDateWithRelative(worker.last_paused_at);
    const lastResumed = formatDateWithRelative(worker.last_resumed_at);
    const nextRefresh = formatDateWithRelative(worker.next_refresh_at);
    const cmlLastSynced = formatDateWithRelative(worker.cml_last_synced_at);
    const cloudwatchLast = formatDateWithRelative(worker.cloudwatch_last_collected_at);

    // Build monitoring settings section
    let html = '<div class="row g-4">';

    // Idle Detection Settings Card
    html += `
        <div class="col-md-6">
            <div class="card h-100">
                <div class="card-header bg-primary text-white">
                    <h6 class="mb-0"><i class="bi bi-activity"></i> Idle Detection</h6>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        <dt class="col-sm-6">Status:</dt>
                        <dd class="col-sm-6">
                            <span class="badge ${worker.is_idle_detection_enabled ? 'bg-success' : 'bg-secondary'}">
                                ${worker.is_idle_detection_enabled ? 'Enabled' : 'Disabled'}
                            </span>
                        </dd>

                        <dt class="col-sm-6">Last Activity:</dt>
                        <dd class="col-sm-6">
                            ${lastActivity}
                        </dd>

                        <dt class="col-sm-6">Last Check:</dt>
                        <dd class="col-sm-6">
                            ${lastCheck}
                        </dd>

                        <dt class="col-sm-6">Next Check:</dt>
                        <dd class="col-sm-6">
                            ${nextCheck}
                        </dd>

                        <dt class="col-sm-6">Target Pause:</dt>
                        <dd class="col-sm-6">
                            ${targetPause}
                        </dd>
                    </dl>
                </div>
            </div>
        </div>`;

    // Pause/Resume History Card
    html += `
        <div class="col-md-6">
            <div class="card h-100">
                <div class="card-header bg-info text-white">
                    <h6 class="mb-0"><i class="bi bi-pause-circle"></i> Pause/Resume History</h6>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        <dt class="col-sm-6">Auto Pauses:</dt>
                        <dd class="col-sm-6"><strong>${worker.auto_pause_count || 0}</strong></dd>

                        <dt class="col-sm-6">Manual Pauses:</dt>
                        <dd class="col-sm-6"><strong>${worker.manual_pause_count || 0}</strong></dd>

                        <dt class="col-sm-6">Auto Resumes:</dt>
                        <dd class="col-sm-6"><strong>${worker.auto_resume_count || 0}</strong></dd>

                        <dt class="col-sm-6">Manual Resumes:</dt>
                        <dd class="col-sm-6"><strong>${worker.manual_resume_count || 0}</strong></dd>

                        <dt class="col-sm-6">Last Paused:</dt>
                        <dd class="col-sm-6">
                            ${lastPaused}
                        </dd>

                        <dt class="col-sm-6">Last Resumed:</dt>
                        <dd class="col-sm-6">
                            ${lastResumed}
                        </dd>
                    </dl>
                </div>
            </div>
        </div>`;

    html += '</div>'; // Close row

    // Last Pause Details Section
    if (worker.last_paused_at) {
        html += `
            <div class="card mt-4">
                <div class="card-header">
                    <h6 class="mb-0"><i class="bi bi-info-circle"></i> Last Pause Details</h6>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        <dt class="col-sm-3">Paused At:</dt>
                        <dd class="col-sm-3">${lastPaused}</dd>

                        <dt class="col-sm-3">Paused By:</dt>
                        <dd class="col-sm-3">${escapeHtml(worker.paused_by || 'Unknown')}</dd>

                        <dt class="col-sm-3">Reason:</dt>
                        <dd class="col-sm-3">
                            <span class="badge ${worker.pause_reason === 'idle_timeout' ? 'bg-warning' : worker.pause_reason === 'manual' ? 'bg-primary' : 'bg-secondary'}">
                                ${escapeHtml(worker.pause_reason || 'Unknown')}
                            </span>
                        </dd>
                    </dl>
                </div>
            </div>`;
    }

    // Metrics Refresh Timing Section
    html += `
        <div class="card mt-4">
            <div class="card-header">
                <h6 class="mb-0"><i class="bi bi-clock-history"></i> Metrics Collection</h6>
            </div>
            <div class="card-body">
                <dl class="row mb-0">
                    <dt class="col-sm-3">Poll Interval:</dt>
                    <dd class="col-sm-3">${worker.poll_interval ? `${worker.poll_interval}s` : '<span class="text-muted">Not set</span>'}</dd>

                    <dt class="col-sm-3">Next Refresh:</dt>
                    <dd class="col-sm-3">
                        ${nextRefresh}
                    </dd>

                    <dt class="col-sm-3">CML Last Synced:</dt>
                    <dd class="col-sm-3">
                        ${cmlLastSynced}
                    </dd>

                    <dt class="col-sm-3">CloudWatch Last:</dt>
                    <dd class="col-sm-3">
                        ${cloudwatchLast}
                    </dd>
                </dl>
            </div>
        </div>`;

    monitoringContent.innerHTML = html;

    // Initialize tooltips for date info icons
    import('../utils/dates.js').then(({ initializeDateTooltips }) => {
        initializeDateTooltips();
    });
}

/**
 * Load monitoring tab from current worker store
 */
export async function loadMonitoringTab() {
    const worker = getActiveWorker();
    renderMonitoringTab(worker);
}

/**
 * Initialize SSE listener for monitoring updates
 */
export function initializeMonitoringSSE() {
    // Listen for worker metrics updates (includes activity/monitoring data)
    sseClient.on('worker.metrics.updated', data => {
        console.log('[worker-monitoring] Received metrics update:', data);
        const activeWorker = getActiveWorker();
        if (activeWorker && data.worker_id === activeWorker.id) {
            // Re-render monitoring tab with updated data
            loadMonitoringTab();
        }
    });

    // Listen for worker activity updates
    sseClient.on('worker.activity.updated', data => {
        console.log('[worker-monitoring] Received activity update:', data);
        const activeWorker = getActiveWorker();
        if (activeWorker && data.worker_id === activeWorker.id) {
            // Re-render monitoring tab with updated data
            loadMonitoringTab();
        }
    });

    // Listen for worker paused events
    sseClient.on('worker.paused', data => {
        console.log('[worker-monitoring] Worker paused:', data);
        const activeWorker = getActiveWorker();
        if (activeWorker && data.worker_id === activeWorker.id) {
            loadMonitoringTab();
        }
    });

    // Listen for worker resumed events
    sseClient.on('worker.resumed', data => {
        console.log('[worker-monitoring] Worker resumed:', data);
        const activeWorker = getActiveWorker();
        if (activeWorker && data.worker_id === activeWorker.id) {
            loadMonitoringTab();
        }
    });
}
