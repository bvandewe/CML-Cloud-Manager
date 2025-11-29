/**
 * WorkerList Component
 *
 * Manages a collection of worker cards with filtering, sorting, and real-time updates.
 * Replaces the renderWorkersTable() and renderWorkersCards() functions.
 *
 * Usage:
 *   <worker-list region="us-east-1" view="cards"></worker-list>
 *   <worker-list region="us-east-1" view="table"></worker-list>
 */

import { BaseComponent } from '../core/BaseComponent.js';
import eventBus, { EventTypes } from '../core/EventBus.js';
import './WorkerCard.js';
import * as bootstrap from 'bootstrap';

export class WorkerList extends BaseComponent {
    static get observedAttributes() {
        return ['region', 'view', 'filter-status', 'search', 'include-terminated'];
    }

    constructor() {
        super();
        this.workers = new Map(); // workerId -> worker data
        this.renderTimeout = null; // For debouncing renders
        this.isLoadingWorkers = false; // Prevent duplicate loads
        this.sseEnabled = false; // Track if SSE updates are enabled
    }

    onMount() {
        console.log('[WorkerList] Mounting component');

        // Load initial workers first, then enable SSE
        this.loadWorkers();
    }

    /**
     * Enable SSE updates after initial load is complete
     * This prevents race conditions between API and SSE during startup
     */
    enableSSEUpdates() {
        if (this.sseEnabled) {
            console.log('[WorkerList] SSE updates already enabled');
            return;
        }

        console.log('[WorkerList] Enabling SSE updates');
        this.sseEnabled = true;

        // Subscribe to worker events for real-time updates
        this.subscribe(EventTypes.WORKER_CREATED, data => {
            console.log('[WorkerList] Worker created:', data);
            this.addWorker(data);
        });

        this.subscribe(EventTypes.WORKER_IMPORTED, data => {
            console.log('[WorkerList] Worker imported:', data);
            this.addWorker(data);
        });

        this.subscribe(EventTypes.WORKER_SNAPSHOT, data => {
            console.log('[WorkerList] Worker snapshot:', data);
            this.updateWorker(data);
        });

        this.subscribe(EventTypes.WORKER_DELETED, data => {
            console.log('[WorkerList] Worker deleted:', data);
            this.removeWorker(data.worker_id);
        });

        this.subscribe(EventTypes.WORKER_STATUS_CHANGED, data => {
            console.log('[WorkerList] Status changed:', data);
            this.updateWorkerStatus(data);
        });

        this.subscribe(EventTypes.WORKER_IDLE_DETECTION_TOGGLED, data => {
            console.log('[WorkerList] Idle detection toggled:', data);
            const worker = this.workers.get(data.worker_id);
            if (worker) {
                worker.is_idle_detection_enabled = data.is_enabled;
                this.updateWorker(worker);
            }
        });
    }

    async loadWorkers() {
        // Prevent duplicate loads
        if (this.isLoadingWorkers) {
            console.log('[WorkerList] Already loading workers, skipping...');
            return;
        }

        this.isLoadingWorkers = true;
        console.log('[WorkerList] Loading workers...');
        const region = this.getAttr('region', 'us-east-1');
        const includeTerminated = this.getAttr('include-terminated') === 'true';

        try {
            // Import API dynamically to avoid circular dependencies
            const { listWorkers } = await import('../api/workers.js');
            const workers = await listWorkers(region, null, includeTerminated);

            console.log(`[WorkerList] Loaded ${workers.length} workers`);

            // Clear and populate - no SSE interference during initial load
            this.workers.clear();
            workers.forEach(worker => {
                this.workers.set(worker.id, this.normalizeWorker(worker));
            });

            this.render();

            // Enable SSE updates after initial render is complete
            this.enableSSEUpdates();
        } catch (error) {
            console.error('[WorkerList] Failed to load workers:', error);
            this.renderError(error.message);
        } finally {
            this.isLoadingWorkers = false;
        }
    }

