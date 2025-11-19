/**
 * Workers UI Component
 * Handles rendering and interaction for CML Workers management
 */

import * as systemApi from '../api/system.js';
import * as workersApi from '../api/workers.js';
import { showToast } from './notifications.js';
import { showConfirm } from '../components/modals.js';
import { isAdmin, isAdminOrManager } from '../utils/roles.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';
import { renderWorkerOverview } from '../components/workerOverview.js';
import { renderMetrics } from '../components/metricsPanel.js';
import { updateStatistics, renderWorkersTable, renderWorkersCards, applyFilters, applyUserFilters, bindRenderDependencies } from './worker-render.js';
// License panel rendering now handled in worker-modals.js; local detailed rendering removed
import { escapeHtml } from '../components/escape.js';
import { getStatusBadgeClass, getServiceStatusBadgeClass, getCpuProgressClass, getMemoryProgressClass, getDiskProgressClass } from '../components/status-badges.js';
import { showWorkerDetails, loadCloudWatchMetrics, setupEnableMonitoringButton, bindWorkerDetailsDependencies } from './worker-details.js';
import { ensureTimingHeader, startMetricsCountdown, stopMetricsCountdown, resetMetricsCountdown, updateLastRefreshedDisplay } from './worker-timing.js';
import { subscribe, fetchWorkerDetails, setActiveWorker, getActiveWorker, getWorker, getAllWorkers, getTiming, updateTiming, upsertWorkerSnapshot, updateWorkerMetrics, logStoreSnapshot } from '../store/workerStore.js';
import { loadLabsTab, handleStartLab, handleStopLab, handleWipeLab, bindLabsDependencies } from './worker-labs.js';
import { loadJobsTab } from './worker-jobs.js';
import { loadMonitoringTab } from './worker-monitoring.js';
import { loadEventsTab } from './worker-events.js';
// Extracted modal & action logic modules
import { showLicenseModal, showLicenseDetailsModal, setupDeleteWorkerModal, showDeleteModal, setupLicenseModal, setupCreateWorkerModal, setupImportWorkerModal } from './worker-modals.js';
import { startWorker, stopWorker, showStartConfirmation, showStopConfirmation, refreshWorkers } from './worker-actions.js';
// SSE initialization moved to worker-init.js
import * as bootstrap from 'bootstrap';
import { initializeWorkersView as initializeWorkersViewCore } from './worker-init.js';

// Store current user and workers data
let currentUser = null;
let workersData = []; // derived from store; bound to render module
let unsubscribeStore = null;
let currentRegion = 'us-east-1';
let currentWorkerDetails = null; // Store current worker for refresh

// Timing handled in worker-timing module

/**
 * Initialize the workers view
 * @param {Object} user - Current authenticated user
 */
