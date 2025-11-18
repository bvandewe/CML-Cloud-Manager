/**
 * Workers UI Component
 * Handles rendering and interaction for CML Workers management
 */

import * as workersApi from '../api/workers.js';
import * as systemApi from '../api/system.js';
import { showToast } from './notifications.js';
import { isAdmin, isAdminOrManager } from '../utils/roles.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';
import sseClient from '../services/sse-client.js';
import * as bootstrap from 'bootstrap';

// Store current user and workers data
let currentUser = null;
let workersData = [];
let currentRegion = 'us-east-1';
let currentWorkerDetails = null; // Store current worker for refresh

// Metrics refresh timer tracking
const WORKER_METRICS_STORAGE_KEY = 'cml-worker-metrics'; // localStorage key for per-worker tracking
let metricsCountdownInterval = null; // Interval ID for countdown updates

/**
 * Initialize the workers view
 * @param {Object} user - Current authenticated user
 */
export function initializeWorkersView(user) {
    console.log('[initializeWorkersView] ========================================');
    console.log('[initializeWorkersView] Called with user:', user);

    currentUser = user;
    const workersSection = document.getElementById('workers-section');
    const adminView = document.getElementById('workers-admin-view');
    const userView = document.getElementById('workers-user-view');

    if (!workersSection) {
        console.error('[initializeWorkersView] workers-section not found!');
        return;
    }
    console.log('[initializeWorkersView] workers-section found');

    workersSection.style.display = 'block';

    // Insert SSE connection status badge if missing
    let statusContainer = document.getElementById('sse-connection-status');
    if (!statusContainer) {
        statusContainer = document.createElement('div');
        statusContainer.id = 'sse-connection-status';
        statusContainer.className = 'mb-2';
        statusContainer.innerHTML = '<span class="badge bg-secondary">Realtime: initializing...</span>';
        workersSection.prepend(statusContainer);
    }

    // Initialize SSE client for real-time updates
    console.log('[initializeWorkersView] Setting up SSE client');
    setupSSEHandlers();
    setupSSEStatusIndicator();
    sseClient.connect();

    // Show appropriate view based on role
    if (hasAdminAccess(user)) {
        console.log('[initializeWorkersView] User has admin access');
        adminView.style.display = 'block';
        userView.style.display = 'none';
        initializeAdminView();
    } else {
        console.log('[initializeWorkersView] User has regular access');
        adminView.style.display = 'none';
        userView.style.display = 'block';
        initializeUserView();
    }

    console.log('[initializeWorkersView] Calling setupEventListeners()');
    setupEventListeners();
    console.log('[initializeWorkersView] Calling loadWorkers()');
    loadWorkers();
    console.log('[initializeWorkersView] Initialization complete');
}

/**
 * Check if user has admin/manager access
 * @param {Object} user
 * @returns {boolean}
 */
function hasAdminAccess(user) {
    console.log('[hasAdminAccess] Checking user:', user);
    console.log('[hasAdminAccess] realm_access:', user.realm_access);
    console.log('[hasAdminAccess] roles:', user.roles);
    const roles = user.realm_access?.roles || user.roles || [];
    console.log('[hasAdminAccess] Final roles array:', roles);
    const hasAccess = roles.includes('admin') || roles.includes('manager');
    console.log('[hasAdminAccess] Result:', hasAccess);
    return hasAccess;
}

/**
 * Get worker metrics info from localStorage
 * @param {string} workerId - Worker ID
 * @returns {Object|null} Worker metrics info or null
 */
function getWorkerMetricsInfo(workerId) {
    try {
        const stored = localStorage.getItem(WORKER_METRICS_STORAGE_KEY);
        if (!stored) return null;

        const allWorkers = JSON.parse(stored);
        return allWorkers[workerId] || null;
    } catch (e) {
        console.error('Failed to get worker metrics info from localStorage:', e);
        return null;
    }
}

/**
 * Save worker metrics info to localStorage
 * @param {string} workerId - Worker ID
 * @param {Object} info - Metrics info {poll_interval, next_refresh_at}
 */
function saveWorkerMetricsInfo(workerId, info) {
    try {
        const stored = localStorage.getItem(WORKER_METRICS_STORAGE_KEY);
        const allWorkers = stored ? JSON.parse(stored) : {};

        allWorkers[workerId] = {
            poll_interval: info.poll_interval,
            next_refresh_at: info.next_refresh_at,
            last_refreshed_at: info.last_refreshed_at || new Date().toISOString(),
            updated_at: new Date().toISOString(),
        };

        localStorage.setItem(WORKER_METRICS_STORAGE_KEY, JSON.stringify(allWorkers));
    } catch (e) {
        console.error('Failed to save worker metrics info to localStorage:', e);
    }
}

/**
 * Update the "last refreshed" display in the modal header
 */
function updateLastRefreshedDisplay() {
    const lastRefreshedElement = document.querySelector('#metrics-last-refreshed .last-refreshed-time');
    if (!lastRefreshedElement || !currentWorkerDetails) {
        return;
    }

    const metricsInfo = getWorkerMetricsInfo(currentWorkerDetails.id);
    if (!metricsInfo || !metricsInfo.last_refreshed_at) {
        lastRefreshedElement.textContent = '--';
        return;
    }

    // Use the date utility to format with relative time
    const formattedTime = formatDateWithRelative(metricsInfo.last_refreshed_at);
    lastRefreshedElement.innerHTML = formattedTime;

    // Reinitialize tooltips for the updated element
    initializeDateTooltips();
}

/**
 * Start the metrics refresh countdown timer
 */
function startMetricsCountdown() {
    // Clear any existing countdown
    stopMetricsCountdown();

    if (!currentWorkerDetails) return;

    // Update the last refreshed display
    updateLastRefreshedDisplay();

    // Try to get metrics info from localStorage
    const metricsInfo = getWorkerMetricsInfo(currentWorkerDetails.id);

    if (metricsInfo && metricsInfo.next_refresh_at) {
        // Use stored next refresh time
        const nextRefreshTime = new Date(metricsInfo.next_refresh_at).getTime();
        const now = Date.now();

        // Only use stored time if it's in the future
        if (nextRefreshTime > now) {
            // Update the countdown display immediately
            updateMetricsCountdownDisplay();

            // Update every second
            metricsCountdownInterval = setInterval(() => {
                updateMetricsCountdownDisplay();
            }, 1000);
            return;
        }
    }

    // Fallback: Show placeholder if no timing info available
    const countdownElement = document.getElementById('metrics-countdown');
    if (countdownElement) {
        countdownElement.textContent = '--:--';
    }
}

/**
 * Stop the metrics refresh countdown timer
 */
function stopMetricsCountdown() {
    if (metricsCountdownInterval) {
        clearInterval(metricsCountdownInterval);
        metricsCountdownInterval = null;
    }
}

/**
 * Reset the metrics refresh countdown timer (called when metrics are updated)
 * @param {Object} data - SSE event data with next_refresh_at and poll_interval
 */
function resetMetricsCountdown(data) {
    // Save the new timing info to localStorage
    if (currentWorkerDetails && data) {
        const info = {
            poll_interval: data.poll_interval || 300,
            next_refresh_at: data.next_refresh_at || new Date(Date.now() + (data.poll_interval || 300) * 1000).toISOString(),
            last_refreshed_at: new Date().toISOString(),
        };
        saveWorkerMetricsInfo(currentWorkerDetails.id, info);
    }

    // Update the last refreshed display
    updateLastRefreshedDisplay();

    // Restart the countdown with new info (stop existing interval first)
    stopMetricsCountdown();
    startMetricsCountdown();
}

/**
 * Update the countdown display
 */
function updateMetricsCountdownDisplay() {
    const countdownElement = document.getElementById('metrics-countdown');
    if (!countdownElement || !currentWorkerDetails) {
        return;
    }

    const metricsInfo = getWorkerMetricsInfo(currentWorkerDetails.id);
    if (!metricsInfo || !metricsInfo.next_refresh_at) {
        countdownElement.textContent = '--:--';
        return;
    }

    const now = Date.now();
    const nextRefreshTime = new Date(metricsInfo.next_refresh_at).getTime();
    const remainingMs = nextRefreshTime - now;

    if (remainingMs <= 0) {
        // Countdown expired - job should be running or about to run
        countdownElement.textContent = 'Refreshing...';
        countdownElement.classList.add('text-muted');
        return;
    }

    countdownElement.classList.remove('text-muted');
    const remainingSeconds = Math.floor(remainingMs / 1000);
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;

    countdownElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/**
 * Initialize admin/manager view
 */
function initializeAdminView() {
    console.log('Initializing admin view for workers');

    // Use setTimeout to ensure DOM is ready
    setTimeout(() => {
        // Show/hide admin-only buttons based on role
        const adminElements = document.querySelectorAll('.admin-only-element');
        console.log('[initializeAdminView] Found admin-only-element buttons:', adminElements.length);

        if (isAdmin()) {
            console.log('[initializeAdminView] User is admin - showing buttons');
            adminElements.forEach(el => {
                console.log('[initializeAdminView] Showing element:', el);
                el.style.display = '';
            });
        } else {
            console.log('[initializeAdminView] User is not admin - hiding buttons');
            adminElements.forEach(el => {
                el.style.display = 'none';
            });
        }
    }, 100);
}

/**
 * Initialize user view
 */
function initializeUserView() {
    console.log('Initializing user view for workers');
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    console.log('[setupEventListeners] ========================================');
    console.log('[setupEventListeners] Called');

    // Filter and search handlers
    const filterRegion = document.getElementById('filter-region');
    const filterStatus = document.getElementById('filter-status');
    const searchWorkers = document.getElementById('search-workers');

    if (filterRegion) {
        filterRegion.addEventListener('change', e => {
            currentRegion = e.target.value || 'us-east-1';
            loadWorkers();
        });
    }

    if (filterStatus) {
        filterStatus.addEventListener('change', () => applyFilters());
    }

    if (searchWorkers) {
        searchWorkers.addEventListener('input', () => applyFilters());
    }

    // User view filters
    const filterStatusUser = document.getElementById('filter-status-user');
    const searchWorkersUser = document.getElementById('search-workers-user');
    const sortWorkersUser = document.getElementById('sort-workers-user');

    if (filterStatusUser) {
        filterStatusUser.addEventListener('change', () => applyUserFilters());
    }

    if (searchWorkersUser) {
        searchWorkersUser.addEventListener('input', () => applyUserFilters());
    }

    if (sortWorkersUser) {
        sortWorkersUser.addEventListener('change', () => applyUserFilters());
    }

    // Modal handlers
    console.log('[setupEventListeners] Setting up modal handlers');
    setupCreateWorkerModal();
    setupImportWorkerModal();
    setupDeleteWorkerModal();
    setupLicenseModal();
    setupTabHandlers();

    console.log('[setupEventListeners] Calling setupRefreshButton()');
    setupRefreshButton();
    console.log('[setupEventListeners] Calling setupDeleteButtonInDetails()');
    setupDeleteButtonInDetails();

    // Setup modal close handler to stop countdown timer
    const workerDetailsModal = document.getElementById('workerDetailsModal');
    if (workerDetailsModal) {
        workerDetailsModal.addEventListener('hidden.bs.modal', () => {
            stopMetricsCountdown();
        });
    }

    console.log('[setupEventListeners] All event listeners set up');
}

/**
 * Setup SSE event handlers for real-time updates
 */
function setupSSEHandlers() {
    console.log('[setupSSEHandlers] Registering SSE event handlers');

    // Handle worker metrics updated
    sseClient.on('worker.metrics.updated', data => {
        const timestamp = new Date().toISOString();
        console.log(`[SSE] [${timestamp}] Worker metrics updated:`, {
            worker_id: data.worker_id,
            cpu_utilization: data.cpu_utilization,
            memory_utilization: data.memory_utilization,
            poll_interval: data.poll_interval,
            next_refresh_at: data.next_refresh_at,
            has_timing_info: !!(data.poll_interval && data.next_refresh_at),
            modal_open: !!(currentWorkerDetails && currentWorkerDetails.id === data.worker_id),
        });

        // Save metrics timing info to localStorage if provided
        if (data.worker_id && (data.next_refresh_at || data.poll_interval)) {
            const info = {
                poll_interval: data.poll_interval || 300,
                next_refresh_at: data.next_refresh_at || new Date(Date.now() + (data.poll_interval || 300) * 1000).toISOString(),
                last_refreshed_at: new Date().toISOString(),
            };
            console.log('[SSE] Saving timing info for worker', data.worker_id, ':', info);
            saveWorkerMetricsInfo(data.worker_id, info);
        }

        // Update the worker in the local cache with new metrics
        const workerIndex = workersData.findIndex(w => w.id === data.worker_id);
        if (workerIndex !== -1) {
            // Update metrics in local cache
            workersData[workerIndex].cpu_utilization = data.cpu_utilization;
            workersData[workerIndex].memory_utilization = data.memory_utilization;
            console.log('[SSE] Updated local worker cache with metrics:', {
                worker_id: data.worker_id,
                cpu: data.cpu_utilization,
                memory: data.memory_utilization,
            });

            // Refresh the table display with updated data
            renderWorkersTable(workersData);
        }

        // If worker details modal is open for this worker, update displays
        if (currentWorkerDetails && currentWorkerDetails.id === data.worker_id) {
            console.log('[SSE] Updating modal displays for open worker');
            // Reset the countdown timer when metrics are updated
            resetMetricsCountdown(data);
            // Reload CloudWatch metrics section in the CML tab
            loadCloudWatchMetrics(data.worker_id, currentWorkerDetails.region);
        }
    });

    // Handle worker labs updated
    sseClient.on('worker.labs.updated', data => {
        console.log('[SSE] Worker labs updated:', data);

        // If worker details modal is open and Labs tab is active, reload it
        if (currentWorkerDetails && currentWorkerDetails.id === data.worker_id) {
            const labsTab = document.querySelector('#labs-tab');
            if (labsTab && labsTab.classList.contains('active')) {
                console.log('[SSE] Reloading Labs tab');
                loadLabsTab();
            }
        }
    });

    // Handle worker status updated
    sseClient.on('worker.status.updated', data => {
        console.log('[SSE] Worker status updated:', data);
        loadWorkers();

        if (currentWorkerDetails && currentWorkerDetails.id === data.worker_id) {
            loadWorkerDetails(data.worker_id, currentWorkerDetails.region);
        }
    });

    // Handle worker created
    sseClient.on('worker.created', data => {
        console.log('[SSE] Worker created:', data);
        loadWorkers();
    });

    // Handle worker terminated
    sseClient.on('worker.terminated', data => {
        console.log('[SSE] Worker terminated:', data);
        loadWorkers();

        // Clean up localStorage for deleted worker
        if (data.worker_id) {
            try {
                const stored = localStorage.getItem(WORKER_METRICS_STORAGE_KEY);
                if (stored) {
                    const allWorkers = JSON.parse(stored);
                    if (allWorkers[data.worker_id]) {
                        delete allWorkers[data.worker_id];
                        localStorage.setItem(WORKER_METRICS_STORAGE_KEY, JSON.stringify(allWorkers));
                        console.log('[SSE] Cleaned up metrics storage for terminated worker:', data.worker_id);
                    }
                }
            } catch (e) {
                console.error('Failed to clean up worker metrics storage:', e);
            }
        }

        // Close modal if this worker is open
        if (currentWorkerDetails && currentWorkerDetails.id === data.worker_id) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('workerDetailsModal'));
            if (modal) {
                modal.hide();
            }
        }
    });

    console.log('[setupSSEHandlers] SSE event handlers registered');
}

