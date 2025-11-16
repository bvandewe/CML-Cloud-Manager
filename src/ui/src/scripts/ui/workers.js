/**
 * Workers UI Component
 * Handles rendering and interaction for CML Workers management
 */

import * as workersApi from '../api/workers.js';
import { showToast } from './notifications.js';
import * as bootstrap from 'bootstrap';

// Store current user and workers data
let currentUser = null;
let workersData = [];
let currentRegion = 'us-east-1';

/**
 * Initialize workers view based on user role
 * @param {Object} user - Current authenticated user
 */
export function initializeWorkersView(user) {
    currentUser = user;
    const workersSection = document.getElementById('workers-section');
    const adminView = document.getElementById('workers-admin-view');
    const userView = document.getElementById('workers-user-view');

    if (!workersSection) return;

    workersSection.style.display = 'block';

    // Show appropriate view based on role
    if (hasAdminAccess(user)) {
        adminView.style.display = 'block';
        userView.style.display = 'none';
        initializeAdminView();
    } else {
        adminView.style.display = 'none';
        userView.style.display = 'block';
        initializeUserView();
    }

    setupEventListeners();
    loadWorkers();
}

/**
 * Check if user has admin/manager access
 * @param {Object} user
 * @returns {boolean}
 */
function hasAdminAccess(user) {
    const roles = user.realm_access?.roles || [];
    return roles.includes('admin') || roles.includes('manager');
}

/**
 * Initialize admin/manager view
 */
