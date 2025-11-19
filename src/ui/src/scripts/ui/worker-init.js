// worker-init.js
// Extracted initialization & event binding logic for workers UI

import { showToast } from './notifications.js';
import { isAdmin } from '../utils/roles.js';
import { initWorkerSSE, setupSSEStatusIndicator } from './worker-sse.js';
import sseClient from '../services/sse-client.js';
import { stopMetricsCountdown } from './worker-timing.js';
import { setupCreateWorkerModal, setupImportWorkerModal, setupDeleteWorkerModal, setupLicenseModal } from './worker-modals.js';
import { loadLabsTab } from './worker-labs.js';
import { loadJobsTab } from './worker-jobs.js';
import { loadMonitoringTab } from './worker-monitoring.js';
import { loadEventsTab } from './worker-events.js';
import * as bootstrap from 'bootstrap';

// Helper: role check replicated from original file
function hasAdminAccess(user) {
    const roles = user?.realm_access?.roles || user?.roles || [];
    return roles.includes('admin') || roles.includes('manager');
}

function initializeAdminView() {
    setTimeout(() => {
        const adminElements = document.querySelectorAll('.admin-only-element');
        if (isAdmin()) {
            adminElements.forEach(el => (el.style.display = ''));
        } else {
            adminElements.forEach(el => (el.style.display = 'none'));
        }
    }, 100);
}

function initializeUserView() {
    // Reserved for future user-specific setup
}

function setupTabHandlers() {
    const cmlTab = document.getElementById('cml-tab');
    const labsTab = document.getElementById('labs-tab');
    const jobsTab = document.getElementById('jobs-tab');
    const monitoringTab = document.getElementById('monitoring-tab');
    const eventsTab = document.getElementById('events-tab');
    if (cmlTab) cmlTab.addEventListener('shown.bs.tab', () => loadCMLTabSafe());
    if (labsTab) labsTab.addEventListener('shown.bs.tab', loadLabsTab);
    if (jobsTab) jobsTab.addEventListener('shown.bs.tab', loadJobsTab);
    if (monitoringTab) monitoringTab.addEventListener('shown.bs.tab', loadMonitoringTab);
    if (eventsTab) eventsTab.addEventListener('shown.bs.tab', loadEventsTab);
}

// Placeholder: original loadCMLTab lives in workers.js; call if present
function loadCMLTabSafe() {
    if (window.workersInternal?.loadCMLTab) {
        window.workersInternal.loadCMLTab();
    }
}

function setupRefreshButton(getCurrentWorkerDetails) {
    const refreshBtn = document.getElementById('refresh-worker-details');
    if (!refreshBtn) return;
    const newBtn = refreshBtn.cloneNode(true);
    refreshBtn.parentNode.replaceChild(newBtn, refreshBtn);
    newBtn.disabled = false;
    newBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Refresh';
    newBtn.addEventListener('click', async () => {
        const current = getCurrentWorkerDetails();
        if (!current) {
            showToast('Unable to refresh: worker not loaded', 'error');
            return;
        }
        const { id, region } = current;
        newBtn.disabled = true;
        const originalHtml = newBtn.innerHTML;
        newBtn.innerHTML = '<i class="bi bi-arrow-clockwise spinner-border spinner-border-sm"></i> Refreshing...';
        try {
            showToast('Fetching latest worker data...', 'info');
            // Lightweight snapshot fetch; store listener will render
            if (window.workersApi?.getWorker) {
                await window.workersApi.getWorker(region, id);
            }
        } catch (e) {
            console.error('[worker-init] refresh error', e);
            showToast(e.message || 'Failed to fetch worker', 'error');
        } finally {
            newBtn.disabled = false;
            newBtn.innerHTML = originalHtml;
        }
    });
}

function setupDeleteButtonInDetails(getCurrentWorkerDetails, showDeleteModal) {
    const deleteBtn = document.getElementById('delete-worker-from-details-btn');
    if (!deleteBtn) return;
    const newBtn = deleteBtn.cloneNode(true);
    deleteBtn.parentNode.replaceChild(newBtn, deleteBtn);
    newBtn.addEventListener('click', () => {
        const current = getCurrentWorkerDetails();
        if (!current) {
            showToast('Unable to delete: worker not loaded', 'error');
            return;
        }
        const { id, region, name } = current;
        const detailsModal = bootstrap.Modal.getInstance(document.getElementById('workerDetailsModal'));
        if (detailsModal) detailsModal.hide();
        showDeleteModal(id, region, name);
    });
}

