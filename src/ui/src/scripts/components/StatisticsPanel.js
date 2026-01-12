/**
 * StatisticsPanel Component
 *
 * Displays aggregate statistics for workers (count, average CPU, memory, disk).
 * Replaces updateStatistics() function in worker-render.js.
 *
 * Usage:
 *   <statistics-panel></statistics-panel>
 */

import { BaseComponent } from '../core/BaseComponent.js';
import { EventTypes } from '../core/EventBus.js';

export class StatisticsPanel extends BaseComponent {
    constructor() {
        super();
        this.workers = [];
    }

    onMount() {
        // Subscribe to worker updates
        this.subscribe(EventTypes.WORKER_SNAPSHOT, () => {
            this.updateFromStore();
        });

        this.subscribe(EventTypes.WORKER_METRICS_UPDATED, () => {
            this.updateFromStore();
        });

        this.subscribe(EventTypes.WORKER_CREATED, () => {
            this.updateFromStore();
        });

        this.subscribe(EventTypes.WORKER_DELETED, () => {
            this.updateFromStore();
        });

        this.updateFromStore();
        this.render();
    }

    async updateFromStore() {
        try {
            const { getAllWorkers } = await import('../store/workerStore.js');
            this.workers = getAllWorkers();
            this.render();
        } catch (error) {
            console.error('[StatisticsPanel] Failed to get workers:', error);
        }
    }

    calculateStatistics() {
        const total = this.workers.length;
        const running = this.workers.filter(w => w.status === 'running').length;
        const stopped = this.workers.filter(w => w.status === 'stopped').length;

        // Calculate average utilization
        const workersWithCpu = this.workers.filter(w => w.cpu_utilization != null);
        const avgCpu = workersWithCpu.length ? (workersWithCpu.reduce((sum, w) => sum + w.cpu_utilization, 0) / workersWithCpu.length).toFixed(1) : 0;

        const workersWithMem = this.workers.filter(w => w.memory_utilization != null);
        const avgMemory = workersWithMem.length ? (workersWithMem.reduce((sum, w) => sum + w.memory_utilization, 0) / workersWithMem.length).toFixed(1) : 0;

        const workersWithDisk = this.workers.filter(w => w.storage_utilization != null);
        const avgDisk = workersWithDisk.length ? (workersWithDisk.reduce((sum, w) => sum + w.storage_utilization, 0) / workersWithDisk.length).toFixed(1) : 0;

        return { total, running, stopped, avgCpu, avgMemory, avgDisk };
    }

    render() {
        const stats = this.calculateStatistics();

        this.innerHTML = `
            <div class="row g-3 mb-4">
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="text-muted mb-2">Total Workers</h6>
                            <h2 class="mb-0">${stats.total}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="text-muted mb-2">Running</h6>
                            <h2 class="mb-0 text-success">${stats.running}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="text-muted mb-2">Stopped</h6>
                            <h2 class="mb-0 text-secondary">${stats.stopped}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-body">
                            <h6 class="text-muted mb-2">Average Utilization</h6>
                            <div class="d-flex justify-content-between">
                                <div class="text-center">
                                    <small class="text-muted d-block">CPU</small>
                                    <strong>${stats.avgCpu}%</strong>
                                </div>
                                <div class="text-center">
                                    <small class="text-muted d-block">Memory</small>
                                    <strong>${stats.avgMemory}%</strong>
                                </div>
                                <div class="text-center">
                                    <small class="text-muted d-block">Disk</small>
                                    <strong>${stats.avgDisk}%</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

// Register custom element
customElements.define('statistics-panel', StatisticsPanel);

export default StatisticsPanel;