    normalizeWorker(worker) {
        return {
            id: worker.id || worker.worker_id,
            name: worker.name,
            aws_region: worker.aws_region || worker.region,
            status: worker.status,
            service_status: worker.service_status,
            instance_type: worker.instance_type,
            aws_instance_id: worker.aws_instance_id,
            public_ip: worker.public_ip,
            private_ip: worker.private_ip,
            https_endpoint: worker.https_endpoint,
            license_status: worker.license_status,
            cml_license_info: worker.cml_license_info,
            cml_version: worker.cml_version,
            cml_ready: worker.cml_ready,
            cml_labs_count: worker.cml_labs_count,
            cml_system_info: worker.cml_system_info,
            is_idle_detection_enabled: worker.is_idle_detection_enabled,
            // Prefer calculated/CML metrics (cpu_utilization), fallback to CloudWatch
            cpu_utilization: worker.cpu_utilization ?? worker.cloudwatch_cpu_utilization,
            memory_utilization: worker.memory_utilization ?? worker.cloudwatch_memory_utilization,
            disk_utilization: worker.disk_utilization ?? worker.storage_utilization ?? worker.cloudwatch_storage_utilization,
            // Preserve CloudWatch fields
            cloudwatch_cpu_utilization: worker.cloudwatch_cpu_utilization,
            cloudwatch_memory_utilization: worker.cloudwatch_memory_utilization,
            cloudwatch_storage_utilization: worker.cloudwatch_storage_utilization,
            cloudwatch_last_collected_at: worker.cloudwatch_last_collected_at,
            created_at: worker.created_at,
            updated_at: worker.updated_at,
        };
    }

    addWorker(workerData) {
        const worker = this.normalizeWorker(workerData);
        this.workers.set(worker.id, worker);
        this.render();
    }

    updateWorker(workerData) {
        const worker = this.normalizeWorker(workerData);
        const workerId = worker.id;

        // Store the worker data
        this.workers.set(workerId, worker);

        // Check if card already exists in DOM
        const existingCard = this.querySelector(`worker-card[worker-id="${workerId}"]`);
        if (existingCard) {
            // Let the card handle its own update via EventBus
            return;
        }

        // If no card exists yet, schedule a render to create it
        // Use short debounce to batch rapid SSE updates during initial load
        this.debouncedRender(50);
    }

    debouncedRender(delay = 50) {
        // Clear existing timeout
        if (this.renderTimeout) {
            clearTimeout(this.renderTimeout);
        }

        // Schedule new render
        this.renderTimeout = setTimeout(() => {
            this.render();
            this.renderTimeout = null;
        }, delay);
    }

    updateWorkerStatus(data) {
        const worker = this.workers.get(data.worker_id);
        if (worker) {
            worker.status = data.new_status;
            worker.updated_at = data.updated_at;
            this.workers.set(data.worker_id, worker);
            // Cards will update themselves via EventBus
        }
    }

    removeWorker(workerId) {
        this.workers.delete(workerId);
        const card = this.querySelector(`worker-card[worker-id="${workerId}"]`);
        if (card) {
            card.remove();
        }
    }

    getFilteredWorkers() {
        const filterStatus = this.getAttr('filter-status');
        const searchTerm = this.getAttr('search', '').toLowerCase();

        let filtered = Array.from(this.workers.values());

        // Filter by status
        if (filterStatus && filterStatus !== 'all') {
            filtered = filtered.filter(w => w.status === filterStatus);
        }

        // Filter by search term
        if (searchTerm) {
            filtered = filtered.filter(w => w.name.toLowerCase().includes(searchTerm) || w.aws_region.toLowerCase().includes(searchTerm) || w.aws_instance_id?.toLowerCase().includes(searchTerm));
        }

        return filtered;
    }

    onAttributeChange(name, oldValue, newValue) {
        if (name === 'region' && oldValue !== newValue) {
            this.loadWorkers();
        } else if (name === 'include-terminated' && oldValue !== newValue) {
            this.loadWorkers();
        } else if (name === 'filter-status' || name === 'search' || name === 'view') {
            this.render();
        }
    }