function initializeAdminView() {
    console.log('Initializing admin view for workers');
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
    setupCreateWorkerModal();
    setupImportWorkerModal();
    setupLicenseModal();
    setupTabHandlers();
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
                <td colspan="10" class="text-center text-muted py-4">
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
        <tr>
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
                <span class="badge ${getLicenseStatusBadgeClass(worker.license_status)}">
                    ${worker.license_status}
                </span>
            </td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    <button class="btn btn-outline-primary" onclick="window.workersApp.showWorkerDetails('${worker.id}', '${worker.aws_region}')"
                            title="View Details">
                        <i class="bi bi-info-circle"></i>
                    </button>
                    ${
                        worker.status === 'stopped'
                            ? `<button class="btn btn-outline-success" onclick="window.workersApp.startWorker('${worker.id}', '${worker.aws_region}')"
                                title="Start">
                            <i class="bi bi-play-fill"></i>
                        </button>`
                            : ''
                    }
                    ${
                        worker.status === 'running'
                            ? `<button class="btn btn-outline-warning" onclick="window.workersApp.stopWorker('${worker.id}', '${worker.aws_region}')"
                                title="Stop">
                            <i class="bi bi-stop-fill"></i>
                        </button>`
                            : ''
                    }
                    ${
                        worker.license_status === 'unregistered'
                            ? `<button class="btn btn-outline-info" onclick="window.workersApp.showLicenseModal('${worker.id}', '${worker.aws_region}')"
                                title="Register License">
                            <i class="bi bi-key"></i>
                        </button>`
                            : ''
                    }
                    <button class="btn btn-outline-danger" onclick="window.workersApp.confirmTerminateWorker('${worker.id}', '${worker.aws_region}', '${escapeHtml(worker.name)}')"
                            title="Terminate">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `
        )
        .join('');
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

    if (importByInstance) {
        importByInstance.addEventListener('change', () => {
            instanceIdGroup.style.display = 'block';
            amiNameGroup.style.display = 'none';
        });
    }

    if (importByAmi) {
        importByAmi.addEventListener('change', () => {
            instanceIdGroup.style.display = 'none';
            amiNameGroup.style.display = 'block';
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
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Importing...';

            const data = {};
            if (isInstanceMethod) {
                data.aws_instance_id = instanceId;
            } else {
                data.ami_name = amiName;
            }
            if (name) data.name = name;

            await workersApi.importWorker(region, data);

            showToast('Worker imported successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('importWorkerModal')).hide();
            document.getElementById('import-worker-form').reset();

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
    const modalElement = document.getElementById('workerDetailsModal');
    if (!modalElement) {
        console.error('Worker details modal element not found');
        showToast('Failed to open worker details: modal not found', 'error');
        return;
    }

    const modal = new bootstrap.Modal(modalElement);
    const overviewContent = document.getElementById('worker-details-overview');

    if (!overviewContent) {
        console.error('Worker details overview content element not found');
        showToast('Failed to open worker details: content area not found', 'error');
        return;
    }

    // Show/hide admin-only tabs based on user role
    const adminTabs = document.querySelectorAll('.admin-only-tab');
    if (hasAdminAccess(currentUser)) {
        adminTabs.forEach(tab => (tab.style.display = 'block'));
    } else {
        adminTabs.forEach(tab => (tab.style.display = 'none'));
    }

    modal.show();

    // Load overview data
    try {
        const worker = await workersApi.getWorkerDetails(region, workerId);

        overviewContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Basic Information</h5>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="40%">Name:</td><td><strong>${escapeHtml(worker.name)}</strong></td></tr>
                        <tr><td class="text-muted">Worker ID:</td><td><code class="small">${worker.id}</code></td></tr>
                        <tr><td class="text-muted">Instance ID:</td><td><code class="small">${worker.aws_instance_id || 'N/A'}</code></td></tr>
                        <tr><td class="text-muted">Region:</td><td><span class="badge bg-secondary">${worker.aws_region}</span></td></tr>
                        <tr><td class="text-muted">Instance Type:</td><td><span class="badge bg-info">${worker.instance_type}</span></td></tr>
                        <tr><td class="text-muted">Status:</td><td><span class="badge ${getStatusBadgeClass(worker.status)}">${worker.status}</span></td></tr>
                        <tr><td class="text-muted">Service Status:</td><td><span class="badge ${getServiceStatusBadgeClass(worker.service_status)}">${worker.service_status}</span></td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Network & CML</h5>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="40%">Public IP:</td><td>${worker.public_ip || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">Private IP:</td><td>${worker.private_ip || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">HTTPS Endpoint:</td><td>${
                            worker.https_endpoint ? `<a href="${worker.https_endpoint}" target="_blank" class="text-decoration-none">${worker.https_endpoint} <i class="bi bi-box-arrow-up-right"></i></a>` : '<span class="text-muted">N/A</span>'
                        }</td></tr>
                        <tr><td class="text-muted">CML Version:</td><td>${worker.cml_version || '<span class="text-muted">N/A</span>'}</td></tr>
                        <tr><td class="text-muted">License Status:</td><td><span class="badge ${getLicenseStatusBadgeClass(worker.license_status)}">${worker.license_status}</span></td></tr>
                        <tr><td class="text-muted">Active Labs:</td><td><strong>${worker.active_labs_count || 0}</strong></td></tr>
                    </table>
                </div>
            </div>
            <div class="row mt-3">
                <div class="col-md-6">
                    <h5 class="border-bottom pb-2 mb-3">Resource Utilization</h5>
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-1">
                            <small class="text-muted">CPU Usage</small>
                            <small><strong>${worker.cpu_utilization != null ? worker.cpu_utilization.toFixed(1) + '%' : 'N/A'}</strong></small>
                        </div>
                        ${
                            worker.cpu_utilization != null
                                ? `
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${getCpuProgressClass(worker.cpu_utilization)}"
                                 style="width: ${worker.cpu_utilization}%">
                            </div>
                        </div>`
                                : '<div class="alert alert-sm alert-secondary py-1">No data available</div>'
                        }
                    </div>
                    <div class="mb-3">
                        <div class="d-flex justify-content-between mb-1">
                            <small class="text-muted">Memory Usage</small>
                            <small><strong>${worker.memory_utilization != null ? worker.memory_utilization.toFixed(1) + '%' : 'N/A'}</strong></small>
                        </div>
                        ${
                            worker.memory_utilization != null
                                ? `
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${getMemoryProgressClass(worker.memory_utilization)}"
                                 style="width: ${worker.memory_utilization}%">
                            </div>
                        </div>`
                                : '<div class="alert alert-sm alert-secondary py-1">No data available</div>'
                        }
                    </div>
                    <div class="text-muted small">
                        <i class="bi bi-clock"></i> Last Activity: ${worker.last_activity_at ? formatDate(worker.last_activity_at) : 'N/A'}
                    </div>
                </div>
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
 * Load metrics tab data
 */
async function loadMetricsTab() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal.dataset.workerId;
    const region = modal.dataset.workerRegion;
    const metricsContent = document.getElementById('worker-details-metrics');

    if (!workerId || !region) {
        metricsContent.innerHTML = '<div class="alert alert-warning">No worker selected</div>';
        return;
    }

    metricsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading metrics...</p></div>';

    try {
        const resources = await workersApi.getWorkerResources(region, workerId, '10m');

        metricsContent.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> Metrics data for the last 10 minutes
            </div>
            <pre class="bg-light p-3 rounded"><code>${JSON.stringify(resources, null, 2)}</code></pre>
        `;
    } catch (error) {
        metricsContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Failed to load metrics: ${error.message}
            </div>
        `;
    }
}

/**
 * Load EC2 tab data
 */
async function loadEC2Tab() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal.dataset.workerId;
    const region = modal.dataset.workerRegion;
    const ec2Content = document.getElementById('worker-details-ec2');

    if (!workerId || !region) {
        ec2Content.innerHTML = '<div class="alert alert-warning">No worker selected</div>';
        return;
    }

    ec2Content.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading EC2 details...</p></div>';

    try {
        const worker = await workersApi.getWorkerDetails(region, workerId);

        ec2Content.innerHTML = `
            <h5 class="border-bottom pb-2 mb-3">EC2 Instance Details</h5>
            <div class="row">
                <div class="col-md-6">
                    <table class="table table-sm">
                        <tr><td class="text-muted" width="40%">Instance ID:</td><td><code>${worker.aws_instance_id || 'N/A'}</code></td></tr>
                        <tr><td class="text-muted">Instance Type:</td><td>${worker.instance_type}</td></tr>
                        <tr><td class="text-muted">Region:</td><td>${worker.aws_region}</td></tr>
                        <tr><td class="text-muted">State:</td><td><span class="badge ${getStatusBadgeClass(worker.status)}">${worker.status}</span></td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <table class="table table-sm">
                        <tr><td class="text-muted" width="40%">Public IP:</td><td>${worker.public_ip || 'N/A'}</td></tr>
                        <tr><td class="text-muted">Private IP:</td><td>${worker.private_ip || 'N/A'}</td></tr>
                        <tr><td class="text-muted">AMI ID:</td><td><code class="small">${worker.ami_id || 'N/A'}</code></td></tr>
                    </table>
                </div>
            </div>
            <div class="alert alert-info mt-3">
                <i class="bi bi-info-circle"></i> Additional EC2 metadata would be displayed here
            </div>
        `;
    } catch (error) {
        ec2Content.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Failed to load EC2 details: ${error.message}
            </div>
        `;
    }
}

