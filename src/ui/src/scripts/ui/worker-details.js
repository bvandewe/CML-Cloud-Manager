// worker-details.js
// Extracted worker details modal logic from workers.js

import * as workersApi from '../api/workers.js';
import { showToast } from './notifications.js';
import { isAdmin, isAdminOrManager } from '../utils/roles.js';
import { initializeDateTooltips } from '../utils/dates.js';
import { renderWorkerOverview } from '../components/workerOverview.js';
import { renderMetrics } from '../components/metricsPanel.js';
import { fetchWorkerDetails, setActiveWorker, updateTiming, logStoreSnapshot } from '../store/workerStore.js';
import { showStartConfirmation, showStopConfirmation } from './worker-actions.js';
import { startMetricsCountdown, updateLastRefreshedDisplay, ensureTimingHeader } from './worker-timing.js';
import * as bootstrap from 'bootstrap';

// These are set by workers.js after import; we keep minimal cross-file state here.
let currentWorkerDetailsRef = null; // {id, region, name?}
let setupRefreshButtonRef = null;
let setupDeleteButtonInDetailsRef = null;
let loadCloudWatchMetricsRef = null;
let setupEnableMonitoringButtonRef = null;
let detailsTransitionInterval = null;

export function bindWorkerDetailsDependencies({ getCurrentWorkerDetails, setCurrentWorkerDetails, setupRefreshButton, setupDeleteButtonInDetails }) {
    // Allow workers.js to bind state & helper callbacks
    currentWorkerDetailsRef = { get: getCurrentWorkerDetails, set: setCurrentWorkerDetails };
    setupRefreshButtonRef = setupRefreshButton;
    setupDeleteButtonInDetailsRef = setupDeleteButtonInDetails;
}

/**
 * Show worker details modal
 */