    render() {
        // Cancel any pending debounced render since we're rendering now
        if (this.renderTimeout) {
            clearTimeout(this.renderTimeout);
            this.renderTimeout = null;
        }

        const view = this.getAttr('view', 'cards');
        const workers = this.getFilteredWorkers();

        console.log(`[WorkerList] Rendering ${workers.length} workers in ${view} view`);

        if (workers.length === 0) {
            this.innerHTML = this.renderEmpty();
            return;
        }

        if (view === 'table') {
            this.innerHTML = this.renderTable(workers);
        } else {
            this.innerHTML = this.renderCards(workers);
        }
    }

    renderEmpty() {
        return `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i>
                No workers found. Try adjusting your filters or create a new worker.
            </div>
        `;
    }

    renderCards(workers) {
        return `
            <div class="row g-3">
                ${workers
                    .map(worker => {
                        // Pass initial data to avoid waiting for SSE
                        // Escape single quotes for attribute value
                        const workerJson = JSON.stringify(worker).replace(/'/g, '&#39;');
                        return `
                    <div class="col-md-6 col-lg-4">
                        <worker-card
                            worker-id="${worker.id}"
                            data='${workerJson}'
                        ></worker-card>
                    </div>
                `;
                    })
                    .join('')}
            </div>
        `;
    }

