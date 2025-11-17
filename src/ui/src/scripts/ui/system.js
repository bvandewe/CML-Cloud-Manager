/**
 * System Monitoring UI Logic
 *
 * Handles the system monitoring interface for viewing:
 * - System health status
 * - APScheduler jobs
 * - Worker monitoring
 * - Metrics collectors
 */

import * as systemApi from '../api/system.js';
import { showToast } from './notifications.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';
import * as bootstrap from 'bootstrap';

/**
 * Initialize the system monitoring view
 */
export function initializeSystemView() {
    console.log('Initializing system monitoring view...');

    // Load initial data
    loadSystemHealth();
    loadSchedulerStatus();
    loadWorkerMonitoring();
    loadMetricsCollectors();

    // Set up tab event listeners to reload data when switching tabs
    const tabs = document.querySelectorAll('#systemTabs button[data-bs-toggle="tab"]');
    tabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', event => {
            const targetId = event.target.getAttribute('data-bs-target');
            if (targetId === '#health-panel') {
                loadSystemHealth();
            } else if (targetId === '#scheduler-panel') {
                loadSchedulerJobs();
            } else if (targetId === '#monitoring-panel') {
                loadWorkerMonitoring();
            } else if (targetId === '#collectors-panel') {
                loadMetricsCollectors();
            }
        });
    });

    // Set up auto-refresh (every 30 seconds)
    setInterval(() => {
        const activeTab = document.querySelector('#systemTabs button.active');
        if (activeTab && document.getElementById('system-view').style.display !== 'none') {
            const targetId = activeTab.getAttribute('data-bs-target');
            if (targetId === '#health-panel') {
                loadSystemHealth();
            } else if (targetId === '#scheduler-panel') {
                loadSchedulerJobs();
            } else if (targetId === '#monitoring-panel') {
                loadWorkerMonitoring();
            } else if (targetId === '#collectors-panel') {
                loadMetricsCollectors();
            }
        }
    }, 30000);
}

/**
 * Load and display system health status
 */
async function loadSystemHealth() {
    try {
        const health = await systemApi.getSystemHealth();

        // Update overall status badge
        const statusElement = document.getElementById('system-overall-status');
        if (statusElement) {
            const statusBadge = getStatusBadge(health.status);
            statusElement.innerHTML = statusBadge;
        }

        // Render health components
        const componentsContainer = document.getElementById('health-components');
        if (componentsContainer) {
            componentsContainer.innerHTML = renderHealthComponents(health.components);
        }
    } catch (error) {
        console.error('Failed to load system health:', error);
        showToast('Failed to load system health', 'error');
    }
}

/**
 * Load scheduler status (for card display)
 */
async function loadSchedulerStatus() {
    try {
        const status = await systemApi.getSchedulerStatus();

        const container = document.getElementById('scheduler-status');
        if (container) {
            container.innerHTML = renderSchedulerStatus(status);
        }
    } catch (error) {
        console.error('Failed to load scheduler status:', error);
        const container = document.getElementById('scheduler-status');

        // Check if it's a permission error
        const isPermissionError = error.message && error.message.includes('Permission denied');

        if (container) {
            if (isPermissionError) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-shield-lock me-2"></i>
                        ${error.message}
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-circle me-2"></i>
                        Failed to load scheduler status
                    </div>
                `;
            }
        }

        // Only show toast for non-permission errors
        if (!isPermissionError) {
            showToast('Failed to load scheduler status', 'error');
        }
    }
}

/**
 * Load and display detailed scheduler jobs
 */
async function loadSchedulerJobs() {
    try {
        const jobs = await systemApi.getSchedulerJobs();

        const container = document.getElementById('scheduler-jobs');
        if (container) {
            // Ensure jobs is an array
            if (!Array.isArray(jobs)) {
                console.warn('Jobs response is not an array:', jobs);
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Unable to load scheduler jobs
                    </div>
                `;
                return;
            }

            if (jobs.length === 0) {
                container.innerHTML = `
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle me-2"></i>
                        No scheduled jobs found
                    </div>
                `;
            } else {
                container.innerHTML = renderSchedulerJobs(jobs);
                // Initialize Bootstrap tooltips for date icons
                initializeDateTooltips();
            }
        }
    } catch (error) {
        console.error('Failed to load scheduler jobs:', error);
        const container = document.getElementById('scheduler-jobs');
        if (container) {
            if (error.message && error.message.includes('Permission denied')) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-shield-lock me-2"></i>
                        ${error.message}
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-circle me-2"></i>
                        Failed to load scheduler jobs
                    </div>
                `;
            }
        }
    }
}

/**
 * Load worker monitoring status
 */
async function loadWorkerMonitoring() {
    try {
        const status = await systemApi.getWorkerMonitoringStatus();

        const container = document.getElementById('monitoring-details');
        if (container) {
            container.innerHTML = renderMonitoringDetails(status);
        }
    } catch (error) {
        console.error('Failed to load worker monitoring:', error);
        const container = document.getElementById('monitoring-details');

        // Check if it's a permission error
        const isPermissionError = error.message && error.message.includes('Permission denied');

        if (container) {
            if (isPermissionError) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-shield-lock me-2"></i>
                        ${error.message}
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-circle me-2"></i>
                        Failed to load worker monitoring
                    </div>
                `;
            }
        }

        // Only show toast for non-permission errors
        if (!isPermissionError) {
            showToast('Failed to load worker monitoring', 'error');
        }
    }
}

