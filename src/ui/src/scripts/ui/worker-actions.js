// worker-actions.js
// Extracted worker lifecycle actions & confirmations

import * as workersApi from '../api/workers.js';
import { showToast } from './notifications.js';
import { isAdmin } from '../utils/roles.js';
import { showConfirm } from '../components/modals.js';
import { fetchWorkerDetails } from '../store/workerStore.js';

export async function startWorker(workerId, region) {
    if (!isAdmin()) {
        showToast('Permission denied: admin only', 'error');
        return;
    }
    try {
        await workersApi.startWorker(region, workerId);
        showToast('Worker start initiated', 'success');
        setTimeout(() => window.workersApp.refreshWorkers?.(), 2000);
    } catch (e) {
        console.error('[worker-actions] start error', e);
        showToast(e.message || 'Failed to start worker', 'error');
    }
}

export async function stopWorker(workerId, region) {
    if (!isAdmin()) {
        showToast('Permission denied: admin only', 'error');
        return;
    }
    try {
        await workersApi.stopWorker(region, workerId);
        showToast('Worker stop initiated', 'success');
        setTimeout(() => window.workersApp.refreshWorkers?.(), 2000);
    } catch (e) {
        console.error('[worker-actions] stop error', e);
        showToast(e.message || 'Failed to stop worker', 'error');
    }
}

export function showStartConfirmation(workerId, region, workerName) {
    if (!isAdmin()) {
        showToast('Permission denied: admin only', 'error');
        return;
    }
    if (typeof showConfirm === 'function') {
        showConfirm(
            'Start Worker',
            `Start worker "${workerName}"? This boots the EC2 instance and CML service.`,
            async () => {
                await startWorker(workerId, region);
            },
            {
                actionLabel: 'Start Worker',
                actionClass: 'btn-success',
                iconClass: 'bi bi-play-fill text-success me-2',
            }
        );
    }
}

export function showStopConfirmation(workerId, region, workerName) {
    if (!isAdmin()) {
        showToast('Permission denied: admin only', 'error');
        return;
    }
    if (typeof showConfirm === 'function') {
        showConfirm(
            'Stop Worker',
            `Stop worker "${workerName}"? This shuts down EC2 and CML service (labs impacted).`,
            async () => {
                await stopWorker(workerId, region);
            },
            {
                actionLabel: 'Stop Worker',
                actionClass: 'btn-warning',
                iconClass: 'bi bi-stop-fill text-warning me-2',
            }
        );
    }
}

export async function refreshWorkers() {
    // Simply refetch via API snapshot call; workers.js will upsert through store
    try {
        const region = 'us-east-1'; // fallback default; callers may perform region-specific operations separately
        // Let existing loadWorkers in workers.js handle actual population.
        if (window.workersInternal?.loadWorkers) {
            await window.workersInternal.loadWorkers();
            showToast('Workers refreshed', 'info');
        }
    } catch (e) {
        console.error('[worker-actions] refresh error', e);
        showToast('Failed to refresh workers', 'error');
    }
}
