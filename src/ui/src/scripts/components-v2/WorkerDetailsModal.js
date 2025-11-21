/**
 * WorkerDetailsModal Component
 *
 * Full-featured modal with horizontal tabs: AWS, CML, Labs, Monitoring, Events
 * Handles license registration, lab operations, and worker details
 *
 * Usage:
 *   <worker-details-modal></worker-details-modal>
 *
 * Open via EventBus:
 *   EventBus.emit('UI_OPEN_WORKER_DETAILS', { workerId: 'abc123', region: 'us-east-1' });
 */

import { BaseComponent } from '../core/BaseComponent.js';
import eventBus, { EventTypes } from '../core/EventBus.js';
import * as bootstrap from 'bootstrap';
import { escapeHtml } from '../components/escape.js';
import { renderWorkerOverview } from '../components/workerOverview.js';
import { isAdmin, isAdminOrManager } from '../utils/roles.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';
import { showToast } from '../ui/notifications.js';
import { showConfirm } from '../components/modals.js';
import { showDeleteModal } from '../ui/worker-modals.js';

export class WorkerDetailsModal extends BaseComponent {
    constructor() {
        super();
        this.modalInstance = null;
        this.currentWorkerId = null;
        this.currentRegion = null;
        this.currentWorker = null;
        this.tabs = {
            aws: null,
            cml: null,
            labs: null,
            monitoring: null,
            events: null,
        };
    }

    onMount() {
        // Subscribe to open modal event
        this.subscribe('UI_OPEN_WORKER_DETAILS', ({ workerId, region }) => {
            this.openModal(workerId, region);
        });

        // Subscribe to worker updates
        this.subscribe(EventTypes.WORKER_SNAPSHOT, data => {
            if (data.worker_id === this.currentWorkerId) {
                this.currentWorker = data;
                this.refreshCurrentTab();
            }
        });

        this.subscribe(EventTypes.WORKER_DELETED, data => {
            if (data.worker_id === this.currentWorkerId) {
                this.closeModal();
                showToast('Worker has been deleted', 'info');
            }
        });

        this.render();
    }