/**
 * Load metrics collectors status
 */
async function loadMetricsCollectors() {
    try {
        const data = await systemApi.getMetricsCollectorsStatus();

        const container = document.getElementById('collectors-list');
        if (container) {
            container.innerHTML = renderCollectorsList(data);
        }
    } catch (error) {
        console.error('Failed to load metrics collectors:', error);
        const container = document.getElementById('collectors-list');

        // Check if it's a permission error
        const isPermissionError = error.message && error.message.includes('Permission denied');

        if (container) {
            if (isPermissionError) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-shield-lock me-2"></i>
                        ${error.message}
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-circle me-2"></i>
                        Failed to load metrics collectors
                    </div>
                `;
            }
        }

        // Only show toast for non-permission errors
        if (!isPermissionError) {
            showToast('Failed to load metrics collectors', 'error');
        }
    }
}

/**
 * Render health components HTML
 */
function renderHealthComponents(components) {
    if (!components || Object.keys(components).length === 0) {
        return '<div class="alert alert-warning">No health components found</div>';
    }

    let html = '<div class="row">';

    for (const [name, info] of Object.entries(components)) {
        const statusClass = info.status === 'healthy' ? 'success' : info.status === 'warning' ? 'warning' : 'danger';
        const icon = info.status === 'healthy' ? 'check-circle' : info.status === 'warning' ? 'exclamation-triangle' : 'x-circle';

        html += `
            <div class="col-md-6 mb-3">
                <div class="card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <h6 class="card-title">${formatComponentName(name)}</h6>
                                <span class="badge bg-${statusClass}">
                                    <i class="bi bi-${icon} me-1"></i>${info.status}
                                </span>
                            </div>
                            <i class="bi bi-${getComponentIcon(name)} text-${statusClass}" style="font-size: 1.5rem;"></i>
                        </div>
                        ${info.error ? `<div class="text-danger small mt-2">${info.error}</div>` : ''}
                        ${info.type ? `<div class="text-muted small mt-1">Type: ${info.type}</div>` : ''}
                        ${info.running != null ? `<div class="text-muted small">Running: ${info.running}</div>` : ''}
                        ${info.job_count != null ? `<div class="text-muted small">Jobs: ${info.job_count}</div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    html += '</div>';
    return html;
}

/**
 * Render scheduler jobs table
 */
function renderSchedulerJobs(jobs) {
    let html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Job ID</th>
                        <th>Name</th>
                        <th>Function</th>
                        <th>Trigger</th>
                        <th>Next Run</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
    `;

    jobs.forEach(job => {
        const nextRun = job.next_run_time ? formatDateTime(job.next_run_time) : 'N/A';
        const statusBadge = job.pending ? '<span class="badge bg-warning">Pending</span>' : '<span class="badge bg-success">Scheduled</span>';

        html += `
            <tr>
                <td><code>${job.id}</code></td>
                <td>${job.name || 'N/A'}</td>
                <td><small>${job.func || 'N/A'}</small></td>
                <td><small>${job.trigger || 'N/A'}</small></td>
                <td>${nextRun}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    return html;
}

/**
 * Render worker monitoring details
 */
function renderMonitoringDetails(monitoring) {
    const statusBadge = monitoring.scheduler_running ? '<span class="badge bg-success">Active</span>' : '<span class="badge bg-warning">Inactive</span>';

    let html = `
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h6 class="card-title">Monitoring Service Status</h6>
                        <p class="mb-1"><strong>Status:</strong> ${statusBadge}</p>
                        <p class="mb-1"><strong>Scheduler Running:</strong> ${monitoring.scheduler_running ? 'Yes' : 'No'}</p>
                        <p class="mb-0"><strong>Active Jobs:</strong> ${monitoring.monitoring_job_count || 0}</p>
                    </div>
                </div>
            </div>
        </div>
    `;

    if (monitoring.monitoring_job_count === 0) {
        html += `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                No workers are currently being monitored. Monitoring jobs are automatically created when you import or create CML Workers.
            </div>
            <div class="text-muted small mt-3">
                <strong>Note:</strong> There is one monitoring job per CML Worker. Each job polls AWS EC2 and CloudWatch APIs every 5 minutes to track worker status and metrics.
            </div>
        `;
    } else if (monitoring.jobs && monitoring.jobs.length > 0) {
        html += `
            <h6 class="mb-3">Active Monitoring Jobs (${monitoring.jobs.length})</h6>
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Job ID</th>
                            <th>Name</th>
                            <th>Next Run</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        monitoring.jobs.forEach(job => {
            const nextRun = job.next_run_time ? formatDateTime(job.next_run_time) : 'N/A';
            html += `
                <tr>
                    <td><code class="small">${job.id}</code></td>
                    <td>${job.name || 'Unnamed Job'}</td>
                    <td>${nextRun}</td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
            <div class="text-muted small mt-3">
                <strong>Note:</strong> Each job monitors one CML Worker's EC2 instance and collects CloudWatch metrics.
            </div>
        `;
    }

    return html;
}

/**
 * Render collectors list
 */
function renderCollectorsList(data) {
    const collectors = data.collectors || [];

    if (collectors.length === 0) {
        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                ${data.message || 'No collectors configured. Collectors are created automatically when workers are imported or created.'}
            </div>
            <div class="text-muted small mt-3">
                <strong>Note:</strong> There is one metrics collector per CML Worker. Each collector monitors the worker's EC2 instance status and CloudWatch metrics.
            </div>
        `;
    }

    let html = `
        <div class="alert alert-info mb-3">
            <i class="bi bi-info-circle me-2"></i>
            <strong>Active Collectors:</strong> ${data.active_collectors} of ${data.total_collectors}
            (Polling every ${data.poll_interval}s)
        </div>
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Worker ID</th>
                        <th>Job ID</th>
                        <th>Status</th>
                        <th>Poll Interval</th>
                    </tr>
                </thead>
                <tbody>
    `;

    collectors.forEach(collector => {
        const statusBadge = collector.status === 'active' ? '<span class="badge bg-success">Active</span>' : '<span class="badge bg-danger">Inactive</span>';

        html += `
            <tr>
                <td><code>${collector.worker_id}</code></td>
                <td><code class="small">${collector.job_id}</code></td>
                <td>${statusBadge}</td>
                <td>${collector.interval}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
        <div class="text-muted small mt-3">
            <strong>Note:</strong> Each CML Worker has a dedicated metrics collector that polls AWS EC2 and CloudWatch APIs to monitor instance status and resource utilization.
        </div>
    `;

    return html;
}

/**
 * Helper: Get status badge HTML
 */
function getStatusBadge(status) {
    const statusMap = {
        healthy: { class: 'success', icon: 'check-circle' },
        degraded: { class: 'warning', icon: 'exclamation-triangle' },
        unhealthy: { class: 'danger', icon: 'x-circle' },
    };

    const config = statusMap[status] || { class: 'secondary', icon: 'question-circle' };
    return `<span class="badge bg-${config.class}"><i class="bi bi-${config.icon} me-1"></i>${status}</span>`;
}

/**
 * Helper: Format component name for display
 */
function formatComponentName(name) {
    return name
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Helper: Get icon for component type
 */
function getComponentIcon(name) {
    const iconMap = {
        database: 'database',
        background_scheduler: 'calendar3',
        worker_monitoring: 'speedometer2',
        redis: 'server',
    };
    return iconMap[name] || 'gear';
}

/**
 * Helper: Format ISO datetime string for display
 */
function formatDateTime(isoString) {
    // Use the utility function that includes relative time
    return formatDateWithRelative(isoString);
}

/**
 * Refresh scheduler data (called from UI)
 */
function refreshScheduler() {
    loadSchedulerJobs();
    showToast('Refreshing scheduler jobs...', 'info');
}

/**
 * Refresh collectors data (called from UI)
 */
function refreshCollectors() {
    loadMetricsCollectors();
    showToast('Refreshing collectors status...', 'info');
}

// Export functions for global access
window.systemApp = {
    refreshScheduler,
    refreshCollectors,
};