/**
 * Setup SSE connection status indicator badge updates
 */
function setupSSEStatusIndicator() {
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

/**
 * Clean up metrics storage for workers that no longer exist
 */
function cleanupStaleWorkerMetrics() {
    try {
        const stored = localStorage.getItem(WORKER_METRICS_STORAGE_KEY);
        if (!stored) return;

        const allMetrics = JSON.parse(stored);
        const storedWorkerIds = Object.keys(allMetrics);
        const currentWorkerIds = workersData.map(w => w.id);

        let cleaned = false;
        storedWorkerIds.forEach(workerId => {
            if (!currentWorkerIds.includes(workerId)) {
                delete allMetrics[workerId];
                cleaned = true;
                console.log('[cleanupStaleWorkerMetrics] Removed stale metrics for worker:', workerId);
            }
        });

        if (cleaned) {
            localStorage.setItem(WORKER_METRICS_STORAGE_KEY, JSON.stringify(allMetrics));
            console.log('[cleanupStaleWorkerMetrics] Cleanup complete. Remaining workers:', Object.keys(allMetrics).length);
        }
    } catch (e) {
        console.error('Failed to cleanup stale worker metrics:', e);
    }
}

/**
 * Load workers from API
 */
async function loadWorkers() {
    try {
        const filterStatus = document.getElementById('filter-status');
        const status = filterStatus?.value || null;

        const response = await workersApi.listWorkers(currentRegion, status);
        console.log('API response:', response, 'Type:', typeof response, 'IsArray:', Array.isArray(response));

        // Handle different response formats
        if (Array.isArray(response)) {
            workersData = response;
        } else if (response?.data && Array.isArray(response.data)) {
            workersData = response.data;
        } else if (response?.result && Array.isArray(response.result)) {
            workersData = response.result;
        } else {
            console.warn('Unexpected response format:', response);
            workersData = [];
        }

        console.log('Workers data:', workersData, 'Length:', workersData.length);

        if (hasAdminAccess(currentUser)) {
            updateStatistics();
            renderWorkersTable();
        } else {
            renderWorkersCards();
        }

        // Clean up stale metrics storage after loading workers
        cleanupStaleWorkerMetrics();
    } catch (error) {
        console.error('Failed to load workers:', error);
        workersData = [];
        showToast('Failed to load workers', 'error');
    }
}

/**
 * Update statistics cards
 */
function updateStatistics() {
    const total = workersData.length;
    const running = workersData.filter(w => w.status === 'running').length;
    const stopped = workersData.filter(w => w.status === 'stopped').length;

    document.getElementById('total-workers-count').textContent = total;
    document.getElementById('running-workers-count').textContent = running;
    document.getElementById('stopped-workers-count').textContent = stopped;

    // Calculate average CPU
    const withCpu = workersData.filter(w => w.cpu_utilization !== null);
    const avgCpu = withCpu.length ? (withCpu.reduce((sum, w) => sum + w.cpu_utilization, 0) / withCpu.length).toFixed(1) : 0;
    document.getElementById('avg-cpu-usage').textContent = `${avgCpu}%`;
}

/**
 * Render workers table (admin/manager view)
 */
function renderWorkersTable() {
    const tbody = document.getElementById('workers-table-body');
    if (!tbody) return;

    if (workersData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center text-muted py-4">
                    <i class="bi bi-inbox fs-1 d-block mb-2"></i>
                    No workers found
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = workersData
        .map(
            worker => `
        <tr class="cursor-pointer" onclick="window.workersApp.showWorkerDetails('${worker.id}', '${worker.aws_region}')">
            <td>
                <span class="badge ${getStatusBadgeClass(worker.status)}">
                    ${worker.status}
                </span>
            </td>
            <td>
                <strong>${escapeHtml(worker.name)}</strong>
                ${worker.https_endpoint ? `<br><small class="text-muted">${worker.https_endpoint}</small>` : ''}
            </td>
            <td>
                <code class="small">${worker.aws_instance_id || 'N/A'}</code>
                ${worker.public_ip ? `<br><small class="text-muted">${worker.public_ip}</small>` : ''}
            </td>
            <td>${worker.instance_type}</td>
            <td><span class="badge bg-secondary">${worker.aws_region}</span></td>
            <td>
                <span class="badge ${getServiceStatusBadgeClass(worker.service_status)}">
                    ${worker.service_status}
                </span>
            </td>
            <td>
                ${
                    worker.cpu_utilization != null
                        ? `<div class="progress" style="height: 20px;">
                        <div class="progress-bar ${getCpuProgressClass(worker.cpu_utilization)}"
                             style="width: ${worker.cpu_utilization}%">
                            ${worker.cpu_utilization.toFixed(1)}%
                        </div>
                    </div>`
                        : '<span class="text-muted">-</span>'
                }
            </td>
            <td>
                ${
                    worker.memory_utilization != null
                        ? `<div class="progress" style="height: 20px;">
                        <div class="progress-bar ${getMemoryProgressClass(worker.memory_utilization)}"
                             style="width: ${worker.memory_utilization}%">
                            ${worker.memory_utilization.toFixed(1)}%
                        </div>
                    </div>`
                        : '<span class="text-muted">-</span>'
                }
            </td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-outline-primary" onclick="event.stopPropagation(); window.workersApp.showWorkerDetails('${worker.id}', '${worker.aws_region}')"
                            title="View Details">
                        <i class="bi bi-info-circle"></i>
                    </button>
                    ${
                        worker.status === 'stopped'
                            ? `<button class="btn btn-outline-success" onclick="event.stopPropagation(); window.workersApp.showStartConfirmation('${worker.id}', '${worker.aws_region}', '${escapeHtml(worker.name)}')"
                                title="Start">
                            <i class="bi bi-play-fill"></i>
                        </button>`
                            : ''
                    }
                    ${
                        worker.status === 'running'
                            ? `<button class="btn btn-outline-warning" onclick="event.stopPropagation(); window.workersApp.showStopConfirmation('${worker.id}', '${worker.aws_region}', '${escapeHtml(worker.name)}')"
                                title="Stop">
                            <i class="bi bi-stop-fill"></i>
                        </button>`
                            : ''
                    }
                    ${
                        worker.status === 'running'
                            ? `<button class="btn btn-outline-secondary refresh-btn" data-worker-id="${worker.id}" data-region="${worker.aws_region}"
                                title="Refresh Metrics" onclick="event.stopPropagation()">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>`
                            : ''
                    }
                    <button class="btn btn-outline-danger admin-only" onclick="event.stopPropagation(); window.workersApp.showDeleteModal('${worker.id}', '${worker.aws_region}', '${escapeHtml(worker.name)}')"
                            title="Delete Worker" style="display: none;">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `
        )
        .join('');

    // Initialize Bootstrap tooltips for date icons
    initializeDateTooltips();

    // Show admin-only buttons for admins
    if (isAdmin()) {
        document.querySelectorAll('.admin-only').forEach(el => {
            el.style.display = '';
        });
    }
}

/**
 * Render workers cards (user view)
 */
function renderWorkersCards() {
    const container = document.getElementById('workers-cards-container');
    if (!container) return;

    if (workersData.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center text-muted py-5">
                <i class="bi bi-inbox fs-1 d-block mb-3"></i>
                <h5>No workers available</h5>
                <p>There are currently no CML workers available to you.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = workersData
        .map(
            worker => `
        <div class="col-md-6 col-lg-4">
            <div class="card worker-card h-100 ${worker.status === 'running' ? 'border-success' : 'border-secondary'} cursor-pointer"
                 onclick="window.workersApp.showWorkerDetails('${worker.id}', '${worker.aws_region}')">
                <div class="card-header ${worker.status === 'running' ? 'bg-success text-white' : 'bg-secondary text-white'}">
                    <div class="d-flex justify-content-between align-items-center">
                        <h5 class="card-title mb-0">
                            <i class="bi bi-server"></i> ${escapeHtml(worker.name)}
                        </h5>
                        <span class="badge ${worker.status === 'running' ? 'bg-light text-success' : 'bg-light text-secondary'}">
                            ${worker.status}
                        </span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-2">
                            <span class="text-muted">
                                <i class="bi bi-geo-alt"></i> Region
                            </span>
                            <strong>${worker.aws_region}</strong>
                        </div>
                        <div class="d-flex justify-content-between mb-2">
                            <span class="text-muted">
                                <i class="bi bi-hdd"></i> Instance Type
                            </span>
                            <strong>${worker.instance_type}</strong>
                        </div>
                        ${
                            worker.cml_version
                                ? `<div class="d-flex justify-content-between mb-2">
                                <span class="text-muted">
                                    <i class="bi bi-box"></i> CML Version
                                </span>
                                <strong>${worker.cml_version}</strong>
                            </div>`
                                : ''
                        }
                    </div>

                    ${
                        worker.cpu_utilization != null && worker.memory_utilization != null
                            ? `<div class="mb-3">
                            <small class="text-muted">CPU Usage</small>
                            <div class="progress mb-2" style="height: 20px;">
                                <div class="progress-bar ${getCpuProgressClass(worker.cpu_utilization)}"
                                     style="width: ${worker.cpu_utilization}%">
                                    ${worker.cpu_utilization.toFixed(1)}%
                                </div>
                            </div>
                            <small class="text-muted">Memory Usage</small>
                            <div class="progress" style="height: 20px;">
                                <div class="progress-bar ${getMemoryProgressClass(worker.memory_utilization)}"
                                     style="width: ${worker.memory_utilization}%">
                                    ${worker.memory_utilization.toFixed(1)}%
                                </div>
                            </div>
                        </div>`
                            : ''
                    }

                    ${
                        worker.https_endpoint && worker.status === 'running'
                            ? `<div class="d-grid" onclick="event.stopPropagation();">
                            <a href="${worker.https_endpoint}" target="_blank" class="btn btn-primary">
                                <i class="bi bi-box-arrow-up-right"></i> Access CML
                            </a>
                        </div>`
                            : `<div class="alert alert-warning mb-0 small">
                            <i class="bi bi-exclamation-triangle"></i> Worker is not available
                        </div>`
                    }
                </div>
                <div class="card-footer text-muted small">
                    <div class="d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-clock"></i> ${formatDate(worker.updated_at)}</span>
                        <span class="badge bg-primary">Click for details</span>
                    </div>
                </div>
            </div>
        </div>
    `
        )
        .join('');

    // Initialize Bootstrap tooltips for date icons
    initializeDateTooltips();
}

/**
 * Apply filters to workers table
 */
function applyFilters() {
    const searchTerm = document.getElementById('search-workers')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-status')?.value || '';

    let filtered = workersData;

    if (statusFilter) {
        filtered = filtered.filter(w => w.status === statusFilter);
    }

    if (searchTerm) {
        filtered = filtered.filter(w => w.name.toLowerCase().includes(searchTerm) || w.aws_instance_id?.toLowerCase().includes(searchTerm) || w.public_ip?.toLowerCase().includes(searchTerm) || w.private_ip?.toLowerCase().includes(searchTerm));
    }

    // Temporarily replace workersData for rendering
    const original = workersData;
    workersData = filtered;
    renderWorkersTable();
    workersData = original;
}

/**
 * Apply filters to user cards view
 */
function applyUserFilters() {
    const searchTerm = document.getElementById('search-workers-user')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-status-user')?.value || '';
    const sortBy = document.getElementById('sort-workers-user')?.value || 'name';

    let filtered = workersData;

    if (statusFilter) {
        filtered = filtered.filter(w => w.status === statusFilter);
    }

    if (searchTerm) {
        filtered = filtered.filter(w => w.name.toLowerCase().includes(searchTerm));
    }

    // Sort
    filtered.sort((a, b) => {
        if (sortBy === 'name') {
            return a.name.localeCompare(b.name);
        } else if (sortBy === 'status') {
            return a.status.localeCompare(b.status);
        } else if (sortBy === 'usage') {
            return (b.cpu_utilization || 0) - (a.cpu_utilization || 0);
        }
        return 0;
    });

    // Temporarily replace workersData for rendering
    const original = workersData;
    workersData = filtered;
    renderWorkersCards();
    workersData = original;
}

/**
 * Setup create worker modal
 */
function setupCreateWorkerModal() {
    const submitBtn = document.getElementById('submit-create-worker-btn');
    if (!submitBtn) return;

    submitBtn.addEventListener('click', async () => {
        const name = document.getElementById('worker-name')?.value;
        const region = document.getElementById('worker-region')?.value;
        const instanceType = document.getElementById('worker-instance-type')?.value;
        const ami = document.getElementById('worker-ami')?.value;
        const cmlVersion = document.getElementById('worker-cml-version')?.value;

        if (!name || !region || !instanceType) {
            showToast('Please fill in all required fields', 'error');
            return;
        }

        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';

            const data = {
                name,
                instance_type: instanceType,
            };

            if (ami) data.ami_id = ami;
            if (cmlVersion) data.cml_version = cmlVersion;

            await workersApi.createWorker(region, data);

            showToast('Worker creation initiated successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('createWorkerModal')).hide();
            document.getElementById('create-worker-form').reset();

            // Reload workers
            setTimeout(() => loadWorkers(), 2000);
        } catch (error) {
            console.error('Failed to create worker:', error);
            showToast(error.message || 'Failed to create worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-plus-circle"></i> Create Worker';
        }
    });
}

/**
 * Setup import worker modal
 */
function setupImportWorkerModal() {
    // Toggle import method
    const importByInstance = document.getElementById('import-by-instance');
    const importByAmi = document.getElementById('import-by-ami');
    const instanceIdGroup = document.getElementById('instance-id-group');
    const amiNameGroup = document.getElementById('ami-name-group');
    const workerNameGroup = document.getElementById('worker-name-group');
    const importAllCheckbox = document.getElementById('import-all-instances');
    const importModeHint = document.getElementById('import-mode-hint');
    const workerNameInput = document.getElementById('import-worker-name');

    if (importByInstance) {
        importByInstance.addEventListener('change', () => {
            instanceIdGroup.style.display = 'block';
            amiNameGroup.style.display = 'none';
            if (workerNameInput) workerNameInput.disabled = false;
        });
    }

    if (importByAmi) {
        importByAmi.addEventListener('change', () => {
            instanceIdGroup.style.display = 'none';
            amiNameGroup.style.display = 'block';
            // Update name field state based on bulk import checkbox
            if (importAllCheckbox && workerNameInput) {
                workerNameInput.disabled = importAllCheckbox.checked;
            }
        });
    }

    // Handle bulk import checkbox toggle
    if (importAllCheckbox && importModeHint && workerNameInput) {
        importAllCheckbox.addEventListener('change', () => {
            if (importAllCheckbox.checked) {
                importModeHint.textContent = 'All instances matching the AMI pattern will be imported. Already registered instances will be skipped.';
                workerNameInput.disabled = true;
                workerNameInput.value = '';
            } else {
                importModeHint.textContent = 'Will import the first matching instance only.';
                workerNameInput.disabled = false;
            }
        });
    }

    const submitBtn = document.getElementById('submit-import-worker-btn');
    if (!submitBtn) return;

    submitBtn.addEventListener('click', async () => {
        const region = document.getElementById('import-region')?.value;
        const instanceId = document.getElementById('import-instance-id')?.value;
        const amiName = document.getElementById('import-ami-name')?.value;
        const name = document.getElementById('import-worker-name')?.value;
        const isInstanceMethod = document.getElementById('import-by-instance')?.checked;
        const importAll = document.getElementById('import-all-instances')?.checked || false;

        if (!region) {
            showToast('Please select a region', 'error');
            return;
        }

        if (isInstanceMethod && !instanceId) {
            showToast('Please provide an instance ID', 'error');
            return;
        }

        if (!isInstanceMethod && !amiName) {
            showToast('Please provide an AMI name pattern', 'error');
            return;
        }

        try {
            submitBtn.disabled = true;
            const actionText = importAll && !isInstanceMethod ? 'Importing all...' : 'Importing...';
            submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${actionText}`;

            const data = {};
            if (isInstanceMethod) {
                data.aws_instance_id = instanceId;
            } else {
                data.ami_name = amiName;
                // Only add import_all flag for AMI-based imports
                data.import_all = importAll;
            }
            // Only include name if not bulk importing
            if (name && !importAll) data.name = name;

            const result = await workersApi.importWorker(region, data);
            (region, data);

            // Show appropriate success message
            if (importAll && result.total_imported !== undefined) {
                const msg = `Bulk import completed: ${result.total_imported} worker(s) imported, ${result.total_skipped} skipped`;
                showToast(msg, 'success');
            } else {
                showToast('Worker imported successfully', 'success');
            }
            bootstrap.Modal.getInstance(document.getElementById('importWorkerModal')).hide();
            document.getElementById('import-worker-form').reset();
            // Reset checkbox to default (checked)
            const checkbox = document.getElementById('import-all-instances');
            if (checkbox) checkbox.checked = true;

            // Reload workers
            setTimeout(() => loadWorkers(), 1000);
        } catch (error) {
            console.error('Failed to import worker:', error);
            showToast(error.message || 'Failed to import worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-box-arrow-in-down"></i> Import Worker';
        }
    });
}

/**
 * Setup license modal
 */
function setupLicenseModal() {
    const submitBtn = document.getElementById('submit-register-license-btn');
    if (!submitBtn) return;

    submitBtn.addEventListener('click', async () => {
        const workerId = document.getElementById('license-worker-id')?.value;
        const region = document.getElementById('license-worker-region')?.value;
        const token = document.getElementById('license-token')?.value;

        if (!token) {
            showToast('Please provide a license token', 'error');
            return;
        }

        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Registering...';

            await workersApi.registerLicense(region, workerId, token);

            showToast('License registered successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('registerLicenseModal')).hide();
            document.getElementById('register-license-form').reset();

            // Reload workers
            setTimeout(() => loadWorkers(), 1000);
        } catch (error) {
            console.error('Failed to register license:', error);
            showToast(error.message || 'Failed to register license', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-key"></i> Register License';
        }
    });
}

/**
 * Show worker details modal
 */
async function showWorkerDetails(workerId, region) {
    console.log('[showWorkerDetails] ========================================');
    console.log('[showWorkerDetails] Called with workerId:', workerId, 'region:', region);

    const modalElement = document.getElementById('workerDetailsModal');
    if (!modalElement) {
        console.error('[showWorkerDetails] Worker details modal element not found');
        showToast('Failed to open worker details: modal not found', 'error');
        return;
    }
    console.log('[showWorkerDetails] Modal element found:', modalElement);

    // Get existing modal instance or create new one
    let modal = bootstrap.Modal.getInstance(modalElement);
    if (modal) {
        // Dispose existing modal to clean up any leftover backdrops
        modal.dispose();
    }
    // Create fresh modal instance
    modal = new bootstrap.Modal(modalElement);

    const overviewContent = document.getElementById('worker-details-overview');

    if (!overviewContent) {
        console.error('[showWorkerDetails] Worker details overview content element not found');
        showToast('Failed to open worker details: content area not found', 'error');
        return;
    }
    console.log('[showWorkerDetails] Overview content element found');

    // Store current worker for refresh
    currentWorkerDetails = { id: workerId, region: region };
    console.log('[showWorkerDetails] Set currentWorkerDetails to:', currentWorkerDetails);

    // Re-setup refresh button to ensure it's attached
    console.log('[showWorkerDetails] Calling setupRefreshButton()');
    setupRefreshButton();
    console.log('[showWorkerDetails] setupRefreshButton() completed');

    // Setup delete button handler
    console.log('[showWorkerDetails] Calling setupDeleteButtonInDetails()');
    setupDeleteButtonInDetails();
    console.log('[showWorkerDetails] setupDeleteButtonInDetails() completed');

    // Show/hide admin-only tabs based on user role
    const adminTabs = document.querySelectorAll('.admin-only-tab');
    if (isAdmin()) {
        adminTabs.forEach(tab => (tab.style.display = 'block'));
    } else {
        adminTabs.forEach(tab => (tab.style.display = 'none'));
    }

    // Show/hide admin-only buttons (like delete button) based on user role
    const adminButtons = modalElement.querySelectorAll('.admin-only');
    if (isAdmin()) {
        adminButtons.forEach(btn => (btn.style.display = ''));
    } else {
        adminButtons.forEach(btn => (btn.style.display = 'none'));
    }

    modal.show();

    // Start metrics refresh countdown timer
    startMetricsCountdown();

    // Load overview data
    try {
        const worker = await workersApi.getWorkerDetails(region, workerId);

        // Debug: Log worker data to see what we're getting
        console.log('[showWorkerDetails] Worker data received:', {
            id: worker.id,
            poll_interval: worker.poll_interval,
            next_refresh_at: worker.next_refresh_at,
            cloudwatch_last_collected_at: worker.cloudwatch_last_collected_at,
        });

        // Initialize timing info from worker data if available
        if (worker.poll_interval && worker.next_refresh_at) {
            console.log('[showWorkerDetails] Initializing timing info from worker data');

            // Check if next_refresh_at is in the future
            const nextRefreshTime = new Date(worker.next_refresh_at).getTime();
            const now = Date.now();
            const isStale = nextRefreshTime <= now;

            console.log('[showWorkerDetails] Timing info validation:', {
                next_refresh_at: worker.next_refresh_at,
                nextRefreshTime,
                now,
                isStale,
                diff_seconds: Math.floor((nextRefreshTime - now) / 1000),
            });

            if (isStale) {
                console.log('[showWorkerDetails] next_refresh_at is stale - calculating fresh value');
                // Calculate fresh next_refresh_at based on current time + poll_interval
                const freshNextRefresh = new Date(now + worker.poll_interval * 1000).toISOString();
                saveWorkerMetricsInfo(workerId, {
                    poll_interval: worker.poll_interval,
                    next_refresh_at: freshNextRefresh,
                    last_refreshed_at: worker.cloudwatch_last_collected_at || new Date().toISOString(),
                });
                console.log('[showWorkerDetails] Saved fresh timing info:', { next_refresh_at: freshNextRefresh });
            } else {
                // Use original timing info if still valid
                saveWorkerMetricsInfo(workerId, {
                    poll_interval: worker.poll_interval,
                    next_refresh_at: worker.next_refresh_at,
                    last_refreshed_at: worker.cloudwatch_last_collected_at || new Date().toISOString(),
                });
            }

            // Update displays and start countdown
            updateLastRefreshedDisplay();
            startMetricsCountdown();
        } else {
            console.log('[showWorkerDetails] No timing info in worker data - triggering manual refresh');
            // Trigger a metrics refresh to populate timing data if worker is running
            if (worker.status === 'running') {
                console.log('[showWorkerDetails] Worker is running - refreshing metrics to get timing data');
                // Use setTimeout to avoid blocking the modal display
                setTimeout(async () => {
                    try {
                        await workersApi.refreshWorker(region, workerId);
                        console.log('[showWorkerDetails] Manual metrics refresh triggered successfully');
                    } catch (error) {
                        console.error('[showWorkerDetails] Failed to trigger metrics refresh:', error);
                    }
                }, 500);
            } else {
                console.log('[showWorkerDetails] Worker not running - cannot refresh metrics');
            }
        }

        overviewContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Basic Information</h5>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="40%">Name:</td><td><strong>${escapeHtml(worker.name)}</strong></td></tr>
                        <tr><td class="text-muted">Worker ID:</td><td><code class="small">${worker.id}</code></td></tr>
                        <tr><td class="text-muted">Instance ID:</td><td>${
                            worker.aws_instance_id
                                ? `<code class="small">${worker.aws_instance_id}</code> <a href="https://${worker.aws_region}.console.aws.amazon.com/ec2/home?region=${worker.aws_region}#InstanceDetails:instanceId=${worker.aws_instance_id}" target="_blank" class="text-decoration-none ms-1" title="View in AWS Console"><i class="bi bi-box-arrow-up-right text-primary"></i></a>`
                                : '<span class="text-muted">N/A</span>'
                        }</td></tr>
                        <tr><td class="text-muted">Region:</td><td><span class="badge bg-secondary">${worker.aws_region}</span></td></tr>
                        <tr><td class="text-muted">Instance Type:</td><td><span class="badge bg-info">${worker.instance_type}</span></td></tr>
                        <tr><td class="text-muted">Status:</td><td><span class="badge ${getStatusBadgeClass(worker.status)}">${worker.status}</span></td></tr>
                        <tr><td class="text-muted">Service Status:</td><td><span class="badge ${getServiceStatusBadgeClass(worker.service_status)}">${worker.service_status}</span></td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">AMI Information</h5>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="40%">AMI ID:</td><td>${
                            worker.ami_id
                                ? `<code class="small">${worker.ami_id}</code> <a href="https://${worker.aws_region}.console.aws.amazon.com/ec2/home?region=${worker.aws_region}#ImageDetails:imageId=${worker.ami_id}" target="_blank" class="text-decoration-none ms-1" title="View in AWS Console"><i class="bi bi-box-arrow-up-right text-primary"></i></a>`
                                : '<span class="text-muted">N/A</span>'
                        }</td></tr>
                        <tr><td class="text-muted">AMI Name:</td><td>${worker.ami_name || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">Description:</td><td>${worker.ami_description || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">Created:</td><td>${worker.ami_creation_date ? formatDate(worker.ami_creation_date) : '<span class="text-muted">N/A</span>'}</td></tr>
                    </table>
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Network</h5>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="40%">Public IP:</td><td>${worker.public_ip || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">Private IP:</td><td>${worker.private_ip || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">HTTPS Endpoint:</td><td>${
                            worker.https_endpoint ? `<a href="${worker.https_endpoint}" target="_blank" class="text-decoration-none">${worker.https_endpoint} <i class="bi bi-box-arrow-up-right"></i></a>` : '<span class="text-muted">N/A</span>'
                        }</td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Monitoring</h5>
                    <table class="table table-sm table-borderless">
                        <tr>
                            <td class="text-muted" width="40%">Detailed Monitoring:</td>
                            <td>
                                ${worker.cloudwatch_detailed_monitoring_enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>'}
                            </td>
                        </tr>
                    </table>
                    ${
                        !worker.cloudwatch_detailed_monitoring_enabled && isAdmin()
                            ? `
                    <button class="btn btn-sm btn-outline-primary" id="enable-monitoring-btn">
                        <i class="bi bi-speedometer2"></i> Enable Detailed Monitoring
                    </button>
                    <div class="text-muted small mt-2">
                        <i class="bi bi-info-circle"></i> Enables 1-minute metric granularity (~$2.10/month)
                    </div>
                    `
                            : ''
                    }
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-12">
                    <h5 class="border-bottom pb-2 mb-3">Resource Utilization</h5>
                    <div id="cloudwatch-metrics-section">
                        <div class="text-center py-3">
                            <div class="spinner-border spinner-border-sm" role="status"></div>
                            <span class="ms-2 text-muted">Loading CloudWatch metrics...</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Lifecycle</h5>
                    <table class="table table-sm table-borderless">
                        <tr>
                            <td class="text-muted" width="40%"><i class="bi bi-plus-circle"></i> Created:</td>
                            <td>${formatDate(worker.created_at)}</td>
                        </tr>
                        <tr>
                            <td class="text-muted"><i class="bi bi-arrow-repeat"></i> Updated:</td>
                            <td>${formatDate(worker.updated_at)}</td>
                        </tr>
                        <tr>
                            <td class="text-muted"><i class="bi bi-x-circle"></i> Terminated:</td>
                            <td>${worker.terminated_at ? formatDate(worker.terminated_at) : '<span class="text-muted">N/A</span>'}</td>
                        </tr>
                    </table>
                </div>
            </div>
        `;

        // Update currentWorkerDetails with worker name for delete modal
        currentWorkerDetails.name = worker.name;
        console.log('[showWorkerDetails] Updated currentWorkerDetails with name:', currentWorkerDetails);

        // Load CloudWatch metrics
        loadCloudWatchMetrics(workerId, region);

        // Setup enable monitoring button handler
        if (!worker.cloudwatch_detailed_monitoring_enabled && isAdmin()) {
            setupEnableMonitoringButton(workerId, region);
        }

        // Initialize Bootstrap tooltips for date icons
        initializeDateTooltips();

        // Store worker data for other tabs
        if (modalElement) {
            modalElement.dataset.workerId = workerId;
            modalElement.dataset.workerRegion = region;
        }
    } catch (error) {
        console.error('Failed to load worker details:', error);
        if (overviewContent) {
            overviewContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> Failed to load worker details: ${error.message}
                </div>
            `;
        }
        showToast(`Failed to load worker details: ${error.message}`, 'error');
    }
}

/**
 * Load CML metrics and display in overview
 * Uses CML's native telemetry API data (same as table view)
 */
async function loadCloudWatchMetrics(workerId, region) {
    const metricsSection = document.getElementById('cloudwatch-metrics-section');
    if (!metricsSection) return;

    try {
        // Get worker data to access CML telemetry metrics
        const worker = await workersApi.getWorkerById(region, workerId);

        const cpuValue = worker.cpu_utilization;
        const memValue = worker.memory_utilization;
        const diskValue = worker.storage_utilization;

        metricsSection.innerHTML = `
            <div class="row">
                <div class="col-md-4">
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-1">
                            <small class="text-muted"><i class="bi bi-cpu"></i> CPU Usage</small>
                            <small><strong>${cpuValue != null ? cpuValue.toFixed(1) + '%' : 'N/A'}</strong></small>
                        </div>
                        ${
                            cpuValue != null
                                ? `
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${getCpuProgressClass(cpuValue)}"
                                 style="width: ${cpuValue}%">
                            </div>
                        </div>`
                                : '<div class="alert alert-sm alert-warning py-1 mb-0"><i class="bi bi-exclamation-triangle"></i> No CPU data available</div>'
                        }
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-1">
                            <small class="text-muted"><i class="bi bi-memory"></i> Memory Usage</small>
                            <small><strong>${memValue != null ? memValue.toFixed(1) + '%' : 'N/A'}</strong></small>
                        </div>
                        ${
                            memValue != null
                                ? `
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${getMemoryProgressClass(memValue)}"
                                 style="width: ${memValue}%">
                            </div>
                        </div>`
                                : '<div class="alert alert-sm alert-info py-1 mb-0"><i class="bi bi-info-circle"></i> No memory data available</div>'
                        }
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-1">
                            <small class="text-muted"><i class="bi bi-hdd"></i> Storage Usage</small>
                            <small><strong>${diskValue != null ? diskValue.toFixed(1) + '%' : 'N/A'}</strong></small>
                        </div>
                        ${
                            diskValue != null
                                ? `
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${getDiskProgressClass(diskValue)}"
                                 style="width: ${diskValue}%">
                            </div>
                        </div>`
                                : '<div class="alert alert-sm alert-info py-1 mb-0"><i class="bi bi-info-circle"></i> No storage data available</div>'
                        }
                    </div>
                </div>
            </div>
            <div class="text-muted small">
                <i class="bi bi-info-circle"></i> Data from CML native telemetry (last refresh: ${formatRelativeTime(worker.updated_at)})
            </div>
        `;
    } catch (error) {
        console.error('Failed to load CloudWatch metrics:', error);
        metricsSection.innerHTML = `
            <div class="alert alert-warning mb-0">
                <i class="bi bi-exclamation-triangle"></i> Unable to load CloudWatch metrics: ${error.message}
            </div>
        `;
    }
}

/**
 * Setup enable monitoring button handler
 */
function setupEnableMonitoringButton(workerId, region) {
    const btn = document.getElementById('enable-monitoring-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Enabling...';

        try {
            await workersApi.enableDetailedMonitoring(region, workerId);
            showToast('Detailed monitoring enabled successfully', 'success');

            // Reload worker details to update UI
            await showWorkerDetails(workerId, region);
        } catch (error) {
            console.error('Failed to enable monitoring:', error);
            showToast(error.message || 'Failed to enable detailed monitoring', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-speedometer2"></i> Enable Detailed Monitoring';
        }
    });
}

/**
 * Load CML tab data - displays CML-specific application details
 */
async function loadCMLTab() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal.dataset.workerId;
    const region = modal.dataset.workerRegion;
    const cmlContent = document.getElementById('worker-details-cml');

    if (!workerId || !region) {
        cmlContent.innerHTML = '<div class="alert alert-warning">No worker selected</div>';
        return;
    }

    cmlContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading CML details...</p></div>';

    try {
        const worker = await workersApi.getWorkerDetails(region, workerId);

        // Parse system health data
        const health = worker.cml_system_health || {};
        const systemInfo = worker.cml_system_info || {};
        const licenseInfo = worker.cml_license_info || null;

        // Debug logging
        console.log('Worker CML Data:', {
            worker_id: worker.id,
            status: worker.status,
            service_status: worker.service_status,
            https_endpoint: worker.https_endpoint,
            has_health: !!worker.cml_system_health,
            has_system_info: !!worker.cml_system_info,
            has_license_info: !!worker.cml_license_info,
            health_is_licensed: health.is_licensed,
            health_is_enterprise: health.is_enterprise,
            license_info_keys: licenseInfo ? Object.keys(licenseInfo) : null,
            cml_last_synced_at: worker.cml_last_synced_at,
        });

        // systemInfo is the computes dictionary from system_stats
        // Extract stats from first compute node
        const firstCompute = Object.values(systemInfo)[0] || {};
        const computeStats = firstCompute.stats || {};
        const stats = {
            cpu: computeStats.cpu || {},
            memory: computeStats.memory || {},
            disk: computeStats.disk || {},
        };
        const domInfo = computeStats.dominfo || null;

        // Format uptime
        let uptimeDisplay = 'Unknown';
        if (worker.cml_uptime_seconds !== null && worker.cml_uptime_seconds !== undefined) {
            const hours = Math.floor(worker.cml_uptime_seconds / 3600);
            const minutes = Math.floor((worker.cml_uptime_seconds % 3600) / 60);
            uptimeDisplay = `${hours}h ${minutes}m`;
        }

        // Format ready state
        const readyBadge = worker.cml_ready ? 'success' : 'warning';
        const readyText = worker.cml_ready ? 'Ready' : 'Not Ready';
        const readyIcon = worker.cml_ready ? 'check-circle' : 'exclamation-triangle';

        // License and Edition info - prefer license_info over health data
        let isLicensed = false;
        let isEnterprise = false;

        if (licenseInfo && licenseInfo.product_license) {
            // Use detailed license info if available
            isEnterprise = licenseInfo.product_license.is_enterprise ?? false;
            // Check registration status for licensed state
            isLicensed = licenseInfo.registration?.status === 'COMPLETED' || licenseInfo.authorization?.status === 'IN_COMPLIANCE';
        } else if (health.is_licensed !== undefined) {
            // Fall back to health data
            isLicensed = health.is_licensed ?? false;
            isEnterprise = health.is_enterprise ?? false;
        }

        const licensedBadge = isLicensed ? 'success' : 'danger';
        const editionBadge = isEnterprise ? 'primary' : 'info';
        const editionText = isEnterprise ? 'Enterprise' : 'Community';

        // System health overall status
        const healthValid = health.valid ?? false;
        const healthBadge = healthValid ? 'success' : 'danger';
        const healthIcon = healthValid ? 'check-circle-fill' : 'x-circle-fill';

        // Controller health
        let controllerSection = '';
        if (health.controller) {
            const ctrl = health.controller;
            const ctrlValidBadge = ctrl.valid ? 'success' : 'danger';

            controllerSection = `
                <div class="col-md-6">
                    <div class="card h-100">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-hdd-rack me-2"></i>Controller Status</h6>
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td class="text-muted" style="width: 50%;">Status</td>
                                    <td><span class="badge bg-${ctrlValidBadge}">${ctrl.valid ? 'Valid' : 'Invalid'}</span></td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Core Connected</td>
                                    <td>${ctrl.core_connected ? '<i class="bi bi-check-circle text-success"></i> Yes' : '<i class="bi bi-x-circle text-danger"></i> No'}</td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Nodes Loaded</td>
                                    <td>${ctrl.nodes_loaded ? '<i class="bi bi-check-circle text-success"></i> Yes' : '<i class="bi bi-x-circle text-danger"></i> No'}</td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Images Loaded</td>
                                    <td>${ctrl.images_loaded ? '<i class="bi bi-check-circle text-success"></i> Yes' : '<i class="bi bi-x-circle text-danger"></i> No'}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        }

        // Compute/Node information
        let computeSection = '';
        if (health.computes && Object.keys(health.computes).length > 0) {
            const firstComputeId = Object.keys(health.computes)[0];
            const compute = health.computes[firstComputeId];
            const admissionBadge = compute.admission_state === 'READY' ? 'success' : 'warning';
            const isController = compute.is_controller ? '<span class="badge bg-primary">Controller</span>' : '';

            computeSection = `
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-server me-2"></i>Compute Node Health</h6>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <table class="table table-sm table-borderless mb-0">
                                        <tr>
                                            <td class="text-muted" style="width: 50%;">Hostname</td>
                                            <td><strong>${escapeHtml(compute.hostname || 'unknown')}</strong> ${isController}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Admission State</td>
                                            <td><span class="badge bg-${admissionBadge}">${escapeHtml(compute.admission_state || 'unknown')}</span></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Overall Valid</td>
                                            <td>${compute.valid ? '<i class="bi bi-check-circle text-success"></i> Yes' : '<i class="bi bi-x-circle text-danger"></i> No'}</td>
                                        </tr>
                                    </table>
                                </div>
                                <div class="col-md-6">
                                    <table class="table table-sm table-borderless mb-0">
                                        <tr>
                                            <td class="text-muted" style="width: 50%;">KVM/VMX</td>
                                            <td>${compute.kvm_vmx_enabled ? '<i class="bi bi-check-circle text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Libvirt</td>
                                            <td>${compute.libvirt ? '<i class="bi bi-check-circle text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">LLD Connected</td>
                                            <td>${compute.lld_connected ? '<i class="bi bi-check-circle text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'} ${compute.lld_synced ? '(Synced)' : ''}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Refplat Images</td>
                                            <td>${compute.refplat_images_available ? '<i class="bi bi-check-circle text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}</td>
                                        </tr>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // System statistics
        let statsSection = '';
        if (stats.cpu || stats.memory || stats.disk || domInfo) {
            // CPU percent is already 0-100 from CML API, don't multiply by 100
            const cpuPercent = stats.cpu?.percent ? parseFloat(stats.cpu.percent).toFixed(1) : 0;
            const cpuCount = stats.cpu?.count || 'N/A';

            const memTotal = stats.memory?.total ? formatBytes(stats.memory.total) : 'N/A';
            const memUsed = stats.memory?.used ? formatBytes(stats.memory.used) : 'N/A';
            const memFree = stats.memory?.free ? formatBytes(stats.memory.free) : 'N/A';
            const memPercent = stats.memory?.total && stats.memory?.used ? ((stats.memory.used / stats.memory.total) * 100).toFixed(1) : 0;

            const diskTotal = stats.disk?.total ? formatBytes(stats.disk.total) : 'N/A';
            const diskUsed = stats.disk?.used ? formatBytes(stats.disk.used) : 'N/A';
            const diskFree = stats.disk?.free ? formatBytes(stats.disk.free) : 'N/A';
            const diskPercent = stats.disk?.total && stats.disk?.used ? ((stats.disk.used / stats.disk.total) * 100).toFixed(1) : 0;

            // Determine progress bar colors based on utilization
            const cpuBarColor = cpuPercent > 80 ? 'danger' : cpuPercent > 60 ? 'warning' : 'success';
            const memBarColor = memPercent > 80 ? 'danger' : memPercent > 60 ? 'warning' : 'success';
            const diskBarColor = diskPercent > 80 ? 'danger' : diskPercent > 60 ? 'warning' : 'success';

            statsSection = `
                <div class="col-12 mt-3">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-speedometer2 me-2"></i>Resource Utilization</h6>
                        </div>
                        <div class="card-body">
                            <div class="row g-4">
                                <div class="col-md-4">
                                    <h6 class="text-muted mb-3"><i class="bi bi-cpu"></i> CPU</h6>
                                    <div class="mb-2">
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <small class="text-muted">Utilization</small>
                                            <strong>${cpuPercent}%</strong>
                                        </div>
                                        <div class="progress" style="height: 20px;">
                                            <div class="progress-bar bg-${cpuBarColor}" role="progressbar" style="width: ${cpuPercent}%;" aria-valuenow="${cpuPercent}" aria-valuemin="0" aria-valuemax="100"></div>
                                        </div>
                                    </div>
                                    <table class="table table-sm table-borderless mb-0">
                                        <tr>
                                            <td class="text-muted" style="width: 50%;">Total Cores</td>
                                            <td>${cpuCount}</td>
                                        </tr>
                                        ${
                                            domInfo
                                                ? `
                                        <tr>
                                            <td class="text-muted">Allocated vCPUs</td>
                                            <td><strong>${domInfo.allocated_cpus || 0}</strong></td>
                                        </tr>
                                        `
                                                : ''
                                        }
                                    </table>
                                </div>
                                <div class="col-md-4">
                                    <h6 class="text-muted mb-3"><i class="bi bi-memory"></i> Memory</h6>
                                    <div class="mb-2">
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <small class="text-muted">Utilization</small>
                                            <strong>${memPercent}%</strong>
                                        </div>
                                        <div class="progress" style="height: 20px;">
                                            <div class="progress-bar bg-${memBarColor}" role="progressbar" style="width: ${memPercent}%;" aria-valuenow="${memPercent}" aria-valuemin="0" aria-valuemax="100"></div>
                                        </div>
                                    </div>
                                    <table class="table table-sm table-borderless mb-0">
                                        <tr>
                                            <td class="text-muted" style="width: 50%;">Total</td>
                                            <td>${memTotal}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Used</td>
                                            <td><strong>${memUsed}</strong></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Free</td>
                                            <td>${memFree}</td>
                                        </tr>
                                        ${
                                            domInfo
                                                ? `
                                        <tr>
                                            <td class="text-muted">VM Allocated</td>
                                            <td><strong>${formatBytes((domInfo.allocated_memory || 0) * 1024)}</strong></td>
                                        </tr>
                                        `
                                                : ''
                                        }
                                    </table>
                                </div>
                                <div class="col-md-4">
                                    <h6 class="text-muted mb-3"><i class="bi bi-hdd"></i> Disk</h6>
                                    <div class="mb-2">
                                        <div class="d-flex justify-content-between align-items-center mb-1">
                                            <small class="text-muted">Utilization</small>
                                            <strong>${diskPercent}%</strong>
                                        </div>
                                        <div class="progress" style="height: 20px;">
                                            <div class="progress-bar bg-${diskBarColor}" role="progressbar" style="width: ${diskPercent}%;" aria-valuenow="${diskPercent}" aria-valuemin="0" aria-valuemax="100"></div>
                                        </div>
                                    </div>
                                    <table class="table table-sm table-borderless mb-0">
                                        <tr>
                                            <td class="text-muted" style="width: 50%;">Total</td>
                                            <td>${diskTotal}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Used</td>
                                            <td><strong>${diskUsed}</strong></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted">Free</td>
                                            <td>${diskFree}</td>
                                        </tr>
                                    </table>
                                </div>
                            </div>
                            ${
                                domInfo
                                    ? `
                            <div class="row mt-3">
                                <div class="col-12">
                                    <div class="border-top pt-3">
                                        <h6 class="text-muted mb-3"><i class="bi bi-diagram-3"></i> Virtual Nodes Summary</h6>
                                        <div class="row">
                                            <div class="col-md-3">
                                                <div class="text-center">
                                                    <div class="display-6 text-success">${domInfo.running_nodes || 0}</div>
                                                    <small class="text-muted">Running</small>
                                                </div>
                                            </div>
                                            <div class="col-md-3">
                                                <div class="text-center">
                                                    <div class="display-6 text-primary">${domInfo.total_nodes || 0}</div>
                                                    <small class="text-muted">Total</small>
                                                </div>
                                            </div>
                                            <div class="col-md-3">
                                                <div class="text-center">
                                                    <div class="display-6 text-info">${domInfo.allocated_cpus || 0}</div>
                                                    <small class="text-muted">vCPUs</small>
                                                </div>
                                            </div>
                                            <div class="col-md-3">
                                                <div class="text-center">
                                                    <div class="display-6 text-info">${formatBytes((domInfo.allocated_memory || 0) * 1024, 0)}</div>
                                                    <small class="text-muted">RAM</small>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            `
                                    : ''
                            }
                        </div>
                    </div>
                </div>
            `;
        }

        cmlContent.innerHTML = `
            <div class="row g-3">
                <!-- System Information -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-info-circle me-2"></i>System Information</h6>
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td class="text-muted" style="width: 50%;">Version</td>
                                    <td><strong>${escapeHtml(worker.cml_version || 'Unknown')}</strong></td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Ready State</td>
                                    <td><i class="bi bi-${readyIcon} text-${readyBadge}"></i> <span class="badge bg-${readyBadge}">${readyText}</span></td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Uptime</td>
                                    <td>${uptimeDisplay}</td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Active Nodes</td>
                                    <td><strong>${domInfo?.running_nodes ?? (worker.cml_labs_count !== null ? worker.cml_labs_count : '—')}</strong> ${domInfo?.total_nodes ? `/ ${domInfo.total_nodes}` : ''}</td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Last Synced</td>
                                    <td><small>${worker.cml_last_synced_at ? formatDate(worker.cml_last_synced_at) : 'Never'}</small></td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- License & Edition -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="bi bi-key me-2"></i>License & Edition</h6>
                            ${licenseInfo ? '<button class="btn btn-sm btn-outline-primary" onclick="workersUi.showLicenseDetailsModal()"><i class="bi bi-info-circle me-1"></i>Details</button>' : ''}
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td class="text-muted" style="width: 50%;">Licensed</td>
                                    <td><span class="badge bg-${licensedBadge}">${isLicensed ? 'Yes' : 'No'}</span></td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Edition</td>
                                    <td><span class="badge bg-${editionBadge}">${editionText}</span></td>
                                </tr>
                            </table>
                            ${!health.is_licensed && !licenseInfo ? '<div class="alert alert-info alert-sm mt-2 mb-0 py-1 px-2"><small><i class="bi bi-info-circle"></i> Click Refresh to fetch latest license data</small></div>' : ''}
                        </div>
                    </div>
                </div>

                <!-- System Health -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-heart-pulse me-2"></i>System Health</h6>
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr>
                                    <td class="text-muted" style="width: 50%;">Overall Status</td>
                                    <td><i class="bi bi-${healthIcon} text-${healthBadge}"></i> <span class="badge bg-${healthBadge}">${healthValid ? 'Valid' : 'Invalid'}</span></td>
                                </tr>
                                <tr>
                                    <td class="text-muted">Service Status</td>
                                    <td>${worker.service_status ? `<span class="badge bg-${worker.service_status === 'available' ? 'success' : 'secondary'}">${escapeHtml(worker.service_status)}</span>` : '—'}</td>
                                </tr>
                                <tr>
                                    <td class="text-muted">HTTPS Endpoint</td>
                                    <td class="font-monospace small">${worker.https_endpoint ? `<a href="${escapeHtml(worker.https_endpoint)}" target="_blank" class="text-decoration-none">${escapeHtml(worker.https_endpoint)}</a>` : 'Not set'}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Controller Status (if available) -->
                ${controllerSection}

                <!-- Statistics -->
                ${statsSection}

                <!-- Compute Health (if available) -->
                ${computeSection}
            </div>
        `;
    } catch (error) {
        cmlContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Failed to load CML details: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

// Helper function to format bytes
// Helper function to format bytes
function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

/**
 * Load labs tab data
 */
async function loadLabsTab() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal.dataset.workerId;
    const region = modal.dataset.workerRegion;
    const labsContent = document.getElementById('worker-details-labs');

    if (!workerId || !region) {
        labsContent.innerHTML = '<div class="alert alert-warning">No worker selected</div>';
        return;
    }

    labsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading labs...</p></div>';

    try {
        const labs = await workersApi.getWorkerLabs(region, workerId);

        if (!Array.isArray(labs) || labs.length === 0) {
            labsContent.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-folder2-open"></i> No labs found on this worker
                </div>
            `;
            return;
        }

        let html = '<div class="accordion accordion-flush" id="labs-accordion">';

        labs.forEach((lab, index) => {
            const collapseId = `lab-collapse-${index}`;
            const headingId = `lab-heading-${index}`;

            // State badge with color coding
            let stateBadge = '';
            switch (lab.state) {
                case 'STARTED':
                    stateBadge = '<span class="badge bg-success">Started</span>';
                    break;
                case 'STOPPED':
                    stateBadge = '<span class="badge bg-secondary">Stopped</span>';
                    break;
                case 'DEFINED_ON_CORE':
                    stateBadge = '<span class="badge bg-info">Defined</span>';
                    break;
                default:
                    stateBadge = `<span class="badge bg-secondary">${escapeHtml(lab.state)}</span>`;
            }

            // Format dates with relative time
            const created = lab.created ? formatDateWithRelative(lab.created) : 'N/A';
            const modified = lab.modified ? formatDateWithRelative(lab.modified) : 'N/A';

            html += `
                <div class="accordion-item">
                    <h2 class="accordion-header" id="${headingId}">
                        <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
                            <div class="d-flex justify-content-between align-items-center w-100 pe-3">
                                <div>
                                    <i class="bi bi-folder2-open text-primary me-2"></i>
                                    <strong>${escapeHtml(lab.title || lab.id)}</strong>
                                </div>
                                <div class="d-flex gap-2 align-items-center">
                                    ${stateBadge}
                                    <span class="badge bg-light text-dark">
                                        <i class="bi bi-diagram-3"></i> ${lab.node_count || 0} nodes
                                    </span>
                                    <span class="badge bg-light text-dark">
                                        <i class="bi bi-arrow-left-right"></i> ${lab.link_count || 0} links
                                    </span>
                                </div>
                            </div>
                        </button>
                    </h2>
                    <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}"
                         data-bs-parent="#labs-accordion">
                        <div class="accordion-body">
                            <div class="row g-3">
                                <div class="col-md-6">
                                    <div class="card h-100">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-3 text-muted">
                                                <i class="bi bi-info-circle"></i> Lab Information
                                            </h6>
                                            <dl class="row mb-0">
                                                <dt class="col-sm-4">Lab ID:</dt>
                                                <dd class="col-sm-8"><code>${escapeHtml(lab.id)}</code></dd>

                                                <dt class="col-sm-4">Title:</dt>
                                                <dd class="col-sm-8">${escapeHtml(lab.title || 'N/A')}</dd>

                                                <dt class="col-sm-4">Owner:</dt>
                                                <dd class="col-sm-8">
                                                    ${escapeHtml(lab.owner_username || 'N/A')}
                                                    ${lab.owner ? `<br><small class="text-muted">${escapeHtml(lab.owner)}</small>` : ''}
                                                </dd>

                                                <dt class="col-sm-4">State:</dt>
                                                <dd class="col-sm-8">${stateBadge}</dd>
                                            </dl>
                                        </div>
                                    </div>
                                </div>

                                <div class="col-md-6">
                                    <div class="card h-100">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-3 text-muted">
                                                <i class="bi bi-clock-history"></i> Timestamps
                                            </h6>
                                            <dl class="row mb-0">
                                                <dt class="col-sm-4">Created:</dt>
                                                <dd class="col-sm-8">${created}</dd>

                                                <dt class="col-sm-4">Modified:</dt>
                                                <dd class="col-sm-8">${modified}</dd>

                                                <dt class="col-sm-4">Nodes:</dt>
                                                <dd class="col-sm-8">
                                                    <span class="badge bg-primary">${lab.node_count || 0}</span>
                                                </dd>

                                                <dt class="col-sm-4">Links:</dt>
                                                <dd class="col-sm-8">
                                                    <span class="badge bg-primary">${lab.link_count || 0}</span>
                                                </dd>
                                            </dl>
                                        </div>
                                    </div>
                                </div>
            `;

            // Description section (if available)
            if (lab.description) {
                html += `
                                <div class="col-12">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-2 text-muted">
                                                <i class="bi bi-file-text"></i> Description
                                            </h6>
                                            <p class="mb-0">${escapeHtml(lab.description)}</p>
                                        </div>
                                    </div>
                                </div>
                `;
            }

            // Notes section (if available)
            if (lab.notes) {
                html += `
                                <div class="col-12">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-2 text-muted">
                                                <i class="bi bi-sticky"></i> Notes
                                            </h6>
                                            <pre class="mb-0" style="white-space: pre-wrap;">${escapeHtml(lab.notes)}</pre>
                                        </div>
                                    </div>
                                </div>
                `;
            }

            // Groups section (if available)
            if (lab.groups && lab.groups.length > 0) {
                html += `
                                <div class="col-12">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-2 text-muted">
                                                <i class="bi bi-people"></i> Groups
                                            </h6>
                                            <div class="d-flex flex-wrap gap-1">
                                                ${lab.groups.map(group => `<span class="badge bg-secondary">${escapeHtml(group)}</span>`).join('')}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                `;
            }

            // Control buttons section
            const isStarted = lab.state === 'STARTED';
            html += `
                                <div class="col-12">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-3 text-muted">
                                                <i class="bi bi-gear"></i> Lab Controls
                                            </h6>
                                            <div class="btn-group" role="group">
                                                <button type="button" class="btn btn-success ${isStarted ? 'disabled' : ''}"
                                                        onclick="window.workersApp.handleStartLab('${region}', '${workerId}', '${escapeHtml(lab.id)}')"
                                                        ${isStarted ? 'disabled' : ''}>
                                                    <i class="bi bi-play-fill"></i> Start Lab
                                                </button>
                                                <button type="button" class="btn btn-warning ${!isStarted ? 'disabled' : ''}"
                                                        onclick="window.workersApp.handleStopLab('${region}', '${workerId}', '${escapeHtml(lab.id)}', '${escapeHtml(lab.title || lab.id)}')"
                                                        ${!isStarted ? 'disabled' : ''}>
                                                    <i class="bi bi-stop-fill"></i> Stop Lab
                                                </button>
                                                <button type="button" class="btn btn-danger"
                                                        onclick="window.workersApp.handleWipeLab('${region}', '${workerId}', '${escapeHtml(lab.id)}', '${escapeHtml(lab.title || lab.id)}')">
                                                    <i class="bi bi-trash-fill"></i> Wipe Lab
                                                </button>
                                            </div>
                                            <div class="mt-2">
                                                <small class="text-muted">
                                                    <i class="bi bi-info-circle"></i>
                                                    Stop and Wipe operations require confirmation
                                                </small>
                                            </div>
                                        </div>
                                    </div>
                                </div>
            `;

            html += `
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        labsContent.innerHTML = html;

        // Initialize date tooltips after rendering
        initializeDateTooltips();
    } catch (error) {
        labsContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Failed to load labs: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

/**
 * Handle starting a lab
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {string} labId - Lab ID
 */
async function handleStartLab(region, workerId, labId) {
    try {
        showToast('Starting lab...', 'info');
        await workersApi.startLab(region, workerId, labId);
        showToast('Lab started successfully', 'success');
        // Reload labs to update state
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to start lab: ${error.message}`, 'danger');
    }
}

/**
 * Handle stopping a lab with confirmation
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {string} labId - Lab ID
 * @param {string} labTitle - Lab title for display
 */
async function handleStopLab(region, workerId, labId, labTitle) {
    const confirmed = await showConfirmDialog('Stop Lab', `Are you sure you want to stop lab "${labTitle}"?`, 'This will stop all running nodes in the lab.', 'warning');

    if (!confirmed) return;

    try {
        showToast('Stopping lab...', 'info');
        await workersApi.stopLab(region, workerId, labId);
        showToast('Lab stopped successfully', 'success');
        // Reload labs to update state
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to stop lab: ${error.message}`, 'danger');
    }
}

/**
 * Handle wiping a lab with confirmation
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {string} labId - Lab ID
 * @param {string} labTitle - Lab title for display
 */
async function handleWipeLab(region, workerId, labId, labTitle) {
    const confirmed = await showConfirmDialog('Wipe Lab', `Are you sure you want to wipe lab "${labTitle}"?`, 'This will perform a factory reset on all nodes. This action cannot be undone!', 'danger');

    if (!confirmed) return;

    try {
        showToast('Wiping lab...', 'info');
        await workersApi.wipeLab(region, workerId, labId);
        showToast('Lab wiped successfully', 'success');
        // Reload labs to update state
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to wipe lab: ${error.message}`, 'danger');
    }
}

/**
 * Show a confirmation dialog
 * @param {string} title - Dialog title
 * @param {string} message - Main message
 * @param {string} details - Additional details
 * @param {string} type - Type of dialog (warning, danger)
 * @returns {Promise<boolean>} True if confirmed
 */
function showConfirmDialog(title, message, details, type = 'warning') {
    return new Promise(resolve => {
        const iconClass = type === 'danger' ? 'bi-exclamation-triangle-fill text-danger' : 'bi-exclamation-triangle text-warning';
        const btnClass = type === 'danger' ? 'btn-danger' : 'btn-warning';

        const modalHtml = `
            <div class="modal fade" id="confirmDialog" tabindex="-1" aria-labelledby="confirmDialogLabel" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="confirmDialogLabel">
                                <i class="bi ${iconClass} me-2"></i>${escapeHtml(title)}
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <p><strong>${escapeHtml(message)}</strong></p>
                            <p class="text-muted mb-0">${escapeHtml(details)}</p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn ${btnClass}" id="confirmDialogBtn">Confirm</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('confirmDialog');
        if (existingModal) {
            existingModal.remove();
        }

        // Append new modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modalElement = document.getElementById('confirmDialog');
        const modal = new bootstrap.Modal(modalElement);

        // Handle confirm button
        document.getElementById('confirmDialogBtn').addEventListener('click', () => {
            modal.hide();
            resolve(true);
        });

        // Handle cancel/close
        modalElement.addEventListener(
            'hidden.bs.modal',
            () => {
                modalElement.remove();
                resolve(false);
            },
            { once: true }
        );

        modal.show();
    });
}

/**
 * Load jobs tab data
 */
async function loadJobsTab() {
    const jobsContent = document.getElementById('worker-details-jobs');

    jobsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading scheduler jobs...</p></div>';

    try {
        const jobs = await systemApi.getSchedulerJobs();

        if (!Array.isArray(jobs) || jobs.length === 0) {
            jobsContent.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle"></i> No scheduler jobs found
                </div>
            `;
            return;
        }

        let html = `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Job ID</th>
                            <th>Name</th>
                            <th>Next Run</th>
                            <th>Trigger</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        jobs.forEach(job => {
            const nextRun = job.next_run_time || 'N/A';
            const statusBadge = job.pending ? '<span class="badge bg-warning">Pending</span>' : '<span class="badge bg-success">Scheduled</span>';

            html += `
                <tr>
                    <td><code class="small">${escapeHtml(job.id)}</code></td>
                    <td>${escapeHtml(job.name || job.func || 'Unknown')}</td>
                    <td>${escapeHtml(nextRun)}</td>
                    <td><small class="text-muted">${escapeHtml(job.trigger || 'N/A')}</small></td>
                    <td>${statusBadge}</td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        jobsContent.innerHTML = html;
    } catch (error) {
        console.error('Failed to load scheduler jobs:', error);
        jobsContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-circle"></i> ${escapeHtml(error.message || 'Failed to load scheduler jobs')}
            </div>
        `;
    }
}

/**
 * Load monitoring tab data
 */
async function loadMonitoringTab() {
    const monitoringContent = document.getElementById('worker-details-monitoring');

    monitoringContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading monitoring status...</p></div>';

    try {
        const status = await systemApi.getWorkerMonitoringStatus();

        let html = `
            <div class="row mb-4">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">Scheduler Status</h6>
                            <p class="card-text">
                                <strong>Running:</strong>
                                <span class="badge ${status.scheduler_running ? 'bg-success' : 'bg-danger'}">
                                    ${status.scheduler_running ? 'Yes' : 'No'}
                                </span>
                            </p>
                            <p class="card-text">
                                <strong>Status:</strong>
                                <span class="badge ${status.status === 'active' ? 'bg-success' : status.status === 'inactive' ? 'bg-secondary' : 'bg-danger'}">
                                    ${escapeHtml(status.status)}
                                </span>
                            </p>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="card-subtitle mb-2 text-muted">Monitoring Jobs</h6>
                            <p class="card-text">
                                <strong>Active Jobs:</strong> ${status.monitoring_job_count || 0}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        if (status.jobs && Array.isArray(status.jobs) && status.jobs.length > 0) {
            html += `
                <h6 class="mb-3">Active Monitoring Jobs</h6>
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

            status.jobs.forEach(job => {
                html += `
                    <tr>
                        <td><code class="small">${escapeHtml(job.id)}</code></td>
                        <td>${escapeHtml(job.name)}</td>
                        <td>${escapeHtml(job.next_run_time || 'N/A')}</td>
                    </tr>
                `;
            });

            html += `
                        </tbody>
                    </table>
                </div>
            `;
        }

        monitoringContent.innerHTML = html;
    } catch (error) {
        console.error('Failed to load monitoring status:', error);
        monitoringContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-circle"></i> ${escapeHtml(error.message || 'Failed to load monitoring status')}
            </div>
        `;
    }
}

/**
 * Load events tab data (admin only)
 */
async function loadEventsTab() {
    const eventsContent = document.getElementById('worker-details-events');

    eventsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading events...</p></div>';

    // Placeholder for events endpoint
    setTimeout(() => {
        eventsContent.innerHTML = `
            <div class="alert alert-warning">
                <i class="bi bi-tools"></i> Events integration coming soon
            </div>
            <p class="text-muted">This will show CloudEvents published for this worker including:</p>
            <ul class="text-muted">
                <li>Worker state changes</li>
                <li>License registration events</li>
                <li>Resource utilization alerts</li>
                <li>Error events</li>
            </ul>
        `;
    }, 500);
}

/**
 * Setup tab change handlers
 */
function setupTabHandlers() {
    const cmlTab = document.getElementById('cml-tab');
    const labsTab = document.getElementById('labs-tab');
    const jobsTab = document.getElementById('jobs-tab');
    const monitoringTab = document.getElementById('monitoring-tab');
    const eventsTab = document.getElementById('events-tab');

    if (cmlTab) {
        cmlTab.addEventListener('shown.bs.tab', loadCMLTab);
    }

    if (labsTab) {
        labsTab.addEventListener('shown.bs.tab', loadLabsTab);
    }

    if (jobsTab) {
        jobsTab.addEventListener('shown.bs.tab', loadJobsTab);
    }

    if (monitoringTab) {
        monitoringTab.addEventListener('shown.bs.tab', loadMonitoringTab);
    }

    if (eventsTab) {
        eventsTab.addEventListener('shown.bs.tab', loadEventsTab);
    }
}

/**
 * Setup refresh button handler
 */
function setupRefreshButton() {
    console.log('[setupRefreshButton] Function called');
    const refreshBtn = document.getElementById('refresh-worker-details');
    console.log('[setupRefreshButton] Button element:', refreshBtn);
    console.log('[setupRefreshButton] Button parent:', refreshBtn?.parentNode);
    console.log('[setupRefreshButton] Current worker details:', currentWorkerDetails);

    if (refreshBtn) {
        console.log('[setupRefreshButton] Attaching event listener to button');

        // Always ensure button is enabled and has correct content
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Refresh';

        // Remove any existing listeners by cloning the button
        const newBtn = refreshBtn.cloneNode(true);
        console.log('[setupRefreshButton] Button cloned, replacing in DOM');
        refreshBtn.parentNode.replaceChild(newBtn, refreshBtn);
        console.log('[setupRefreshButton] Button replaced in DOM');

        const clickHandler = async e => {
            console.log('[CLICK HANDLER] ========================================');
            console.log('[CLICK HANDLER] Refresh button clicked!');
            console.log('[CLICK HANDLER] Event:', e);
            console.log('[CLICK HANDLER] currentWorkerDetails:', currentWorkerDetails);
            console.log('[CLICK HANDLER] workersApi:', workersApi);

            if (currentWorkerDetails) {
                const { id, region } = currentWorkerDetails;
                console.log('[CLICK HANDLER] Worker ID:', id, 'Region:', region);

                // Disable button during refresh
                newBtn.disabled = true;
                const originalHtml = newBtn.innerHTML;
                newBtn.innerHTML = '<i class="bi bi-arrow-clockwise spinner-border spinner-border-sm"></i> Refreshing...';
                console.log('[CLICK HANDLER] Button disabled and text updated');

                try {
                    console.log('[CLICK HANDLER] Showing info toast');
                    showToast('Refreshing worker state from AWS...', 'info');

                    console.log('[CLICK HANDLER] Calling workersApi.refreshWorker');
                    const refreshedWorker = await workersApi.refreshWorker(region, id);
                    console.log('[CLICK HANDLER] Refresh response:', refreshedWorker);

                    // Also refresh labs data from CML API
                    try {
                        console.log('[CLICK HANDLER] Calling workersApi.refreshWorkerLabs');
                        const labsRefresh = await workersApi.refreshWorkerLabs(region, id);
                        console.log('[CLICK HANDLER] Labs refresh response:', labsRefresh);
                        if (labsRefresh && labsRefresh.labs_synced !== undefined) {
                            console.log(`[CLICK HANDLER] Labs synced: ${labsRefresh.labs_synced}, created: ${labsRefresh.labs_created}, updated: ${labsRefresh.labs_updated}`);
                        }
                    } catch (labsError) {
                        // Don't fail the whole refresh if labs refresh fails
                        console.warn('[CLICK HANDLER] Labs refresh failed (non-fatal):', labsError);
                        // Show a warning toast but don't block the refresh
                        showToast('Worker refreshed, but labs refresh failed: ' + (labsError.message || 'Unknown error'), 'warning');
                    }

                    showToast('Worker state refreshed successfully', 'success');

                    // Re-enable button before reloading modal (so it gets cloned in correct state)
                    newBtn.disabled = false;
                    newBtn.innerHTML = originalHtml;
                    console.log('[CLICK HANDLER] Button re-enabled before reload');

                    // TODO: Replace manual refresh with SSE (Server-Sent Events)
                    // Once Labs tab and all metrics are finalized, implement real-time
                    // updates via CloudEventBus streaming. This will auto-update the UI
                    // when scheduled jobs complete (every 5 minutes) without user action.
                    // See TODO.md for full SSE implementation plan.

                    // Reload the workers list to reflect updated state
                    console.log('[CLICK HANDLER] Reloading workers list');
                    await loadWorkers();

                    // Reload the worker details modal with fresh data
                    console.log('[CLICK HANDLER] Reloading worker details modal');
                    await showWorkerDetails(id, region);

                    // If Labs tab is active, reload it to show updated lab data
                    const labsTab = document.querySelector('#worker-details-tabs button[data-bs-target="#worker-details-labs"]');
                    if (labsTab && labsTab.classList.contains('active')) {
                        console.log('[CLICK HANDLER] Labs tab is active, reloading labs data');
                        await loadLabsTab();
                    }
                } catch (error) {
                    console.error('[CLICK HANDLER] Error during refresh:', error);
                    showToast(error.message || 'Failed to refresh worker state', 'error');

                    // Re-enable button on error
                    newBtn.disabled = false;
                    newBtn.innerHTML = originalHtml;
                    console.log('[CLICK HANDLER] Button re-enabled after error');
                }
            } else {
                console.warn('[CLICK HANDLER] No currentWorkerDetails available for refresh');
                showToast('Unable to refresh: worker details not loaded', 'error');
            }
        };

        newBtn.addEventListener('click', clickHandler);
        console.log('[setupRefreshButton] Click event listener attached');

        // Test: trigger a click programmatically to verify it works
        console.log('[setupRefreshButton] Test: Button onclick property:', newBtn.onclick);
    } else {
        console.error('[setupRefreshButton] ERROR: Refresh button not found in DOM!');
        console.error('[setupRefreshButton] Available buttons:', document.querySelectorAll('button'));
    }
}

/**
 * Setup delete button handler in worker details modal
 */
function setupDeleteButtonInDetails() {
    console.log('[setupDeleteButtonInDetails] Function called');
    const deleteBtn = document.getElementById('delete-worker-from-details-btn');
    console.log('[setupDeleteButtonInDetails] Button element:', deleteBtn);

    if (deleteBtn) {
        console.log('[setupDeleteButtonInDetails] Attaching event listener to button');

        // Remove any existing listeners by cloning the button
        const newBtn = deleteBtn.cloneNode(true);
        deleteBtn.parentNode.replaceChild(newBtn, deleteBtn);

        const clickHandler = e => {
            console.log('[DELETE HANDLER] Delete button clicked from details modal');
            console.log('[DELETE HANDLER] currentWorkerDetails:', currentWorkerDetails);

            if (currentWorkerDetails) {
                const { id, region, name } = currentWorkerDetails;
                console.log('[DELETE HANDLER] Opening delete modal for:', { id, region, name });

                // Close the worker details modal first
                const workerDetailsModal = bootstrap.Modal.getInstance(document.getElementById('workerDetailsModal'));
                if (workerDetailsModal) {
                    workerDetailsModal.hide();
                }

                // Show delete modal
                showDeleteModal(id, region, name);
            } else {
                console.warn('[DELETE HANDLER] No currentWorkerDetails available');
                showToast('Unable to delete: worker details not loaded', 'error');
            }
        };

        newBtn.addEventListener('click', clickHandler);
        console.log('[setupDeleteButtonInDetails] Click event listener attached');
    } else {
        console.error('[setupDeleteButtonInDetails] ERROR: Delete button not found in DOM!');
    }
}

/**
 * Show license registration modal
 */
function showLicenseModal(workerId, region) {
    document.getElementById('license-worker-id').value = workerId;
    document.getElementById('license-worker-region').value = region;
    new bootstrap.Modal(document.getElementById('registerLicenseModal')).show();
}

/**
 * Start a worker
 */
async function startWorker(workerId, region) {
    if (!isAdmin()) {
        showToast('Permission denied. Only administrators can start workers.', 'error');
        return;
    }

    try {
        await workersApi.startWorker(region, workerId);
        showToast('Worker start initiated', 'success');
        setTimeout(() => loadWorkers(), 2000);
    } catch (error) {
        console.error('Failed to start worker:', error);
        showToast(error.message || 'Failed to start worker', 'error');
    }
}

/**
 * Stop a worker
 */
async function stopWorker(workerId, region) {
    if (!isAdmin()) {
        showToast('Permission denied. Only administrators can stop workers.', 'error');
        return;
    }

    try {
        await workersApi.stopWorker(region, workerId);
        showToast('Worker stop initiated', 'success');
        setTimeout(() => loadWorkers(), 2000);
    } catch (error) {
        console.error('Failed to stop worker:', error);
        showToast(error.message || 'Failed to stop worker', 'error');
    }
}

/**
 * Show confirmation modal for starting a worker
 */
function showStartConfirmation(workerId, region, workerName) {
    if (!isAdmin()) {
        showToast('Permission denied. Only administrators can start workers.', 'error');
        return;
    }

    const modal = document.getElementById('confirmModal');
    const title = document.getElementById('confirm-modal-title');
    const message = document.getElementById('confirm-modal-message');
    const actionBtn = document.getElementById('confirm-modal-action');

    title.textContent = 'Start Worker';
    message.textContent = `Are you sure you want to start worker "${workerName}"? This will boot up the EC2 instance and start the CML service.`;
    actionBtn.textContent = 'Start Worker';
    actionBtn.className = 'btn btn-success';

    // Remove any existing event listeners
    const newActionBtn = actionBtn.cloneNode(true);
    actionBtn.parentNode.replaceChild(newActionBtn, actionBtn);

    newActionBtn.addEventListener('click', async () => {
        bootstrap.Modal.getInstance(modal).hide();
        await startWorker(workerId, region);
    });

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Show confirmation modal for stopping a worker
 */
function showStopConfirmation(workerId, region, workerName) {
    if (!isAdmin()) {
        showToast('Permission denied. Only administrators can stop workers.', 'error');
        return;
    }

    const modal = document.getElementById('confirmModal');
    const title = document.getElementById('confirm-modal-title');
    const message = document.getElementById('confirm-modal-message');
    const actionBtn = document.getElementById('confirm-modal-action');

    title.textContent = 'Stop Worker';
    message.textContent = `Are you sure you want to stop worker "${workerName}"? This will shut down the EC2 instance and stop the CML service. Any running labs will be affected.`;
    actionBtn.textContent = 'Stop Worker';
    actionBtn.className = 'btn btn-warning';

    // Remove any existing event listeners
    const newActionBtn = actionBtn.cloneNode(true);
    actionBtn.parentNode.replaceChild(newActionBtn, actionBtn);

    newActionBtn.addEventListener('click', async () => {
        bootstrap.Modal.getInstance(modal).hide();
        await stopWorker(workerId, region);
    });

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Setup delete worker modal
 */
function setupDeleteWorkerModal() {
    const submitBtn = document.getElementById('submit-delete-worker-btn');
    if (!submitBtn) {
        console.error('Delete worker submit button not found');
        return;
    }

    submitBtn.addEventListener('click', async () => {
        const workerId = document.getElementById('delete-worker-id')?.value;
        const region = document.getElementById('delete-worker-region')?.value;
        const terminateInstance = document.getElementById('delete-terminate-instance')?.checked || false;

        if (!workerId || !region) {
            showToast('Missing worker information', 'error');
            return;
        }

        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deleting...';

            await workersApi.deleteWorker(region, workerId, terminateInstance);

            const action = terminateInstance ? 'deleted and terminated' : 'deleted';
            showToast(`Worker ${action} successfully`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('deleteWorkerModal')).hide();
            document.getElementById('delete-worker-form').reset();
            setTimeout(() => loadWorkers(), 1000);
        } catch (error) {
            console.error('Failed to delete worker:', error);
            showToast(error.message || 'Failed to delete worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-trash"></i> Delete Worker';
        }
    });
}

/**
 * Show delete worker modal
 */
function showDeleteModal(workerId, region, name) {
    if (!isAdmin()) {
        showToast('Permission denied. Only administrators can delete workers.', 'error');
        return;
    }

    document.getElementById('delete-worker-id').value = workerId;
    document.getElementById('delete-worker-region').value = region;
    document.getElementById('delete-worker-name').textContent = name;
    document.getElementById('delete-terminate-instance').checked = false;

    const modal = new bootstrap.Modal(document.getElementById('deleteWorkerModal'));
    modal.show();
}

/**
 * Refresh workers list
 */
async function refreshWorkers() {
    await loadWorkers();
    showToast('Workers refreshed', 'info');
}

// Utility functions
function getStatusBadgeClass(status) {
    const classes = {
        running: 'bg-success',
        stopped: 'bg-warning',
        pending: 'bg-info',
        stopping: 'bg-warning',
        terminated: 'bg-danger',
    };
    return classes[status] || 'bg-secondary';
}

function getServiceStatusBadgeClass(status) {
    const classes = {
        available: 'bg-success',
        unavailable: 'bg-secondary',
        degraded: 'bg-warning',
    };
    return classes[status] || 'bg-secondary';
}

function getLicenseStatusBadgeClass(status) {
    const classes = {
        registered: 'bg-success',
        unregistered: 'bg-warning',
        expired: 'bg-danger',
    };
    return classes[status] || 'bg-secondary';
}

function getCpuProgressClass(value) {
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-success';
}

function getMemoryProgressClass(value) {
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-info';
}

function getDiskProgressClass(value) {
    if (value >= 90) return 'bg-danger';
    if (value >= 70) return 'bg-warning';
    return 'bg-primary';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    // Use the utility function that includes relative time
    return formatDateWithRelative(dateString);
}

/**
 * Show license details modal with detailed licensing information
 */
async function showLicenseDetailsModal() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal.dataset.workerId;
    const region = modal.dataset.workerRegion;

    if (!workerId || !region) {
        showToast('No worker selected', 'error');
        return;
    }

    try {
        const worker = await workersApi.getWorkerDetails(region, workerId);

        if (!worker.cml_license_info) {
            showToast('No license information available for this worker', 'warning');
            return;
        }

        const licenseData = worker.cml_license_info;

        // Check if license modal exists
        const licenseModalElement = document.getElementById('licenseDetailsModal');
        if (!licenseModalElement) {
            console.error('License details modal not found in DOM');
            showToast('License details modal not available. Please refresh the page.', 'error');
            return;
        }

        // Check if content elements exist
        const registrationContent = document.getElementById('license-registration-content');
        const authorizationContent = document.getElementById('license-authorization-content');
        const featuresContent = document.getElementById('license-features-content');
        const transportContent = document.getElementById('license-transport-content');

        if (!registrationContent || !authorizationContent || !featuresContent || !transportContent) {
            console.error('License modal content elements not found:', {
                registration: !!registrationContent,
                authorization: !!authorizationContent,
                features: !!featuresContent,
                transport: !!transportContent,
            });
            showToast('License details modal not properly loaded. Please refresh the page.', 'error');
            return;
        }

        // Populate tabs
        registrationContent.innerHTML = renderRegistrationTab(licenseData.registration || {});
        authorizationContent.innerHTML = renderAuthorizationTab(licenseData.authorization || {});
        featuresContent.innerHTML = renderFeaturesTab(licenseData.features || []);
        transportContent.innerHTML = renderTransportTab(licenseData.transport || {}, licenseData.udi || {});

        // Show the modal
        const licenseModal = new bootstrap.Modal(licenseModalElement);
        licenseModal.show();
    } catch (error) {
        console.error('Error loading license details:', error);
        showToast('Failed to load license details', 'error');
    }
}

function renderRegistrationTab(registration) {
    const status = registration.status || 'UNKNOWN';
    const statusBadge = status === 'COMPLETED' ? 'success' : status === 'FAILED' ? 'danger' : 'warning';

    return `
        <div class="card">
            <div class="card-body">
                <div class="row mb-3">
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Status</h6>
                        <span class="badge bg-${statusBadge} fs-6">${status}</span>
                    </div>
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Expires</h6>
                        <p class="mb-0">${registration.expires || 'N/A'}</p>
                    </div>
                </div>

                <div class="row mb-3">
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Smart Account</h6>
                        <p class="mb-0">${registration.smart_account || 'N/A'}</p>
                    </div>
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Virtual Account</h6>
                        <p class="mb-0">${registration.virtual_account || 'N/A'}</p>
                    </div>
                </div>

                ${
                    registration.register_time
                        ? `
                <div class="mt-4">
                    <h6 class="text-muted mb-3">Register Time</h6>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" style="width: 40%;">Attempted:</td><td>${registration.register_time.attempted || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Succeeded:</td><td>${registration.register_time.succeeded || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Status:</td><td><span class="badge bg-${registration.register_time.success === 'SUCCESS' ? 'success' : 'secondary'}">${registration.register_time.success || 'N/A'}</span></td></tr>
                        <tr><td class="text-muted">Failure:</td><td>${registration.register_time.failure || 'N/A'}</td></tr>
                    </table>
                </div>
                `
                        : ''
                }

                ${
                    registration.renew_time
                        ? `
                <div class="mt-4">
                    <h6 class="text-muted mb-3">Renew Time</h6>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" style="width: 40%;">Scheduled:</td><td>${registration.renew_time.scheduled || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Attempted:</td><td>${registration.renew_time.attempted || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Succeeded:</td><td>${registration.renew_time.succeeded || 'N/A'}</td></tr>
                    </table>
                </div>
                `
                        : ''
                }
            </div>
        </div>
    `;
}

function renderAuthorizationTab(authorization) {
    const status = authorization.status || 'UNKNOWN';
    const statusBadge = status === 'IN_COMPLIANCE' ? 'success' : status === 'OUT_OF_COMPLIANCE' ? 'danger' : 'warning';

    return `
        <div class="card">
            <div class="card-body">
                <div class="row mb-3">
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Status</h6>
                        <span class="badge bg-${statusBadge} fs-6">${status.replace('_', ' ')}</span>
                    </div>
                    <div class="col-md-6">
                        <h6 class="text-muted mb-2">Expires</h6>
                        <p class="mb-0">${authorization.expires || 'N/A'}</p>
                    </div>
                </div>

                ${
                    authorization.renew_time
                        ? `
                <div class="mt-4">
                    <h6 class="text-muted mb-3">Renew Time</h6>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" style="width: 40%;">Scheduled:</td><td>${authorization.renew_time.scheduled || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Attempted:</td><td>${authorization.renew_time.attempted || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Succeeded:</td><td>${authorization.renew_time.succeeded || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Status:</td><td><span class="badge bg-${authorization.renew_time.status === 'SUCCEEDED' ? 'success' : 'secondary'}">${authorization.renew_time.status || 'N/A'}</span></td></tr>
                    </table>
                </div>
                `
                        : ''
                }
            </div>
        </div>
    `;
}

function renderFeaturesTab(features) {
    if (!features || features.length === 0) {
        return '<div class="alert alert-info"><i class="bi bi-info-circle"></i> No features available</div>';
    }

    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Feature Name</th>
                        <th>Status</th>
                        <th>In Use</th>
                        <th>Range</th>
                        <th>Version</th>
                    </tr>
                </thead>
                <tbody>
                    ${features
                        .map(feature => {
                            const statusBadge = feature.status === 'IN_COMPLIANCE' ? 'success' : feature.status === 'INIT' ? 'secondary' : 'warning';
                            return `
                            <tr>
                                <td>
                                    <strong>${feature.name || 'Unknown'}</strong>
                                    ${feature.description ? `<br><small class="text-muted">${feature.description}</small>` : ''}
                                </td>
                                <td><span class="badge bg-${statusBadge}">${feature.status || 'N/A'}</span></td>
                                <td>${feature.in_use !== undefined ? feature.in_use : 'N/A'}</td>
                                <td>${feature.min !== undefined && feature.max !== undefined ? `${feature.min} - ${feature.max}` : 'N/A'}</td>
                                <td>${feature.version || 'N/A'}</td>
                            </tr>
                        `;
                        })
                        .join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderTransportTab(transport, udi) {
    return `
        <div class="card mb-3">
            <div class="card-header bg-light">
                <h6 class="mb-0"><i class="bi bi-hdd-network me-2"></i>Smart Software Manager (SSM)</h6>
            </div>
            <div class="card-body">
                <table class="table table-sm table-borderless">
                    <tr>
                        <td class="text-muted" style="width: 30%;">SSMS URL:</td>
                        <td class="font-monospace small">${transport.ssms || 'N/A'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Default SSMS:</td>
                        <td class="font-monospace small">${transport.default_ssms || 'N/A'}</td>
                    </tr>
                    ${
                        transport.proxy && (transport.proxy.server || transport.proxy.port)
                            ? `
                    <tr>
                        <td class="text-muted">Proxy:</td>
                        <td>${transport.proxy.server || 'None'}${transport.proxy.port ? ':' + transport.proxy.port : ''}</td>
                    </tr>
                    `
                            : ''
                    }
                </table>
            </div>
        </div>

        <div class="card">
            <div class="card-header bg-light">
                <h6 class="mb-0"><i class="bi bi-fingerprint me-2"></i>Unique Device Identifier (UDI)</h6>
            </div>
            <div class="card-body">
                <table class="table table-sm table-borderless">
                    <tr>
                        <td class="text-muted" style="width: 30%;">Hostname:</td>
                        <td>${udi.hostname || 'N/A'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Product UUID:</td>
                        <td class="font-monospace small">${udi.product_uuid || 'N/A'}</td>
                    </tr>
                </table>
            </div>
        </div>
    `;
}

// Export functions to global scope for onclick handlers
window.workersApp = {
    showWorkerDetails,
    showLicenseModal,
    showLicenseDetailsModal,
    showDeleteModal,
    showStartConfirmation,
    showStopConfirmation,
    startWorker,
    stopWorker,
    refreshWorkers,
    handleStartLab,
    handleStopLab,
    handleWipeLab,
};

// Alias for UI component functions
window.workersUi = window.workersApp;