// Bind worker details module dependencies so showWorkerDetails can update local state
bindWorkerDetailsDependencies({
    getCurrentWorkerDetails: () => currentWorkerDetails,
    setCurrentWorkerDetails: v => {
        currentWorkerDetails = v;
    },
    setupRefreshButton: () => setupRefreshButton(),
    setupDeleteButtonInDetails: () => setupDeleteButtonInDetails(),
});
export function initializeWorkersView(user) {
    currentUser = user;
    if (unsubscribeStore) unsubscribeStore();
    initializeWorkersViewCore(user, {
        upsertWorkerSnapshot,
        updateWorkerMetrics,
        updateTiming,
        onLabsTabShouldReload: () => loadLabsTab(),
        subscribe,
        handleStoreUpdate,
        bindRenderDependencies,
        loadWorkers,
        getCurrentWorkerDetails: () => currentWorkerDetails,
        setCurrentWorkerDetails: v => {
            currentWorkerDetails = v;
        },
        setUnsubscribe: fn => {
            unsubscribeStore = fn;
        },
        showDeleteModal,
        setCurrentRegion: v => {
            currentRegion = v;
        },
        getWorkersData: () => workersData,
    });
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
    console.log('[loadWorkers] Fetching initial workers list from API');
    try {
        const workers = await workersApi.listWorkers(currentRegion);
        console.log(`[loadWorkers] Received ${workers.length} workers from API`);
        workers.forEach(w => {
            upsertWorkerSnapshot({
                id: w.id || w.worker_id,
                name: w.name,
                aws_region: w.aws_region || w.region,
                status: w.status,
                service_status: w.service_status,
                instance_type: w.instance_type,
                aws_instance_id: w.aws_instance_id,
                public_ip: w.public_ip,
                private_ip: w.private_ip,
                ami_id: w.ami_id,
                ami_name: w.ami_name,
                ami_description: w.ami_description,
                ami_creation_date: w.ami_creation_date,
                https_endpoint: w.https_endpoint,
                license_status: w.license_status,
                cml_version: w.cml_version,
                cml_ready: w.cml_ready,
                cml_uptime_seconds: w.cml_uptime_seconds,
                cml_labs_count: w.cml_labs_count,
                cpu_utilization: w.cpu_utilization,
                memory_utilization: w.memory_utilization,
                storage_utilization: w.storage_utilization,
                poll_interval: w.poll_interval,
                next_refresh_at: w.next_refresh_at,
                updated_at: w.updated_at,
                terminated_at: w.terminated_at,
                _reason: 'initial_load',
            });
            if (w.poll_interval && w.next_refresh_at) {
                updateTiming(w.id || w.worker_id, {
                    poll_interval: w.poll_interval,
                    next_refresh_at: w.next_refresh_at,
                    last_refreshed_at: w.updated_at || new Date().toISOString(),
                });
            }
        });
        console.log('[loadWorkers] Initial workers processed into store');
    } catch (error) {
        console.error('[loadWorkers] Failed to load workers:', error);
        showToast('Failed to load workers', 'danger');

        // Show error message in the UI
        const tbody = document.getElementById('workers-table-body');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center text-danger py-4">
                        <i class="bi bi-exclamation-triangle fs-1 d-block mb-2"></i>
                        Failed to load workers. Please refresh the page.
                    </td>
                </tr>`;
        }
    }
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
        cmlContent.innerHTML = '<div class="alert alert-warning">CML application details will appear here</div>';
        // Retry shortly in case dataset not yet set by showWorkerDetails
        setTimeout(() => {
            const m = document.getElementById('workerDetailsModal');
            if (m?.dataset.workerId && m?.dataset.workerRegion) {
                loadCMLTab();
            }
        }, 250);
        return;
    }

    cmlContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading CML details...</p></div>';

    try {
        const worker = await fetchWorkerDetails(region, workerId);

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

// Expose CML tab loader for worker-init tab handler
window.workersInternal = window.workersInternal || {};
window.workersInternal.loadCMLTab = loadCMLTab;

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
            console.log('[CLICK HANDLER][Refresh] Requesting on-demand metrics refresh');
            if (!currentWorkerDetails) {
                console.warn('[CLICK HANDLER][Refresh] No currentWorkerDetails available');
                showToast('Unable to refresh: worker details not loaded', 'danger');
                return;
            }
            const { id, region } = currentWorkerDetails;
            if (!id || !region) {
                showToast('Refresh failed: missing worker id/region', 'danger');
                return;
            }

            // Disable button while scheduling
            const originalHtml = newBtn.innerHTML;
            newBtn.disabled = true;
            newBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Scheduling...';
            try {
                const result = await workersApi.requestWorkerRefresh(region, id);
                console.log('[CLICK HANDLER][Refresh] API response:', result);
                if (result.scheduled) {
                    const eta = result.eta_seconds != null ? ` ETA: ${result.eta_seconds}s` : '';
                    showToast(`Refresh scheduled.${eta}`, 'info');
                } else {
                    const reason = result.reason || 'unknown';
                    let msg = `Refresh skipped: ${reason}`;
                    if (result.retry_after_seconds) msg += ` (retry in ${result.retry_after_seconds}s)`;
                    showToast(msg, 'warning');
                }
            } catch (error) {
                console.error('[CLICK HANDLER][Refresh] Error scheduling refresh:', error);
                showToast(error.message || 'Failed to schedule refresh', 'danger');
            } finally {
                // Re-enable button immediately; SSE events will deliver updates shortly
                newBtn.disabled = false;
                newBtn.innerHTML = originalHtml;
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

// Utility functions
// (Replaced local badge & escape helpers with centralized component utilities)

function formatDate(dateString) {
    // Use the utility function that includes relative time
    return formatDateWithRelative(dateString);
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
    // Expose escapeHtml for legacy inline handlers (will remove later)
    escapeHtml,
};

// ---------------------------------------------------------------------------
// Backward Compatibility Shim
// Older bundled UI code (pre modular refactor) referenced `_workersJs.refreshWorker(workerId, region)`
// and a global `refreshWorker` function to trigger an on-demand metrics refresh of a single worker.
// After refactor we use `workersApi.requestWorkerRefresh(region, id)` plus store-driven updates.
// This shim provides a safe no-op fallback mapping to avoid console errors in stale cached assets.
// ---------------------------------------------------------------------------
if (!window._workersJs) {
    window._workersJs = {};
}
if (typeof window._workersJs.refreshWorker !== 'function') {
    window._workersJs.refreshWorker = async function (workerId, region) {
        try {
            // Allow argument order flexibility: some legacy handlers passed (region, workerId)
            // Detect if first arg looks like a region pattern (contains '-') and second looks like id (length > 6)
            if (workerId && region && /-[0-9]/.test(workerId) && !/-[0-9]/.test(region)) {
                // Likely reversed order; swap
                const tmp = workerId;
                workerId = region;
                region = tmp;
            }
            // Fallback to current modal details if params missing
            if ((!workerId || !region) && window.workersApp && window.workersApp.showWorkerDetails) {
                if (window.workersInternal?.getWorkersData) {
                    const current = window.workersInternal.getWorkersData().find(w => w.id === (workerId || (window.currentWorkerDetails && window.currentWorkerDetails.id)));
                    region = region || current?.aws_region || 'us-east-1';
                }
                if (!workerId && window.currentWorkerDetails?.id) {
                    workerId = window.currentWorkerDetails.id;
                }
            }
            if (!workerId || !region) {
                console.warn('[compat.refreshWorker] Missing workerId/region; aborting');
                return false;
            }
            const btn = document.getElementById('refresh-worker-details');
            if (btn) {
                btn.disabled = true;
                const original = btn.innerHTML;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Scheduling...';
                try {
                    const result = await workersApi.requestWorkerRefresh(region, workerId);
                    if (result?.scheduled) {
                        showToast('Refresh scheduled (compat)', 'info');
                    } else {
                        showToast('Refresh skipped (compat)', 'warning');
                    }
                } catch (e) {
                    console.error('[compat.refreshWorker] Error:', e);
                    showToast(e.message || 'Compat refresh failed', 'danger');
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = original;
                }
            } else {
                // No button context; just schedule
                const result = await workersApi.requestWorkerRefresh(region, workerId);
                if (result?.scheduled) {
                    showToast('Refresh scheduled (compat)', 'info');
                }
            }
            return true;
        } catch (err) {
            console.error('[compat.refreshWorker] Unexpected error:', err);
            return false;
        }
    };
    console.log('[compat] Installed legacy _workersJs.refreshWorker shim');
}

// Legacy global alias for scripts calling just `refreshWorker(workerId, region)`
if (typeof window.refreshWorker !== 'function') {
    window.refreshWorker = function (workerId, region) {
        return window._workersJs.refreshWorker(workerId, region);
    };
}

// Alias for UI component functions
window.workersUi = window.workersApp;

// Store subscription handler: derive workersData, render views, update modal.
function handleStoreUpdate(storeState) {
    workersData = getAllWorkers();
    // expose for external modules
    window.workersInternal = window.workersInternal || {};
    window.workersInternal.getWorkersData = () => workersData;
    // Always update global statistics & timing, regardless of role
    updateStatistics();
    if (hasAdminAccess(currentUser)) {
        renderWorkersTable();
    } else {
        renderWorkersCards();
    }
    // If modal open for active worker, refresh metrics panel & timing displays
    if (currentWorkerDetails && currentWorkerDetails.id === storeState.activeWorkerId) {
        const w = getWorker(storeState.activeWorkerId);
        if (w) {
            const metricsSection = document.getElementById('cloudwatch-metrics-section');
            if (metricsSection) metricsSection.innerHTML = renderMetrics(w);
            updateLastRefreshedDisplay();
            // Restart countdown if timing changed
            startMetricsCountdown();
        }
    }
}