export async function showWorkerDetails(workerId, region) {
    console.log('[worker-details] showWorkerDetails()', workerId, region);
    const modalElement = document.getElementById('workerDetailsModal');
    if (!modalElement) {
        showToast('Failed to open worker details: modal not found', 'error');
        return;
    }

    let modal = bootstrap.Modal.getInstance(modalElement);
    if (modal) modal.dispose();
    modal = new bootstrap.Modal(modalElement);

    const overviewContent = document.getElementById('worker-details-overview');
    if (!overviewContent) {
        showToast('Failed to open worker details: content area not found', 'error');
        return;
    }

    // Track active worker
    if (currentWorkerDetailsRef?.set) currentWorkerDetailsRef.set({ id: workerId, region });
    setActiveWorker(workerId);
    logStoreSnapshot('after setActiveWorker (details)');

    // Refresh/delete buttons re-bind
    setupRefreshButtonRef && setupRefreshButtonRef();
    setupDeleteButtonInDetailsRef && setupDeleteButtonInDetailsRef();

    modal.show();

    // Role-based tab/button visibility (must be after modal.show())
    const adminTabs = modalElement.querySelectorAll('.admin-only-tab');
    const adminManagerTabs = modalElement.querySelectorAll('.admin-manager-only-tab');
    const adminButtons = modalElement.querySelectorAll('.admin-only');

    console.log('[worker-details] isAdmin():', isAdmin(), 'isAdminOrManager():', isAdminOrManager());
    console.log('[worker-details] Found adminTabs:', adminTabs.length, 'adminManagerTabs:', adminManagerTabs.length);

    if (isAdmin()) {
        adminTabs.forEach(t => {
            console.log('[worker-details] Showing admin tab:', t);
            t.style.display = 'block';
        });
        adminManagerTabs.forEach(t => {
            console.log('[worker-details] Showing admin-manager tab:', t);
            t.style.display = 'block';
        });
        adminButtons.forEach(b => (b.style.display = ''));
    } else if (isAdminOrManager()) {
        adminManagerTabs.forEach(t => {
            console.log('[worker-details] Showing admin-manager tab for manager:', t);
            t.style.display = 'block';
        });
        adminTabs.forEach(t => (t.style.display = 'none'));
        adminButtons.forEach(b => (b.style.display = 'none'));
    } else {
        adminTabs.forEach(t => (t.style.display = 'none'));
        adminManagerTabs.forEach(t => (t.style.display = 'none'));
        adminButtons.forEach(b => (b.style.display = 'none'));
    }

    // Timing header + countdown
    ensureTimingHeader(modalElement);
    startMetricsCountdown();

    try {
        const worker = await fetchWorkerDetails(region, workerId, { force: true });
        overviewContent.innerHTML = renderWorkerOverview(worker);
        startDetailsTransitionUpdater(modalElement);
        setupTagManagement(worker, region);
        // Bind admin action buttons if present
        if (isAdmin()) {
            const startBtn = document.getElementById('admin-action-start');
            if (startBtn) {
                startBtn.addEventListener('click', e => {
                    e.stopPropagation();
                    showStartConfirmation(worker.id, worker.aws_region, worker.name);
                });
            }
            const stopBtn = document.getElementById('admin-action-stop');
            if (stopBtn) {
                stopBtn.addEventListener('click', e => {
                    e.stopPropagation();
                    showStopConfirmation(worker.id, worker.aws_region, worker.name);
                });
            }
            const refreshBtn = document.getElementById('admin-action-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', e => {
                    e.stopPropagation();
                    // Reuse existing refresh button logic if present
                    const modalRefreshBtn = document.getElementById('refresh-worker-details');
                    if (modalRefreshBtn) modalRefreshBtn.click();
                });
            }
        }

        if (currentWorkerDetailsRef?.get) {
            const cur = currentWorkerDetailsRef.get();
            if (cur) cur.name = worker.name;
        }

        loadCloudWatchMetrics(worker);
        if (!worker.cloudwatch_detailed_monitoring_enabled && isAdmin()) {
            setupEnableMonitoringButton(workerId, region);
        }
        initializeDateTooltips();
        modalElement.dataset.workerId = workerId;
        modalElement.dataset.workerRegion = region;

        if (worker.poll_interval && worker.next_refresh_at) {
            updateTiming(worker.id, {
                poll_interval: worker.poll_interval,
                next_refresh_at: worker.next_refresh_at,
                last_refreshed_at: worker.cloudwatch_last_collected_at || new Date().toISOString(),
            });
            updateLastRefreshedDisplay();
            startMetricsCountdown();
        }
    } catch (error) {
        console.error('[worker-details] Failed to load worker details:', error);
        overviewContent.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> Failed to load worker details: ${error.message}</div>`;
        showToast(`Failed to load worker details: ${error.message}`, 'error');
    }
}

/**
 * CloudWatch metrics panel rendering (accepts worker object or id)
 */
export async function loadCloudWatchMetrics(workerOrWorkerId, region) {
    const metricsSection = document.getElementById('cloudwatch-metrics-section');
    if (!metricsSection) return;
    try {
        let worker;
        if (workerOrWorkerId && typeof workerOrWorkerId === 'object') {
            worker = workerOrWorkerId;
            region = worker.aws_region || region;
        } else {
            const workerId = workerOrWorkerId;
            worker = await fetchWorkerDetails(region, workerId);
        }
        metricsSection.innerHTML = renderMetrics(worker);
    } catch (error) {
        console.error('[worker-details] Failed to load CloudWatch metrics:', error);
        metricsSection.innerHTML = `<div class="alert alert-warning mb-0"><i class="bi bi-exclamation-triangle"></i> Unable to load CloudWatch metrics: ${error.message}</div>`;
    }
}

/**
 * Enable detailed monitoring button handler
 */
export function setupEnableMonitoringButton(workerId, region) {
    const btn = document.getElementById('enable-monitoring-btn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Enabling...';
        try {
            await workersApi.enableDetailedMonitoring(region, workerId);
            showToast('Detailed monitoring enabled successfully', 'success');
            await showWorkerDetails(workerId, region); // reload
        } catch (error) {
            console.error('[worker-details] Failed to enable monitoring:', error);
            showToast(error.message || 'Failed to enable detailed monitoring', 'error');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-speedometer2"></i> Enable Detailed Monitoring';
        }
    });
}

function setupTagManagement(worker, region) {
    const workerId = worker.id;
    const listEl = document.getElementById('worker-tags-list');
    const formEl = document.getElementById('add-tag-form');
    if (!listEl) return; // section not present
    // Remove tag handlers (admin only)
    if (isAdmin()) {
        listEl.querySelectorAll('.remove-tag-btn').forEach(btn => {
            btn.addEventListener('click', async e => {
                e.preventDefault();
                e.stopPropagation();
                const key = btn.getAttribute('data-remove-tag');
                if (!key) return;
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
                try {
                    const currentTags = { ...(worker.aws_tags || {}) };
                    delete currentTags[key];
                    const result = await workersApi.updateWorkerTags(region, workerId, currentTags);
                    if (result && typeof result === 'object') {
                        showToast(`Tag '${key}' removed`, 'success');
                        // Re-fetch details to refresh UI
                        const refreshed = await fetchWorkerDetails(region, workerId, { force: true });
                        const overviewContent = document.getElementById('worker-details-overview');
                        if (overviewContent) {
                            overviewContent.innerHTML = renderWorkerOverview(refreshed);
                            setupTagManagement(refreshed, region); // re-bind
                        }
                    } else {
                        showToast('Failed to remove tag', 'error');
                    }
                } catch (err) {
                    console.error('[worker-details] remove tag failed', err);
                    showToast(err.message || 'Tag removal failed', 'error');
                }
            });
        });
    }
    // Add tag form (admin only)
    if (formEl && isAdmin()) {
        formEl.addEventListener('submit', async e => {
            e.preventDefault();
            const keyInput = document.getElementById('new-tag-key');
            const valueInput = document.getElementById('new-tag-value');
            const feedbackEl = document.getElementById('add-tag-feedback');
            if (!keyInput || !valueInput) return;
            const key = (keyInput.value || '').trim();
            const value = (valueInput.value || '').trim();
            if (!key || !value) {
                feedbackEl.textContent = 'Key and value are required.';
                return;
            }
            if (key.length > 128 || value.length > 256) {
                feedbackEl.textContent = 'Exceeded maximum length.';
                return;
            }
            feedbackEl.textContent = 'Saving tag...';
            try {
                const currentTags = { ...(worker.aws_tags || {}) };
                currentTags[key] = value;
                const result = await workersApi.updateWorkerTags(region, workerId, currentTags);
                if (result && typeof result === 'object') {
                    showToast(`Tag '${key}' added`, 'success');
                    keyInput.value = '';
                    valueInput.value = '';
                    feedbackEl.textContent = 'Tag added.';
                    // Re-fetch details
                    const refreshed = await fetchWorkerDetails(region, workerId, { force: true });
                    const overviewContent = document.getElementById('worker-details-overview');
                    if (overviewContent) {
                        overviewContent.innerHTML = renderWorkerOverview(refreshed);
                        setupTagManagement(refreshed, region);
                    }
                } else {
                    feedbackEl.textContent = 'Failed to add tag.';
                    showToast('Failed to add tag', 'error');
                }
            } catch (err) {
                console.error('[worker-details] add tag failed', err);
                feedbackEl.textContent = 'Error adding tag.';
                showToast(err.message || 'Add tag failed', 'error');
            }
        });
    }
}

function startDetailsTransitionUpdater(modalElement) {
    stopDetailsTransitionUpdater();
    detailsTransitionInterval = setInterval(() => {
        if (!modalElement || !modalElement.classList.contains('show')) {
            stopDetailsTransitionUpdater();
            return;
        }
        const elements = modalElement.querySelectorAll('.transition-duration');
        if (!elements.length) return; // keep interval; may appear later
        elements.forEach(el => {
            const initTs = el.dataset.initTs;
            if (!initTs) return;
            let initMs;
            try {
                initMs = Date.parse(initTs);
                if (isNaN(initMs)) return;
            } catch (_) {
                return;
            }
            const diffSec = Math.max(0, Math.floor((Date.now() - initMs) / 1000));
            const mins = Math.floor(diffSec / 60);
            const secs = diffSec % 60;
            const span = el.querySelector('.elapsed');
            if (span) span.textContent = `${mins}m ${secs}s`;
        });
    }, 1000);
    // Clear interval when modal hidden
    modalElement.addEventListener(
        'hidden.bs.modal',
        () => {
            stopDetailsTransitionUpdater();
        },
        { once: true }
    );
}

function stopDetailsTransitionUpdater() {
    if (detailsTransitionInterval) {
        clearInterval(detailsTransitionInterval);
        detailsTransitionInterval = null;
    }
}
