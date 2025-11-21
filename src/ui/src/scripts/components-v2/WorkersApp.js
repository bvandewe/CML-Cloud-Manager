/**
 * WorkersApp - Web Components Integration Layer
 *
 * Main application controller for the workers view using Web Components architecture.
 * Replaces workers.js orchestration with clean component composition.
 *
 * Features:
 * - Feature flag support (gradual migration)
 * - EventBus integration
 * - SSE connection management
 * - Component initialization
 */

import { eventBus, EventTypes } from '../core/EventBus.js';
import { sseService } from '../services/SSEService.js';
import { setupCreateWorkerModal, setupImportWorkerModal } from '../ui/worker-modals.js';
import { isAdminOrManager } from '../utils/roles.js';
import '../components-v2/WorkerCard.js';
import '../components-v2/WorkerList.js';
import '../components-v2/FilterBar.js';
import '../components-v2/StatisticsPanel.js';
import '../components-v2/WorkerDetailsModal.js';

class WorkersApp {
    constructor() {
        this.currentUser = null;
        this.currentRegion = 'us-east-1';
        this.currentView = 'cards';
        this.initialized = false;
    }

    /**
     * Initialize the workers app
     */
    async initialize(user) {
        if (this.initialized) {
            console.warn('[WorkersApp] Already initialized');
            return;
        }

        console.log('[WorkersApp] Initializing with user:', user);
        this.currentUser = user;

        // Setup EventBus debugging in development
        if (localStorage.getItem('debug-events') === 'true') {
            eventBus.enableDebug();
        }

        // Subscribe to filter changes
        this.subscribeToEvents();

        // Connect SSE
        this.connectSSE();

        // Render the UI
        this.render();

        // Initialize modals
        setupCreateWorkerModal();
        setupImportWorkerModal();

        // Expose refresh method for modals
        // Note: We attach to the existing window.workersApp object or create it
        window.workersApp = window.workersApp || {};
        window.workersApp.refreshWorkers = () => this.refreshWorkers();

        this.initialized = true;
        console.log('[WorkersApp] Initialization complete');
    }

    /**
     * Refresh the workers list
     */
    refreshWorkers() {
        console.log('[WorkersApp] Refreshing workers list...');
        const workerList = document.querySelector('worker-list');
        if (workerList && typeof workerList.loadWorkers === 'function') {
            workerList.loadWorkers();
        }
    }

    /**
     * Subscribe to EventBus events
     */
    subscribeToEvents() {
        // Handle filter changes
        eventBus.on(EventTypes.UI_FILTER_CHANGED, data => {
            console.log('[WorkersApp] Filter changed:', data);

            switch (data.type) {
                case 'region':
                    this.currentRegion = data.value;
                    this.updateWorkerList();
                    break;
                case 'status':
                    this.updateFilterAttribute('filter-status', data.value);
                    break;
                case 'search':
                    this.updateFilterAttribute('search', data.value);
                    break;
                case 'view':
                    this.currentView = data.value;
                    this.updateFilterAttribute('view', data.value);
                    break;
            }
        });

        // Handle modal open requests (legacy event type)
        eventBus.on(EventTypes.UI_MODAL_OPENED, data => {
            console.log('[WorkersApp] Modal open requested:', data);

            if (data.type === 'worker-details') {
                // Legacy path - convert to new event format
                eventBus.emit('UI_OPEN_WORKER_DETAILS', {
                    workerId: data.workerId,
                    region: data.worker?.aws_region,
                });
            }
        });

        // Note: WorkerDetailsModal subscribes to 'UI_OPEN_WORKER_DETAILS' directly
        // No need to re-emit here to avoid infinite loop

        // Handle SSE connection status
        eventBus.on(EventTypes.SSE_CONNECTED, () => {
            this.updateSSEStatus('connected');
        });

        eventBus.on(EventTypes.SSE_DISCONNECTED, () => {
            this.updateSSEStatus('disconnected');
        });

        eventBus.on(EventTypes.SSE_ERROR, () => {
            this.updateSSEStatus('error');
        });
    }

    /**
     * Connect to SSE
     */
    connectSSE() {
        console.log('[WorkersApp] Connecting SSE...');
        sseService.connect();
    }