function setupEventListeners(deps) {
    const { loadWorkers, applyFilters, applyUserFilters, showDeleteModal, getCurrentWorkerDetails } = deps;
    const filterRegion = document.getElementById('filter-region');
    const filterStatus = document.getElementById('filter-status');
    const searchWorkers = document.getElementById('search-workers');
    if (filterRegion)
        filterRegion.addEventListener('change', e => {
            deps.setCurrentRegion(e.target.value || 'us-east-1');
            loadWorkers();
        });
    if (filterStatus) filterStatus.addEventListener('change', () => applyFilters && applyFilters());
    if (searchWorkers) searchWorkers.addEventListener('input', () => applyFilters && applyFilters());
    const filterStatusUser = document.getElementById('filter-status-user');
    const searchWorkersUser = document.getElementById('search-workers-user');
    const sortWorkersUser = document.getElementById('sort-workers-user');
    if (filterStatusUser) filterStatusUser.addEventListener('change', () => applyUserFilters && applyUserFilters());
    if (searchWorkersUser) searchWorkersUser.addEventListener('input', () => applyUserFilters && applyUserFilters());
    if (sortWorkersUser) sortWorkersUser.addEventListener('change', () => applyUserFilters && applyUserFilters());
    setupCreateWorkerModal();
    setupImportWorkerModal();
    setupDeleteWorkerModal();
    setupLicenseModal();
    setupTabHandlers();
    setupRefreshButton(getCurrentWorkerDetails);
    setupDeleteButtonInDetails(getCurrentWorkerDetails, showDeleteModal);
    const workerDetailsModal = document.getElementById('workerDetailsModal');
    if (workerDetailsModal) {
        workerDetailsModal.addEventListener('hidden.bs.modal', () => {
            stopMetricsCountdown();
        });
    }
}

export function initializeWorkersView(user, deps) {
    const { upsertWorkerSnapshot, updateWorkerMetrics, updateTiming, onLabsTabShouldReload, subscribe, handleStoreUpdate, bindRenderDependencies, loadWorkers, getCurrentWorkerDetails, setCurrentWorkerDetails, setUnsubscribe, showDeleteModal } = deps;

    const workersSection = document.getElementById('workers-section');
    const adminView = document.getElementById('workers-admin-view');
    const userView = document.getElementById('workers-user-view');
    if (!workersSection) {
        console.error('[worker-init] workers-section not found');
        return;
    }
    workersSection.style.display = 'block';

    // Inject SSE status badge
    let statusContainer = document.getElementById('sse-connection-status');
    if (!statusContainer) {
        statusContainer = document.createElement('div');
        statusContainer.id = 'sse-connection-status';
        statusContainer.className = 'mb-2';
        statusContainer.innerHTML = '<span class="badge bg-secondary">Realtime: initializing...</span>';
        workersSection.prepend(statusContainer);
    }

    // Initialize SSE
    initWorkerSSE({
        upsertWorkerSnapshot,
        updateWorkerMetrics,
        updateTiming,
        getCurrentWorkerDetails,
        onLabsTabShouldReload,
    });
    setupSSEStatusIndicator();
    sseClient.connect();

    // Role-specific view
    if (hasAdminAccess(user)) {
        adminView.style.display = 'block';
        userView.style.display = 'none';
        initializeAdminView();
    } else {
        adminView.style.display = 'none';
        userView.style.display = 'block';
        initializeUserView();
    }

    // Events
    setupEventListeners({
        loadWorkers,
        applyFilters: window.workersInternal?.applyFilters,
        applyUserFilters: window.workersInternal?.applyUserFilters,
        showDeleteModal,
        getCurrentWorkerDetails,
        setCurrentRegion: val => {
            if (deps.setCurrentRegion) deps.setCurrentRegion(val);
        },
    });

    // Store subscription
    const unsubscribe = subscribe(handleStoreUpdate);
    // Use provided getWorkersData dependency directly
    if (deps.getWorkersData) {
        bindRenderDependencies({ getWorkersData: deps.getWorkersData });
    }
    setUnsubscribe && setUnsubscribe(unsubscribe);

    // Initial load
    loadWorkers();
}