    renderTable(workers) {
        const html = `
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Region</th>
                            <th>Status</th>
                            <th>License</th>
                            <th>Idle</th>
                            <th>Instance Type</th>
                            <th>CPU</th>
                            <th>Memory</th>
                            <th>Disk</th>
                            <th>Nodes</th>
                            <th>Labs</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${workers.map(worker => this.renderTableRow(worker)).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Need to attach event listeners after rendering
        setTimeout(() => this.attachTableEventListeners(), 0);

        return html;
    }

    renderProgressBar(value) {
        if (value === null || value === undefined) return '<span class="text-muted">N/A</span>';

        const val = parseFloat(value);
        let colorClass = 'bg-success';
        if (val >= 90) colorClass = 'bg-danger';
        else if (val >= 70) colorClass = 'bg-warning';

        return `
            <div class="d-flex align-items-center" style="width: 100px;">
                <div class="progress flex-grow-1" style="height: 6px;" title="${val.toFixed(1)}%">
                    <div class="progress-bar ${colorClass}" role="progressbar" style="width: ${val}%" aria-valuenow="${val}" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
                <span class="ms-2 small text-muted" style="width: 35px; text-align: right;">${Math.round(val)}%</span>
            </div>
        `;
    }

    renderTableRow(worker) {
        const statusClass = this.getStatusClass(worker.status);
        const licenseStatus = worker.license_status || 'unknown';
        const isLicensed = licenseStatus === 'registered';

        // Status icon mapping
        let statusIcon = 'bi-question-circle-fill';
        const s = (worker.status || '').toLowerCase();
        if (s === 'running') statusIcon = 'bi-play-circle-fill';
        else if (s === 'stopped') statusIcon = 'bi-stop-circle-fill';
        else if (s === 'pending') statusIcon = 'bi-hourglass-split';
        else if (s === 'stopping' || s === 'shutting-down') statusIcon = 'bi-power';
        else if (s === 'terminated') statusIcon = 'bi-x-circle-fill';

        // Extract node counts
        let runningNodes = 0;
        let totalNodes = 0;

        if (worker.cml_system_info) {
            if (worker.cml_system_info.running_nodes !== undefined && worker.cml_system_info.running_nodes !== null && worker.cml_system_info.total_nodes !== undefined && worker.cml_system_info.total_nodes !== null) {
                runningNodes = worker.cml_system_info.running_nodes;
                totalNodes = worker.cml_system_info.total_nodes;
            } else if (worker.cml_system_info.computes) {
                const computes = worker.cml_system_info.computes;
                for (const key in computes) {
                    const domInfo = computes[key]?.stats?.dominfo;
                    if (domInfo) {
                        runningNodes += domInfo.running_nodes || 0;
                        totalNodes += domInfo.total_nodes || 0;
                    }
                }
            }
        }
        const nodesDisplay = totalNodes > 0 ? `${runningNodes} / ${totalNodes}` : '—';
        return `
            <tr class="worker-row" data-worker-id="${worker.id}" style="cursor: pointer;">
                <td><strong>${this.escapeHtml(worker.name)}</strong></td>
                <td>${this.escapeHtml(worker.aws_region)}</td>
                <td>
                    <span class="badge bg-${statusClass}" data-bs-toggle="tooltip" title="${this.escapeHtml(worker.status)}">
                        <i class="bi ${statusIcon}"></i>
                    </span>
                </td>
                <td>
                    ${
                        isLicensed
                            ? '<span class="badge bg-success" data-bs-toggle="tooltip" title="Licensed"><i class="bi bi-key-fill"></i></span>'
                            : '<span class="badge bg-warning" data-bs-toggle="tooltip" title="Unlicensed"><i class="bi bi-key"></i></span>'
                    }
                </td>
                <td>
                    ${
                        worker.is_idle_detection_enabled
                            ? '<span class="badge bg-success" data-bs-toggle="tooltip" title="Idle Detection Enabled"><i class="bi bi-moon-stars-fill"></i></span>'
                            : '<span class="badge bg-secondary" data-bs-toggle="tooltip" title="Idle Detection Disabled"><i class="bi bi-moon-stars"></i></span>'
                    }
                </td>
                <td>${this.escapeHtml(worker.instance_type || 'N/A')}</td>
                <td>${this.renderProgressBar(worker.cpu_utilization)}</td>
                <td>${this.renderProgressBar(worker.memory_utilization)}</td>
                <td>${this.renderProgressBar(worker.disk_utilization)}</td>
                <td>${nodesDisplay}</td>
                <td>${worker.cml_labs_count ?? 0}</td>
                <td>
                    <button class="btn btn-sm btn-primary view-details-btn" data-worker-id="${worker.id}">
                        <i class="bi bi-eye"></i>
                    </button>
                </td>
            </tr>
        `;
    }

    getStatusClass(status) {
        const statusMap = {
            running: 'success',
            stopped: 'secondary',
            stopping: 'warning',
            pending: 'info',
            terminated: 'dark',
        };
        return statusMap[status] || 'secondary';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    attachTableEventListeners() {
        // Initialize tooltips
        this.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            new bootstrap.Tooltip(el);
        });

        // Click on table rows to open details
        this.querySelectorAll('.worker-row').forEach(row => {
            row.addEventListener('click', e => {
                // Don't trigger if clicking on a button
                if (e.target.closest('button')) return;

                const workerId = row.dataset.workerId;
                const worker = this.workers.get(workerId);
                console.log('[WorkerList] Row clicked, workerId:', workerId, 'worker:', worker);
                if (worker) {
                    console.log('[WorkerList] Emitting UI_OPEN_WORKER_DETAILS:', {
                        workerId: worker.id,
                        region: worker.aws_region,
                    });
                    eventBus.emit('UI_OPEN_WORKER_DETAILS', {
                        workerId: worker.id,
                        region: worker.aws_region,
                    });
                } else {
                    console.error('[WorkerList] Worker not found in Map for ID:', workerId);
                }
            });
        });

        // Explicit view details buttons
        this.querySelectorAll('.view-details-btn').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                const workerId = btn.dataset.workerId;
                const worker = this.workers.get(workerId);
                console.log('[WorkerList] Button clicked, workerId:', workerId, 'worker:', worker);
                if (worker) {
                    console.log('[WorkerList] Emitting UI_OPEN_WORKER_DETAILS:', {
                        workerId: worker.id,
                        region: worker.aws_region,
                    });
                    eventBus.emit('UI_OPEN_WORKER_DETAILS', {
                        workerId: worker.id,
                        region: worker.aws_region,
                    });
                } else {
                    console.error('[WorkerList] Worker not found in Map for ID:', workerId);
                }
            });
        });
    }

    renderError(message) {
        this.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i>
                <strong>Error loading workers:</strong> ${this.escapeHtml(message)}
            </div>
        `;
    }
}

// Register custom element
customElements.define('worker-list', WorkerList);

export default WorkerList;