    render() {
        this.innerHTML = `
            <div class="modal fade" id="workerDetailsModalV2" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="bi bi-info-circle"></i> Worker Details
                            </h5>
                            <div class="d-flex align-items-center gap-3 ms-auto">
                                <small class="text-muted" id="metrics-last-refreshed">
                                    <i class="bi bi-clock-history"></i> <span class="last-refreshed-time">--</span>
                                </small>
                                <small class="text-muted" id="metrics-refresh-timer">
                                    <i class="bi bi-arrow-clockwise"></i> <span id="metrics-countdown">--:--</span>
                                </small>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                        </div>
                        <div class="modal-body">
                            <!-- Navigation Tabs -->
                            <ul class="nav nav-tabs mb-3" id="workerDetailsTabs" role="tablist">
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link active" id="aws-tab-btn" data-tab="aws" type="button">
                                        <i class="bi bi-hdd-stack"></i> AWS
                                    </button>
                                </li>
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link" id="cml-tab-btn" data-tab="cml" type="button">
                                        <i class="bi bi-diagram-3"></i> CML
                                    </button>
                                </li>
                                <li class="nav-item" role="presentation">
                                    <button class="nav-link" id="labs-tab-btn" data-tab="labs" type="button">
                                        <i class="bi bi-folder2-open"></i> Labs
                                    </button>
                                </li>
                                <li class="nav-item admin-manager-only-tab" role="presentation" style="display: none;">
                                    <button class="nav-link" id="monitoring-tab-btn" data-tab="monitoring" type="button">
                                        <i class="bi bi-activity"></i> Monitoring
                                    </button>
                                </li>
                                <li class="nav-item admin-only-tab" role="presentation" style="display: none;">
                                    <button class="nav-link" id="events-tab-btn" data-tab="events" type="button">
                                        <i class="bi bi-bell"></i> Events
                                    </button>
                                </li>
                            </ul>

                            <!-- Tab Content -->
                            <div class="tab-content" id="workerDetailsTabContent">
                                <!-- AWS Tab -->
                                <div class="tab-pane fade show active" id="aws-panel" role="tabpanel">
                                    <div id="worker-details-aws">
                                        <div class="text-center py-5">
                                            <div class="spinner-border" role="status"></div>
                                            <p class="mt-3 text-muted">Loading worker details...</p>
                                        </div>
                                    </div>
                                </div>

                                <!-- CML Tab -->
                                <div class="tab-pane fade" id="cml-panel" role="tabpanel">
                                    <div id="worker-details-cml">
                                        <div class="text-center py-5 text-muted">
                                            <i class="bi bi-diagram-3 fs-1 d-block mb-3"></i>
                                            <p>CML application details will appear here</p>
                                        </div>
                                    </div>
                                </div>

                                <!-- Labs Tab -->
                                <div class="tab-pane fade" id="labs-panel" role="tabpanel">
                                    <div id="worker-details-labs">
                                        <div class="text-center py-5 text-muted">
                                            <i class="bi bi-folder2-open fs-1 d-block mb-3"></i>
                                            <p>Lab details will appear here</p>
                                        </div>
                                    </div>
                                </div>

                                <!-- Monitoring Tab -->
                                <div class="tab-pane fade" id="monitoring-panel" role="tabpanel">
                                    <div id="worker-details-monitoring">
                                        <div class="text-center py-5 text-muted">
                                            <i class="bi bi-activity fs-1 d-block mb-3"></i>
                                            <p>Worker monitoring status will appear here</p>
                                        </div>
                                    </div>
                                </div>

                                <!-- Events Tab -->
                                <div class="tab-pane fade" id="events-panel" role="tabpanel">
                                    <div id="worker-details-events">
                                        <div class="text-center py-5 text-muted">
                                            <i class="bi bi-bell fs-1 d-block mb-3"></i>
                                            <p>Events will appear here</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <div class="me-auto d-flex gap-2">
                                <button type="button" class="btn btn-danger admin-only" id="delete-worker-from-details-btn"
                                    style="display: none;" title="Delete Worker">
                                    <i class="bi bi-trash"></i> Delete Worker
                                </button>
                                <button type="button" class="btn btn-warning admin-only" id="stop-worker-btn"
                                    style="display: none;" title="Stop Worker">
                                    <i class="bi bi-stop-fill"></i> Stop Worker
                                </button>
                                <button type="button" class="btn btn-success admin-only" id="start-worker-btn"
                                    style="display: none;" title="Start Worker">
                                    <i class="bi bi-play-fill"></i> Start Worker
                                </button>
                                <input type="file" id="lab-upload-input" accept=".yaml,.yml" style="display: none;">
                                <button type="button" class="btn btn-primary" id="upload-lab-btn" style="display: none;">
                                    <i class="bi bi-upload"></i> Import Lab
                                </button>
                            </div>
                            <button type="button" class="btn btn-primary" id="refresh-worker-details">
                                <i class="bi bi-arrow-clockwise"></i> Refresh
                            </button>
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.setupEventListeners();
    }

    setupEventListeners() {
        const modalEl = this.$('#workerDetailsModalV2');
        if (!modalEl) return;

        // Initialize Bootstrap modal
        this.modalInstance = new bootstrap.Modal(modalEl);

        // Tab click handlers
        this.$$('[data-tab]').forEach(btn => {
            btn.addEventListener('click', e => {
                e.preventDefault();
                const tab = btn.dataset.tab;
                this.switchTab(tab);
            });
        });

        // Refresh button
        const refreshBtn = this.$('#refresh-worker-details');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshWorkerData());
        }

        // Delete button
        const deleteBtn = this.$('#delete-worker-from-details-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.handleDeleteWorker());
        }

        // Start button
        const startBtn = this.$('#start-worker-btn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.handleStartWorker());
        }

        // Stop button
        const stopBtn = this.$('#stop-worker-btn');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => this.handleStopWorker());
        }

        // Import Lab button
        const uploadBtn = this.$('#upload-lab-btn');
        const uploadInput = this.$('#lab-upload-input');
        if (uploadBtn && uploadInput) {
            uploadBtn.addEventListener('click', () => uploadInput.click());
            uploadInput.addEventListener('change', e => this.handleLabFileSelected(e));
        }

        // Modal lifecycle events
        modalEl.addEventListener('hidden.bs.modal', () => {
            this.currentWorkerId = null;
            this.currentRegion = null;
            this.currentWorker = null;
        });
    }

    async openModal(workerId, region) {
        console.log('[WorkerDetailsModal] Opening for worker:', workerId, region);

        this.currentWorkerId = workerId;
        this.currentRegion = region;

        // Show modal
        if (this.modalInstance) {
            this.modalInstance.show();
        }

        // Apply RBAC visibility
        this.applyRBAC();

        // Load worker data first, then switch to AWS tab
        await this.loadWorkerData();
        this.switchTab('aws');
    }

    closeModal() {
        if (this.modalInstance) {
            this.modalInstance.hide();
        }
    }

    applyRBAC() {
        const modalEl = this.$('#workerDetailsModalV2');
        if (!modalEl) return;

        const adminTabs = modalEl.querySelectorAll('.admin-only-tab');
        const adminManagerTabs = modalEl.querySelectorAll('.admin-manager-only-tab');
        const adminButtons = modalEl.querySelectorAll('.admin-only');

        if (isAdmin()) {
            adminTabs.forEach(t => (t.style.display = 'block'));
            adminManagerTabs.forEach(t => (t.style.display = 'block'));
            adminButtons.forEach(b => (b.style.display = ''));
        } else if (isAdminOrManager()) {
            adminManagerTabs.forEach(t => (t.style.display = 'block'));
            adminTabs.forEach(t => (t.style.display = 'none'));
            adminButtons.forEach(b => (b.style.display = 'none'));
        } else {
            adminTabs.forEach(t => (t.style.display = 'none'));
            adminManagerTabs.forEach(t => (t.style.display = 'none'));
            adminButtons.forEach(b => (b.style.display = 'none'));
        }
    }

    switchTab(tabName) {
        // Update tab buttons
        this.$$('[data-tab]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Update tab panels
        this.$('#aws-panel')?.classList.toggle('show', tabName === 'aws');
        this.$('#aws-panel')?.classList.toggle('active', tabName === 'aws');
        this.$('#cml-panel')?.classList.toggle('show', tabName === 'cml');
        this.$('#cml-panel')?.classList.toggle('active', tabName === 'cml');
        this.$('#labs-panel')?.classList.toggle('show', tabName === 'labs');
        this.$('#labs-panel')?.classList.toggle('active', tabName === 'labs');
        this.$('#monitoring-panel')?.classList.toggle('show', tabName === 'monitoring');
        this.$('#monitoring-panel')?.classList.toggle('active', tabName === 'monitoring');
        this.$('#events-panel')?.classList.toggle('show', tabName === 'events');
        this.$('#events-panel')?.classList.toggle('active', tabName === 'events');

        // Load tab content
        this.loadTabContent(tabName);
        this.updateFooterButtons();
    }

    async loadWorkerData() {
        if (!this.currentWorkerId || !this.currentRegion) return;

        const maxRetries = 3;
        let attempt = 0;

        while (attempt < maxRetries) {
            try {
                const { getWorkerDetails } = await import('../api/workers.js');
                this.currentWorker = await getWorkerDetails(this.currentRegion, this.currentWorkerId);
                this.refreshCurrentTab();
                return; // Success, exit
            } catch (error) {
                attempt++;
                console.error(`[WorkerDetailsModal] Failed to load worker (attempt ${attempt}/${maxRetries}):`, error);

                if (attempt >= maxRetries) {
                    showToast(`Failed to load worker after ${maxRetries} attempts: ${error.message}`, 'error');
                } else {
                    // Wait before retry (exponential backoff)
                    await new Promise(resolve => setTimeout(resolve, 500 * attempt));
                }
            }
        }
    }

    async refreshWorkerData() {
        await this.loadWorkerData();
        showToast('Worker data refreshed', 'success');
    }

    refreshCurrentTab() {
        this.updateModalHeader();
        this.updateFooterButtons();
        const activeTab = this.$('[data-tab].active');
        if (activeTab) {
            this.loadTabContent(activeTab.dataset.tab);
        }
    }

    updateFooterButtons() {
        if (!this.currentWorker) return;
        const w = this.currentWorker;
        const isAdminUser = isAdmin();
        const activeTab = this.$('[data-tab].active')?.dataset.tab;

        const startBtn = this.$('#start-worker-btn');
        const stopBtn = this.$('#stop-worker-btn');
        const deleteBtn = this.$('#delete-worker-from-details-btn');
        const importLabBtn = this.$('#upload-lab-btn');

        if (startBtn) startBtn.style.display = isAdminUser && w.status === 'stopped' ? '' : 'none';
        if (stopBtn) stopBtn.style.display = isAdminUser && w.status === 'running' ? '' : 'none';
        if (deleteBtn) deleteBtn.style.display = isAdminUser ? '' : 'none';

        // Show import button only on Labs tab
        if (importLabBtn) importLabBtn.style.display = activeTab === 'labs' ? '' : 'none';
    }

    updateModalHeader() {
        const titleEl = this.$('.modal-title');
        if (titleEl && this.currentWorker) {
            const httpsEndpoint = this.currentWorker.https_endpoint;
            const name = escapeHtml(this.currentWorker.name || 'Unknown Worker');

            if (httpsEndpoint) {
                titleEl.innerHTML = `<i class="bi bi-info-circle"></i> <a href="${httpsEndpoint}" target="_blank" class="text-decoration-none text-reset" title="Open Worker in new tab">${name} <i class="bi bi-box-arrow-up-right small ms-1" style="font-size: 0.7em;"></i></a>`;
            } else {
                titleEl.innerHTML = `<i class="bi bi-info-circle"></i> ${name}`;
            }
        }
    }

    async loadTabContent(tabName) {
        switch (tabName) {
            case 'aws':
                await this.loadAWSTab();
                break;
            case 'cml':
                await this.loadCMLTab();
                break;
            case 'labs':
                await this.loadLabsTab();
                break;
            case 'monitoring':
                await this.loadMonitoringTab();
                break;
            case 'events':
                await this.loadEventsTab();
                break;
        }
    }

    async loadAWSTab() {
        const container = this.$('#worker-details-aws');
        if (!container || !this.currentWorker) return;

        try {
            container.innerHTML = renderWorkerOverview(this.currentWorker);
            // Initialize tooltips for timestamp icons
            setTimeout(() => initializeDateTooltips(), 100);
        } catch (error) {
            console.error('[WorkerDetailsModal] Failed to render AWS tab:', error);
            container.innerHTML = `<div class="alert alert-danger">Failed to load AWS details: ${escapeHtml(error.message)}</div>`;
        }
    }

    async loadCMLTab() {
        const container = this.$('#worker-details-cml');
        if (!container || !this.currentWorker) return;

        const w = this.currentWorker;
        const sysInfo = w.system_info || {};
        const sysStats = w.system_stats || {};
        // Handle both API field names (cml_*) and potential legacy/mapped names
        const license = w.cml_license_info || w.license_info || {};
        const health = w.cml_system_health || w.system_health || {};

        // Compute nodes are in system health
        const computesDict = health.computes || {};
        // Convert dict to array, adding ID/name from key if needed
        const compute = Object.entries(computesDict).map(([key, val]) => ({
            name: key, // Key is usually hostname or ID
            ...val,
        }));

        // Helper for badges
        const renderBadge = (condition, trueText = 'Yes', falseText = 'No') => {
            return `<span class="badge bg-${condition ? 'success' : 'danger'}"><i class="bi bi-${condition ? 'check-circle' : 'x-circle'}"></i> ${condition ? trueText : falseText}</span>`;
        };

        const renderCheck = condition => {
            return `<span class="text-${condition ? 'success' : 'danger'}"><i class="bi bi-${condition ? 'check-circle-fill' : 'x-circle-fill'}"></i> ${condition ? 'Yes' : 'No'}</span>`;
        };

        // Helper for progress bars with details
        const renderProgressWithDetails = (val, label, details = []) => {
            const v = parseFloat(val) || 0;
            let color = 'success';
            if (v > 70) color = 'warning';
            if (v > 90) color = 'danger';

            const detailsHtml = details
                .map(
                    d => `
                <div class="d-flex justify-content-between small text-muted mt-1">
                    <span>${d.label}</span>
                    <span class="fw-bold">${d.value}</span>
                </div>
            `
                )
                .join('');

            return `
                <div class="col-md-4">
                    <div class="mb-2">
                        <div class="d-flex justify-content-between small mb-1">
                            <span class="fw-bold"><i class="bi bi-${label === 'CPU' ? 'cpu' : label === 'Memory' ? 'memory' : 'hdd'}"></i> ${label}</span>
                            <span class="fw-bold">${v}%</span>
                        </div>
                        <div class="progress" style="height: 8px;">
                            <div class="progress-bar bg-${color}" role="progressbar" style="width: ${v}%" aria-valuenow="${v}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                        <div class="mt-2 border-top pt-2">
                            ${detailsHtml}
                        </div>
                    </div>
                </div>
            `;
        };

        try {
            container.innerHTML = `
            <div class="row g-3">
                <!-- System Information -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-info-circle"></i> System Information</h6>
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr><td class="text-muted">Version:</td><td><strong>${escapeHtml(w.cml_version || 'N/A')}</strong></td></tr>
                                <tr><td class="text-muted">Ready State:</td><td>${renderBadge(w.cml_ready, 'READY', 'NOT READY')}</td></tr>
                                <tr><td class="text-muted">Uptime:</td><td>${sysStats.uptime || 'Unknown'}</td></tr>
                                <tr><td class="text-muted">Active Nodes:</td><td><strong>${sysStats.active_nodes || 0}</strong> / ${sysStats.total_nodes || '?'}</td></tr>
                                <tr><td class="text-muted">Last Synced:</td><td>${w.last_synced_at ? formatDateWithRelative(w.last_synced_at) : 'N/A'} <i class="bi bi-info-circle text-muted" title="Last time data was synced from CML"></i></td></tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- License & Edition -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="bi bi-key"></i> License & Edition</h6>
                            <button class="btn btn-sm btn-outline-primary py-0" id="btn-license-details">Details</button>
                        </div>
                        <div class="card-body">
                            <table class="table table-sm table-borderless mb-0">
                                <tr><td class="text-muted">Licensed:</td><td>${renderBadge(w.license_status === 'registered' || w.cml_license_info?.registration_status === 'COMPLETED', 'YES', 'NO')}</td></tr>
                                <tr><td class="text-muted">Edition:</td><td><span class="badge bg-primary">${escapeHtml(license.product_name || license.active_license || 'UNKNOWN')}</span></td></tr>
                                <tr><td class="text-muted">Smart Account:</td><td><strong>${escapeHtml(license.smart_account || 'N/A')}</strong></td></tr>
                                <tr><td class="text-muted">Virtual Account:</td><td><strong>${escapeHtml(license.virtual_account || 'N/A')}</strong></td></tr>
                                <tr><td class="text-muted">Reg. Expires:</td><td>${license.registration_expires || 'N/A'}</td></tr>
                                <tr><td class="text-muted">Auth Status:</td><td>${license.authorization_status || 'N/A'}</td></tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- System Health -->
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-heart-pulse"></i> System Health</h6>
                        </div>
                        <div class="card-body">
                             <table class="table table-sm table-borderless mb-0">
                                <tr><td class="text-muted">Overall Status:</td><td>${renderBadge(health.valid !== false, 'VALID', 'INVALID')}</td></tr>
                                <tr><td class="text-muted">Service Status:</td><td><span class="badge bg-${w.service_status === 'available' ? 'success' : 'warning'}">${w.service_status}</span></td></tr>
                                <tr><td class="text-muted">HTTPS Endpoint:</td><td>${w.https_endpoint ? `<a href="${escapeHtml(w.https_endpoint)}" target="_blank" class="text-decoration-none">${escapeHtml(w.https_endpoint)}</a>` : 'N/A'}</td></tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Controller Status -->
                <div class="col-md-12">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-cpu"></i> Controller Status</h6>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-3">
                                    <div class="d-flex justify-content-between">
                                        <span class="text-muted">Status:</span>
                                        ${renderBadge(health.controller?.valid !== false, 'VALID', 'INVALID')}
                                    </div>
                                </div>
                                <div class="col-md-3">
                                    <div class="d-flex justify-content-between">
                                        <span class="text-muted">Core Connected:</span>
                                        ${renderCheck(health.controller?.is_connected !== false)}
                                    </div>
                                </div>
                                <div class="col-md-3">
                                    <div class="d-flex justify-content-between">
                                        <span class="text-muted">Nodes Loaded:</span>
                                        ${renderCheck(health.controller?.has_nodes !== false)}
                                    </div>
                                </div>
                                <div class="col-md-3">
                                    <div class="d-flex justify-content-between">
                                        <span class="text-muted">Images Loaded:</span>
                                        ${renderCheck(health.controller?.has_images !== false)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Resource Utilization -->
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-speedometer2"></i> Resource Utilization</h6>
                        </div>
                        <div class="card-body">
                            <div class="row g-4">
                                ${renderProgressWithDetails(w.cpu_utilization, 'CPU', [
                                    { label: 'Total Cores', value: sysInfo.cpu_cores || '-' },
                                    { label: 'Allocated vCPUs', value: sysStats.allocated_vcpus || '-' },
                                ])}
                                ${renderProgressWithDetails(w.memory_utilization, 'Memory', [
                                    { label: 'Total', value: sysInfo.memory_total || '-' },
                                    { label: 'Used', value: sysStats.memory_used || '-' },
                                    { label: 'Free', value: sysStats.memory_free || '-' },
                                    { label: 'VM Allocated', value: sysStats.vm_allocated_memory || '-' },
                                ])}
                                ${renderProgressWithDetails(w.disk_utilization || w.storage_utilization, 'Disk', [
                                    { label: 'Total', value: sysInfo.disk_total || '-' },
                                    { label: 'Used', value: sysStats.disk_used || '-' },
                                    { label: 'Free', value: sysStats.disk_free || '-' },
                                ])}
                            </div>

                            <!-- Virtual Nodes Summary -->
                            <div class="mt-4 pt-3 border-top">
                                <h6 class="small text-muted mb-3"><i class="bi bi-diagram-2"></i> Virtual Nodes Summary</h6>
                                <div class="row text-center">
                                    <div class="col-3">
                                        <h3 class="text-success mb-0">${sysStats.running_nodes || 0}</h3>
                                        <small class="text-muted">Running</small>
                                    </div>
                                    <div class="col-3">
                                        <h3 class="text-primary mb-0">${sysStats.total_nodes || 0}</h3>
                                        <small class="text-muted">Total</small>
                                    </div>
                                    <div class="col-3">
                                        <h3 class="text-info mb-0">${sysStats.total_vcpus || 0}</h3>
                                        <small class="text-muted">vCPUs</small>
                                    </div>
                                    <div class="col-3">
                                        <h3 class="text-info mb-0">${sysStats.total_ram || 0} GB</h3>
                                        <small class="text-muted">RAM</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Compute Node Health -->
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-light">
                            <h6 class="mb-0"><i class="bi bi-server"></i> Compute Node Health</h6>
                        </div>
                        <div class="card-body">
                            ${
                                compute.length
                                    ? compute
                                          .map(
                                              node => `
                                <div class="row align-items-center mb-3 pb-3 border-bottom last-no-border">
                                    <div class="col-md-4">
                                        <div class="d-flex align-items-center mb-2">
                                            <span class="fw-bold me-2">Hostname</span>
                                            <span>${escapeHtml(node.name)}</span>
                                            <span class="badge bg-primary ms-2">CONTROLLER</span>
                                        </div>
                                        <div class="d-flex align-items-center mb-2">
                                            <span class="text-muted me-2">Admission State</span>
                                            <span class="badge bg-${node.status === 'ready' ? 'success' : 'secondary'}">${(node.status || 'UNKNOWN').toUpperCase()}</span>
                                        </div>
                                        <div class="d-flex align-items-center">
                                            <span class="text-muted me-2">Overall Valid</span>
                                            ${renderCheck(node.valid !== false)}
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-muted">KVM/VMX</span>
                                            ${renderCheck(node.has_kvm !== false)}
                                        </div>
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-muted">Libvirt</span>
                                            ${renderCheck(node.has_libvirt !== false)}
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-muted">LLD Connected</span>
                                            <span>${renderCheck(node.is_connected !== false)} <small class="text-muted">(Synced)</small></span>
                                        </div>
                                        <div class="d-flex justify-content-between mb-2">
                                            <span class="text-muted">Refplat Images</span>
                                            ${renderCheck(node.has_refplat !== false)}
                                        </div>
                                    </div>
                                </div>
                            `
                                          )
                                          .join('')
                                    : '<div class="text-center text-muted py-3">No compute nodes found</div>'
                            }
                        </div>
                    </div>
                </div>
            </div>
            `;

            // Bind license buttons
            this.$('#btn-license-details')?.addEventListener('click', () => showToast('License details modal not implemented', 'info'));
            this.$('#btn-manage-license')?.addEventListener('click', () => showToast('Manage license modal not implemented', 'info'));
        } catch (error) {
            console.error('[WorkerDetailsModal] Failed to render CML tab:', error);
            container.innerHTML = `<div class="alert alert-danger">Failed to load CML details: ${escapeHtml(error.message)}</div>`;
        }
    }

    async loadLabsTab() {
        const container = this.$('#worker-details-labs');
        if (!container) return;

        try {
            const { getWorkerLabs } = await import('../api/workers.js');
            const labs = await getWorkerLabs(this.currentRegion, this.currentWorkerId);

            if (!labs || labs.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-5 text-muted">
                        <i class="bi bi-folder2-open fs-1 d-block mb-3"></i>
                        <p>No labs found on this worker</p>
                    </div>
                `;
                this.bindLabsTabActions();
                return;
            }

            container.innerHTML = `
                <div class="accordion" id="labsAccordion">
                    ${labs
                        .map((lab, index) => {
                            const id = `lab-${index}`;
                            const state = lab.state || 'UNKNOWN';
                            const isStarted = state === 'STARTED';

                            return `
                            <div class="accordion-item">
                                <h2 class="accordion-header" id="heading-${id}">
                                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${id}" aria-expanded="false" aria-controls="collapse-${id}">
                                        <div class="d-flex align-items-center w-100 me-3">
                                            <span class="fw-bold me-3">${escapeHtml(lab.title)}</span>
                                            <span class="badge ${this.getLabStateBadgeClass(state)} me-auto">${state}</span>
                                            <span class="small text-muted me-3"><i class="bi bi-pc-display"></i> ${lab.node_count || 0} Nodes</span>
                                            <span class="small text-muted"><i class="bi bi-link"></i> ${lab.link_count || 0} Links</span>
                                        </div>
                                    </button>
                                </h2>
                                <div id="collapse-${id}" class="accordion-collapse collapse" aria-labelledby="heading-${id}" data-bs-parent="#labsAccordion">
                                    <div class="accordion-body">
                                        <div class="row g-3">
                                            <div class="col-md-6">
                                                <h6 class="border-bottom pb-2">Lab Information</h6>
                                                <table class="table table-sm table-borderless mb-3">
                                                    <tr><td class="text-muted" width="30%">ID:</td><td><code>${lab.id}</code></td></tr>
                                                    <tr><td class="text-muted">Owner:</td><td>${escapeHtml(lab.owner || 'Unknown')}</td></tr>
                                                    <tr><td class="text-muted">Created:</td><td>${formatDateWithRelative(lab.created)}</td></tr>
                                                </table>
                                            </div>
                                            <div class="col-md-6">
                                                <h6 class="border-bottom pb-2">Actions</h6>
                                                <div class="d-flex gap-2 flex-wrap">
                                                    <button class="btn btn-sm btn-success lab-action" data-action="start" data-lab-id="${lab.id}" ${isStarted ? 'disabled' : ''}><i class="bi bi-play-fill"></i> Start</button>
                                                    <button class="btn btn-sm btn-warning lab-action" data-action="stop" data-lab-id="${lab.id}" ${!isStarted ? 'disabled' : ''}><i class="bi bi-stop-fill"></i> Stop</button>
                                                    <button class="btn btn-sm btn-danger lab-action" data-action="wipe" data-lab-id="${lab.id}"><i class="bi bi-eraser"></i> Wipe</button>
                                                    <button class="btn btn-sm btn-outline-primary lab-action" data-action="export" data-lab-id="${lab.id}"><i class="bi bi-download"></i> Download</button>
                                                    <button class="btn btn-sm btn-outline-danger lab-action" data-action="delete" data-lab-id="${lab.id}"><i class="bi bi-trash"></i> Delete</button>
                                                </div>
                                            </div>
                                            <div class="col-12">
                                                <h6 class="border-bottom pb-2">Description</h6>
                                                <div class="bg-light p-2 rounded small">${escapeHtml(lab.description || 'No description')}</div>
                                            </div>
                                            <div class="col-12">
                                                <h6 class="border-bottom pb-2">Notes</h6>
                                                <div class="bg-light p-2 rounded small">${escapeHtml(lab.notes || 'No notes')}</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                        })
                        .join('')}
                </div>
            `;

            this.bindLabsTabActions();
            // Initialize tooltips for timestamp icons
            setTimeout(() => initializeDateTooltips(), 100);
        } catch (error) {
            console.error('[WorkerDetailsModal] Failed to load labs:', error);
            container.innerHTML = `<div class="alert alert-danger">Failed to load labs: ${escapeHtml(error.message)}</div>`;
        }
    }

    getLabStateBadgeClass(state) {
        switch (state?.toLowerCase()) {
            case 'started':
                return 'bg-success';
            case 'stopped':
                return 'bg-secondary';
            case 'booted':
                return 'bg-info';
            default:
                return 'bg-warning';
        }
    }

    bindLabsTabActions() {
        this.$$('.lab-action').forEach(btn => {
            btn.addEventListener('click', async e => {
                const action = btn.dataset.action;
                const labId = btn.dataset.labId;
                await this.handleLabAction(action, labId);
            });
        });
    }

    async handleLabFileSelected(event) {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const { importLab } = await import('../api/workers.js');

            await importLab(this.currentRegion, this.currentWorkerId, file);
            showToast('Lab imported successfully', 'success');
            this.loadLabsTab(); // Refresh labs list
        } catch (error) {
            console.error('[WorkerDetailsModal] Failed to import lab:', error);
            showToast(`Failed to import lab: ${error.message}`, 'error');
        }
    }

    async handleLabAction(action, labId) {
        try {
            const { startLab, stopLab, wipeLab, deleteLab, downloadLab } = await import('../api/workers.js');

            switch (action) {
                case 'start':
                    await startLab(this.currentRegion, this.currentWorkerId, labId);
                    showToast('Lab started', 'success');
                    break;
                case 'stop':
                    await stopLab(this.currentRegion, this.currentWorkerId, labId);
                    showToast('Lab stopped', 'success');
                    break;
                case 'wipe':
                    const confirmWipe = await showConfirm('Wipe Lab', 'This will reset the lab to initial state. Continue?', () => {});
                    if (confirmWipe) {
                        await wipeLab(this.currentRegion, this.currentWorkerId, labId);
                        showToast('Lab wiped', 'success');
                    }
                    break;
                case 'delete':
                    const confirmDelete = await showConfirm('Delete Lab', 'This will permanently delete the lab. Continue?', () => {});
                    if (confirmDelete) {
                        await deleteLab(this.currentRegion, this.currentWorkerId, labId);
                        showToast('Lab deleted', 'success');
                    }
                    break;
                case 'export':
                    const { downloadLab } = await import('../api/workers.js');
                    const labData = await downloadLab(this.currentRegion, this.currentWorkerId, labId);
                    const blob = new Blob([labData], { type: 'application/x-yaml' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `lab-${labId}.yaml`;
                    a.click();
                    URL.revokeObjectURL(url);
                    showToast('Lab exported', 'success');
                    break;
            }

            // Refresh labs list after action
            if (action !== 'export') {
                this.loadLabsTab();
            }
        } catch (error) {
            console.error(`[WorkerDetailsModal] Failed to ${action} lab:`, error);
            showToast(`Failed to ${action} lab: ${error.message}`, 'error');
        }
    }

    async loadMonitoringTab() {
        const container = this.$('#worker-details-monitoring');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-activity fs-1 d-block mb-3"></i>
                <p>Monitoring tab - integration with legacy code pending</p>
            </div>
        `;
    }

    async loadEventsTab() {
        const container = this.$('#worker-details-events');
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-bell fs-1 d-block mb-3"></i>
                <p>Events tab - integration with legacy code pending</p>
            </div>
        `;
    }

    async handleStartWorker() {
        const confirmed = await showConfirm('Start Worker', `Start worker ${this.currentWorker?.name || this.currentWorkerId}?`, () => {});

        if (confirmed) {
            try {
                const { startWorker } = await import('../api/workers.js');
                await startWorker(this.currentRegion, this.currentWorkerId);
                showToast('Worker start initiated', 'success');
            } catch (error) {
                console.error('[WorkerDetailsModal] Failed to start worker:', error);
                showToast(`Failed to start worker: ${error.message}`, 'error');
            }
        }
    }

    async handleStopWorker() {
        const confirmed = await showConfirm('Stop Worker', `Stop worker ${this.currentWorker?.name || this.currentWorkerId}?`, () => {});

        if (confirmed) {
            try {
                const { stopWorker } = await import('../api/workers.js');
                await stopWorker(this.currentRegion, this.currentWorkerId);
                showToast('Worker stop initiated', 'success');
            } catch (error) {
                console.error('[WorkerDetailsModal] Failed to stop worker:', error);
                showToast(`Failed to stop worker: ${error.message}`, 'error');
            }
        }
    }

    async handleDeleteWorker() {
        // Use the shared delete modal which supports optional EC2 termination
        showDeleteModal(this.currentWorkerId, this.currentRegion, this.currentWorker?.name || this.currentWorkerId);

        // Close details modal so the delete modal is visible
        this.closeModal();
    }

    async handleDeregisterLicense() {
        const confirmed = await showConfirm('Deregister License', `Remove license from worker ${this.currentWorker?.name || this.currentWorkerId}?`, () => {});

        if (confirmed) {
            try {
                const { deregisterLicense } = await import('../api/workers.js');
                await deregisterLicense(this.currentRegion, this.currentWorkerId);
                showToast('License deregistration initiated', 'success');
                this.loadCMLTab(); // Refresh CML tab
            } catch (error) {
                console.error('[WorkerDetailsModal] Failed to deregister license:', error);
                showToast(`Failed to deregister license: ${error.message}`, 'error');
            }
        }
    }
}

// Register custom element
customElements.define('worker-details-modal', WorkerDetailsModal);