    /**
     * Render the UI components
     */
    render() {
        const container = document.getElementById('workers-container');
        if (!container) {
            console.error('[WorkersApp] workers-container not found');
            return;
        }

        // Hide legacy views
        const adminView = document.getElementById('workers-admin-view');
        const userView = document.getElementById('workers-user-view');
        if (adminView) adminView.style.display = 'none';
        if (userView) userView.style.display = 'none';

        // Determine view mode based on user role
        // Use the utility function which checks localStorage 'user_roles'
        // This is more reliable than checking the user object passed to initialize
        // as that object structure might vary depending on the auth provider response
        const isAdmin = isAdminOrManager();

        console.log('[WorkersApp] User roles check:', {
            user: this.currentUser,
            roles: this.currentUser?.realm_access?.roles,
            isAdmin,
        });

        const defaultView = isAdmin ? 'table' : 'cards';
        this.currentView = defaultView;

        container.innerHTML = `
            <!-- Action Buttons -->
            <div class="row mb-4">
                <div class="col">
                    <h2>
                        <i class="bi bi-server"></i> CML Workers Management
                    </h2>
                </div>
                <div class="col-auto">
                    <div class="btn-group" role="group">
                        ${
                            isAdmin
                                ? `
                            <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#createWorkerModal">
                                <i class="bi bi-plus-circle"></i> New
                            </button>
                            <button class="btn btn-outline-primary" data-bs-toggle="modal" data-bs-target="#importWorkerModal">
                                <i class="bi bi-box-arrow-in-down"></i> Import
                            </button>
                        `
                                : ''
                        }
                        <button class="btn btn-outline-secondary" onclick="location.reload()">
                            <i class="bi bi-arrow-clockwise"></i> Refresh
                        </button>
                    </div>
                </div>
            </div>

            <!-- SSE Connection Status -->
            <div id="sse-connection-status" class="mb-3">
                <span class="badge bg-secondary">
                    <i class="bi bi-wifi"></i> Connecting to real-time updates...
                </span>
            </div>

            <!-- Filter Bar -->
            <filter-bar></filter-bar>

            <!-- Workers List -->
            <worker-list
                region="${this.currentRegion}"
                view="${this.currentView}"
            ></worker-list>

            <!-- Worker Details Modal -->
            <worker-details-modal></worker-details-modal>
        `;

        console.log('[WorkersApp] Rendered with view:', this.currentView);
    }

    /**
     * Update worker list component
     */
    updateWorkerList() {
        const workerList = document.querySelector('worker-list');
        if (workerList) {
            workerList.setAttribute('region', this.currentRegion);
        }
    }

    /**
     * Update filter attribute on worker list
     */
    updateFilterAttribute(attr, value) {
        const workerList = document.querySelector('worker-list');
        if (workerList) {
            workerList.setAttribute(attr, value);
        }
    }

    /**
     * Update SSE connection status indicator
     */
    updateSSEStatus(status) {
        const statusEl = document.getElementById('sse-connection-status');
        if (!statusEl) return;

        const statusConfig = {
            connected: {
                class: 'bg-success',
                icon: 'wifi',
                text: 'Real-time updates active',
            },
            disconnected: {
                class: 'bg-secondary',
                icon: 'wifi-off',
                text: 'Real-time updates disconnected',
            },
            error: {
                class: 'bg-danger',
                icon: 'exclamation-triangle',
                text: 'Real-time updates error',
            },
        };

        const config = statusConfig[status] || statusConfig.disconnected;

        statusEl.innerHTML = `
            <span class="badge ${config.class}">
                <i class="bi bi-${config.icon}"></i> ${config.text}
            </span>
        `;
    }

    /**
     * Open worker details modal (for programmatic use)
     * This method is kept for backward compatibility but should not re-emit the event
     * to avoid infinite loops. Components should emit 'UI_OPEN_WORKER_DETAILS' directly.
     */
    async openWorkerDetailsModal(workerId, region) {
        console.log('[WorkersApp] Opening worker details modal (direct call):', workerId, region);

        // Emit event only if called programmatically (not from event handler)
        // The modal subscribes to this event directly
        if (workerId && region) {
            eventBus.emit('UI_OPEN_WORKER_DETAILS', { workerId, region });
        } else {
            console.warn('[WorkersApp] Invalid parameters for opening modal:', { workerId, region });
        }
    }

    /**
     * Cleanup on app unmount
     */
    destroy() {
        console.log('[WorkersApp] Destroying...');
        sseService.disconnect();
        this.initialized = false;
    }
}

// Create singleton instance
const workersApp = new WorkersApp();

/**
 * Initialize workers view (called from app.js)
 */
export function initializeWorkersView(user) {
    console.log('[WorkersApp] initializeWorkersView called');

    // Check feature flag
    const useWebComponents = localStorage.getItem('use-web-components') !== 'false';

    if (useWebComponents) {
        console.log('[WorkersApp] Using Web Components implementation');
        workersApp.initialize(user);
    } else {
        console.log('[WorkersApp] Using legacy implementation');
        // Fall back to legacy workers.js
        import('../ui/workers.js').then(module => {
            module.initializeWorkersView(user);
        });
    }
}

export default workersApp;
