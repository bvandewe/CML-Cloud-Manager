/**
 * WorkerCard Component
 *
 * Self-contained worker card with:
 * - Reactive updates via EventBus
 * - Encapsulated rendering
 * - No global state dependencies
 *
 * Usage:
 *   <worker-card worker-id="abc123"></worker-card>
 */

import { BaseComponent } from '../core/BaseComponent.js';
import { EventTypes } from '../core/EventBus.js';
import { escapeHtml } from '../components/escape.js';
import { getStatusBadgeClass, getCpuProgressClass, getMemoryProgressClass } from '../components/status-badges.js';
import { formatDateWithRelative } from '../utils/dates.js';

export class WorkerCard extends BaseComponent {
    static get observedAttributes() {
        return ['worker-id', 'compact', 'data'];
    }

    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
    }

    onAttributeChange(name, oldValue, newValue) {
        if (name === 'data' && newValue && newValue !== oldValue) {
            try {
                const worker = JSON.parse(newValue);
                this.setState({ worker });
            } catch (e) {
                console.error('WorkerCard: Invalid data attribute', e);
            }
        }
    }

    onMount() {
        const workerId = this.getAttr('worker-id');
        if (!workerId) {
            console.error('WorkerCard: worker-id attribute is required');
            return;
        }

        // Check for initial data
        const dataAttr = this.getAttr('data');
        if (dataAttr) {
            try {
                const worker = JSON.parse(dataAttr);
                this.setState({ worker });
            } catch (e) {
                console.error('WorkerCard: Invalid initial data', e);
            }
        }

        // Subscribe to worker updates
        this.subscribe(EventTypes.WORKER_SNAPSHOT, data => {
            if (data.worker_id === workerId) {
                // Normalize worker data to ensure consistent field names
                const normalizedWorker = {
                    id: data.id || data.worker_id,
                    worker_id: data.worker_id,
                    name: data.name,
                    aws_region: data.aws_region || data.region,
                    region: data.region || data.aws_region,
                    status: data.status,
                    service_status: data.service_status,
                    instance_type: data.instance_type,
                    license_status: data.license_status,
                    cpu_utilization: data.cpu_utilization,
                    memory_utilization: data.memory_utilization,
                    disk_utilization: data.disk_utilization || data.storage_utilization,
                    updated_at: data.updated_at,
                    ...data, // Keep all other fields
                };
                this.setState({ worker: normalizedWorker });
            }
        });

        this.subscribe(EventTypes.WORKER_METRICS_UPDATED, data => {
            if (data.worker_id === workerId) {
                this.updateMetrics(data);
            }
        });

        this.subscribe(EventTypes.WORKER_DELETED, data => {
            if (data.worker_id === workerId) {
                this.remove(); // Self-destruct when worker deleted
            }
        });

        // Initial render
        this.loadWorkerData();
    }

    async loadWorkerData() {
        const workerId = this.getAttr('worker-id');
        // In real implementation, fetch from store or API
        // For now, we'll wait for EventBus updates
        this.render();
    }

    updateMetrics(metricsData) {
        const state = this.getState();
        if (state.worker) {
            this.setState({
                worker: {
                    ...state.worker,
                    cpu_utilization: metricsData.cpu_utilization,
                    memory_utilization: metricsData.memory_utilization,
                    disk_utilization: metricsData.disk_utilization,
                },
            });
        }
    }

    render() {
        const { worker } = this.getState();
        const isCompact = this.getBoolAttr('compact');

        if (!worker) {
            this.shadowRoot.innerHTML = this.renderLoading();
            return;
        }

        this.shadowRoot.innerHTML = this.html`
            ${this.renderStyles()}
            ${isCompact ? this.renderCompactCard(worker) : this.renderFullCard(worker)}
        `;

        this.attachEventListeners();
    }

    renderStyles() {
        return `
            <style>
                :host {
                    display: block;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                }
                .card {
                    border: 1px solid #dee2e6;
                    border-radius: 0.375rem;
                    background: white;
                    transition: box-shadow 0.2s, transform 0.2s;
                    height: 100%;
                }
                .card:hover {
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    transform: translateY(-2px);
                    cursor: pointer;
                }
                .card-header {
                    padding: 1rem;
                    border-bottom: 1px solid #dee2e6;
                    background-color: #f8f9fa;
                }
                .card-body {
                    padding: 1rem;
                }
                .badge {
                    padding: 0.25rem 0.5rem;
                    border-radius: 0.25rem;
                    font-size: 0.75rem;
                    font-weight: 600;
                }
                .badge-success { background: #198754; color: white; }
                .badge-danger { background: #dc3545; color: white; }
                .badge-warning { background: #ffc107; color: #000; }
                .badge-secondary { background: #6c757d; color: white; }
                .progress {
                    height: 0.5rem;
                    background-color: #e9ecef;
                    border-radius: 0.25rem;
                    overflow: hidden;
                }
                .progress-bar {
                    height: 100%;
                    transition: width 0.3s ease;
                }
                .progress-bar-success { background: #198754; }
                .progress-bar-warning { background: #ffc107; }
                .progress-bar-danger { background: #dc3545; }
                .metric-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 0.5rem;
                }
                .text-muted {
                    color: #6c757d;
                    font-size: 0.875rem;
                }
                button {
                    padding: 0.375rem 0.75rem;
                    border: 1px solid #dee2e6;
                    border-radius: 0.25rem;
                    background: white;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                button:hover {
                    background: #f8f9fa;
                }
            </style>
        `;
    }

    renderLoading() {
        return `
            ${this.renderStyles()}
            <div class="card">
                <div class="card-body" style="text-align: center; padding: 2rem;">
                    <div class="spinner" style="border: 3px solid #f3f3f3; border-top: 3px solid #0d6efd; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                    <p style="margin-top: 1rem; color: #6c757d;">Loading worker...</p>
                </div>
            </div>
            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        `;
    }

    renderFullCard(worker) {
        const statusClass = getStatusBadgeClass(worker.status);
        const cpuClass = getCpuProgressClass(worker.cpu_utilization);
        const memClass = getMemoryProgressClass(worker.memory_utilization);
        const diskClass = getMemoryProgressClass(worker.disk_utilization); // Reuse memory colors

        // Determine header color based on overall status
        let headerBgColor = '#f8f9fa'; // default
        if (worker.status === 'running' && worker.service_status === 'ready') {
            headerBgColor = '#d1e7dd'; // success light
        } else if (worker.status === 'running' && worker.service_status !== 'ready') {
            headerBgColor = '#fff3cd'; // warning light
        } else if (worker.status === 'stopped') {
            headerBgColor = '#e2e3e5'; // secondary light
        } else if (worker.status === 'pending' || worker.status === 'stopping') {
            headerBgColor = '#cff4fc'; // info light
        }

        const licenseStatus = worker.license_status || 'unknown';
        // Check nested registration status if available
        const registrationStatus = worker.cml_license_info?.registration?.status;
        const isLicensed = licenseStatus === 'registered' || registrationStatus === 'COMPLETED' || registrationStatus === 'REGISTERED';

        return `
            <div class="card" data-action="open-details">
                <div class="card-header" style="background-color: ${headerBgColor};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>${escapeHtml(worker.name)}</strong>
                        <div style="display: flex; gap: 0.25rem;">
                            ${isLicensed ? '<span class="badge badge-success" title="Licensed"><i class="bi bi-key-fill"></i></span>' : '<span class="badge badge-warning" title="Unlicensed"><i class="bi bi-key"></i></span>'}
                            <span class="badge badge-${statusClass}">${escapeHtml(worker.status)}</span>
                        </div>
                    </div>
                </div>
                <div class="card-body">
                    <div class="metric-row">
                        <span class="text-muted">Region</span>
                        <span>${escapeHtml(worker.aws_region)}</span>
                    </div>
                    <div class="metric-row">
                        <span class="text-muted">Instance Type</span>
                        <span>${escapeHtml(worker.instance_type || 'N/A')}</span>
                    </div>

                    <!-- Resource Utilization in a single row -->
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-top: 0.75rem;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                <span class="text-muted" style="font-size: 0.75rem;">CPU</span>
                                <span style="font-size: 0.75rem;">${worker.cpu_utilization ? worker.cpu_utilization.toFixed(1) : '0'}%</span>
                            </div>
                            <div class="progress">
                                <div class="progress-bar progress-bar-${cpuClass}" style="width: ${worker.cpu_utilization || 0}%"></div>
                            </div>
                        </div>
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                <span class="text-muted" style="font-size: 0.75rem;">Memory</span>
                                <span style="font-size: 0.75rem;">${worker.memory_utilization ? worker.memory_utilization.toFixed(1) : '0'}%</span>
                            </div>
                            <div class="progress">
                                <div class="progress-bar progress-bar-${memClass}" style="width: ${worker.memory_utilization || 0}%"></div>
                            </div>
                        </div>
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                                <span class="text-muted" style="font-size: 0.75rem;">Disk</span>
                                <span style="font-size: 0.75rem;">${worker.disk_utilization ? worker.disk_utilization.toFixed(1) : '0'}%</span>
                            </div>
                            <div class="progress">
                                <div class="progress-bar progress-bar-${diskClass}" style="width: ${worker.disk_utilization || 0}%"></div>
                            </div>
                        </div>
                    </div>

                    <div style="margin-top: 1rem; font-size: 0.75rem; color: #6c757d;">
                        Updated: ${formatDateWithRelative(worker.updated_at)}
                    </div>
                </div>
            </div>
        `;
    }

    renderCompactCard(worker) {
        const statusClass = getStatusBadgeClass(worker.status);

        return `
            <div class="card" data-action="open-details" style="padding: 0.75rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>${escapeHtml(worker.name)}</strong>
                        <div class="text-muted" style="font-size: 0.75rem;">
                            ${escapeHtml(worker.aws_region)}
                        </div>
                    </div>
                    <span class="badge badge-${statusClass}">${escapeHtml(worker.status)}</span>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const card = this.shadowRoot.querySelector('[data-action="open-details"]');
        if (card) {
            card.addEventListener('click', () => {
                const worker = this.getState().worker;
                if (!worker) {
                    console.error('[WorkerCard] No worker data available for click');
                    return;
                }
                if (!worker.id || !worker.aws_region) {
                    console.error('[WorkerCard] Worker missing id or region:', worker);
                    return;
                }
                console.log('[WorkerCard] Emitting UI_OPEN_WORKER_DETAILS:', {
                    workerId: worker.id,
                    region: worker.aws_region,
                });
                this.emit('UI_OPEN_WORKER_DETAILS', {
                    workerId: worker.id,
                    region: worker.aws_region,
                });
            });
        }
    }
}

// Register custom element
customElements.define('worker-card', WorkerCard);

export default WorkerCard;