/**
 * Load jobs tab data (admin only)
 */
async function loadJobsTab() {
    const jobsContent = document.getElementById('worker-details-jobs');

    jobsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading scheduler jobs...</p></div>';

    // Placeholder for scheduler jobs endpoint
    setTimeout(() => {
        jobsContent.innerHTML = `
            <div class="alert alert-warning">
                <i class="bi bi-tools"></i> Scheduler jobs integration coming soon
            </div>
            <p class="text-muted">This will show APScheduler jobs related to this worker including:</p>
            <ul class="text-muted">
                <li>Monitoring jobs</li>
                <li>Metrics collection jobs</li>
                <li>Health check jobs</li>
                <li>Reconciliation jobs</li>
            </ul>
        `;
    }, 500);
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
    const metricsTab = document.getElementById('metrics-tab');
    const ec2Tab = document.getElementById('ec2-tab');
    const jobsTab = document.getElementById('jobs-tab');
    const eventsTab = document.getElementById('events-tab');

    if (metricsTab) {
        metricsTab.addEventListener('shown.bs.tab', loadMetricsTab);
    }

    if (ec2Tab) {
        ec2Tab.addEventListener('shown.bs.tab', loadEC2Tab);
    }

    if (jobsTab) {
        jobsTab.addEventListener('shown.bs.tab', loadJobsTab);
    }

    if (eventsTab) {
        eventsTab.addEventListener('shown.bs.tab', loadEventsTab);
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
    if (!confirm('Are you sure you want to start this worker?')) return;

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
    if (!confirm('Are you sure you want to stop this worker?')) return;

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
 * Confirm and terminate a worker
 */
async function confirmTerminateWorker(workerId, region, name) {
    if (!confirm(`Are you sure you want to TERMINATE "${name}"? This action cannot be undone!`)) {
        return;
    }

    try {
        await workersApi.terminateWorker(region, workerId);
        showToast('Worker terminated successfully', 'success');
        setTimeout(() => loadWorkers(), 1000);
    } catch (error) {
        console.error('Failed to terminate worker:', error);
        showToast(error.message || 'Failed to terminate worker', 'error');
    }
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Export functions to global scope for onclick handlers
window.workersApp = {
    showWorkerDetails,
    showLicenseModal,
    startWorker,
    stopWorker,
    confirmTerminateWorker,
    refreshWorkers,
};
