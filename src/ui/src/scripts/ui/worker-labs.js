// worker-labs.js
// Extracted labs tab logic and lab control handlers.

import * as workersApi from '../api/workers.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';
import { showToast } from './notifications.js';
import { showConfirm } from '../components/modals.js';
import { escapeHtml } from '../components/escape.js';
import * as bootstrap from 'bootstrap';

let getCurrentWorkerDetailsRef = () => null;

export function bindLabsDependencies({ getCurrentWorkerDetails }) {
    getCurrentWorkerDetailsRef = getCurrentWorkerDetails || (() => null);
}

function confirmDialog(title, message, details, type = 'warning') {
    return new Promise(resolve => {
        const iconClass = type === 'danger' ? 'bi bi-exclamation-triangle-fill text-danger me-2' : 'bi bi-exclamation-triangle text-warning me-2';
        const actionClass = type === 'danger' ? 'btn-danger' : 'btn-warning';
        let confirmed = false;
        const modalEl = document.getElementById('confirmModal');
        if (modalEl) {
            const handleHidden = () => {
                // Resolve negative path if not confirmed
                if (!confirmed) resolve(false);
                modalEl.removeEventListener('hidden.bs.modal', handleHidden);
                // Always restore worker details modal opacity
                const detailsModal = document.getElementById('workerDetailsModal');
                if (detailsModal) detailsModal.style.opacity = '1';
                // Backdrop cleanup: remove duplicate backdrops or stale overlay
                const backdrops = Array.from(document.querySelectorAll('.modal-backdrop'));
                const openModals = Array.from(document.querySelectorAll('.modal.show'));
                if (detailsModal && detailsModal.classList.contains('show')) {
                    // Keep only one backdrop for the details modal
                    if (backdrops.length > 1) {
                        backdrops.forEach((bd, i) => {
                            if (i < backdrops.length - 1) bd.parentNode?.removeChild(bd);
                        });
                    }
                    backdrops.forEach(bd => {
                        bd.style.zIndex = '';
                    });
                } else {
                    // If no modals remain, remove all backdrops and body classes
                    if (openModals.length === 0) {
                        backdrops.forEach(bd => bd.parentNode?.removeChild(bd));
                        document.body.classList.remove('modal-open');
                        document.body.style.removeProperty('padding-right');
                    }
                }
            };
            modalEl.addEventListener('hidden.bs.modal', handleHidden);
            modalEl.style.zIndex = 2000;
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.style.zIndex = 1990;
        }
        showConfirm(
            title,
            message,
            async () => {
                confirmed = true;
                resolve(true);
            },
            { actionLabel: 'Confirm', actionClass, iconClass, detailsHtml: escapeHtml(details) }
        );
        const workerDetailsModal = bootstrap.Modal.getInstance(document.getElementById('workerDetailsModal'));
        if (workerDetailsModal) document.getElementById('workerDetailsModal').style.opacity = '0.6';
    });
}

export async function loadLabsTab() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal?.dataset.workerId;
    const region = modal?.dataset.workerRegion;
    const labsContent = document.getElementById('worker-details-labs');
    if (!labsContent) return;

    if (!workerId || !region) {
        labsContent.innerHTML = '<div class="alert alert-warning">No worker selected</div>';
        return;
    }
    labsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading labs...</p></div>';
    try {
        const labs = await workersApi.getWorkerLabs(region, workerId);
        if (!Array.isArray(labs) || labs.length === 0) {
            labsContent.innerHTML = '<div class="alert alert-info"><i class="bi bi-folder2-open"></i> No labs found on this worker</div>';
            return;
        }
        let html = '<div class="accordion accordion-flush" id="labs-accordion">';
        labs.forEach((lab, index) => {
            const collapseId = `lab-collapse-${index}`;
            const headingId = `lab-heading-${index}`;
            let stateBadge = '';
            switch (lab.state) {
                case 'STARTED':
                    stateBadge = '<span class="badge bg-success">Started</span>';
                    break;
                case 'STOPPED':
                    stateBadge = '<span class="badge bg-secondary">Stopped</span>';
                    break;
                case 'DEFINED_ON_CORE':
                    stateBadge = '<span class="badge bg-info">Defined</span>';
                    break;
                default:
                    stateBadge = `<span class="badge bg-secondary">${escapeHtml(lab.state)}</span>`;
            }
            const created = lab.created ? formatDateWithRelative(lab.created) : 'N/A';
            const modified = lab.modified ? formatDateWithRelative(lab.modified) : 'N/A';
            const isStarted = lab.state === 'STARTED';
            html += `
        <div class="accordion-item">
          <h2 class="accordion-header" id="${headingId}">
            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}">
              <div class="d-flex justify-content-between align-items-center w-100 pe-3">
                <div><i class="bi bi-folder2-open text-primary me-2"></i><strong>${escapeHtml(lab.title || lab.id)}</strong></div>
                <div class="d-flex gap-2 align-items-center">
                  ${stateBadge}
                  <span class="badge bg-light text-dark"><i class="bi bi-diagram-3"></i> ${lab.node_count || 0} nodes</span>
                  <span class="badge bg-light text-dark"><i class="bi bi-arrow-left-right"></i> ${lab.link_count || 0} links</span>
                </div>
              </div>
            </button>
          </h2>
          <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#labs-accordion">
            <div class="accordion-body">
              <div class="row g-3">
                <div class="col-md-6">
                  <div class="card h-100"><div class="card-body">
                    <h6 class="card-subtitle mb-3 text-muted"><i class="bi bi-info-circle"></i> Lab Information</h6>
                    <dl class="row mb-0">
                      <dt class="col-sm-4">Lab ID:</dt><dd class="col-sm-8"><code>${escapeHtml(lab.id)}</code></dd>
                      <dt class="col-sm-4">Title:</dt><dd class="col-sm-8">${escapeHtml(lab.title || 'N/A')}</dd>
                      <dt class="col-sm-4">Owner:</dt><dd class="col-sm-8">${escapeHtml(lab.owner_username || 'N/A')}${lab.owner ? `<br><small class='text-muted'>${escapeHtml(lab.owner)}</small>` : ''}</dd>
                      <dt class="col-sm-4">State:</dt><dd class="col-sm-8">${stateBadge}</dd>
                    </dl>
                  </div></div>
                </div>
                <div class="col-md-6">
                  <div class="card h-100"><div class="card-body">
                    <h6 class="card-subtitle mb-3 text-muted"><i class="bi bi-clock-history"></i> Timestamps</h6>
                    <dl class="row mb-0">
                      <dt class="col-sm-4">Created:</dt><dd class="col-sm-8">${created}</dd>
                      <dt class="col-sm-4">Modified:</dt><dd class="col-sm-8">${modified}</dd>
                      <dt class="col-sm-4">Nodes:</dt><dd class="col-sm-8"><span class="badge bg-primary">${lab.node_count || 0}</span></dd>
                      <dt class="col-sm-4">Links:</dt><dd class="col-sm-8"><span class="badge bg-primary">${lab.link_count || 0}</span></dd>
                    </dl>
                  </div></div>
                </div>
                ${
                    lab.description
                        ? `<div class='col-12'><div class='card'><div class='card-body'><h6 class='card-subtitle mb-2 text-muted'><i class='bi bi-file-text'></i> Description</h6><p class='mb-0'>${escapeHtml(lab.description)}</p></div></div></div>`
                        : ''
                }
                ${
                    lab.notes
                        ? `<div class='col-12'><div class='card'><div class='card-body'><h6 class='card-subtitle mb-2 text-muted'><i class='bi bi-sticky'></i> Notes</h6><pre class='mb-0' style='white-space: pre-wrap;'>${escapeHtml(
                              lab.notes
                          )}</pre></div></div></div>`
                        : ''
                }
                ${
                    lab.groups && lab.groups.length
                        ? `<div class='col-12'><div class='card'><div class='card-body'><h6 class='card-subtitle mb-2 text-muted'><i class='bi bi-people'></i> Groups</h6><div class='d-flex flex-wrap gap-1'>${lab.groups
                              .map(g => `<span class='badge bg-secondary'>${escapeHtml(g)}</span>`)
                              .join('')}</div></div></div></div>`
                        : ''
                }
                <div class='col-12'><div class='card'><div class='card-body'>
                  <h6 class='card-subtitle mb-3 text-muted'><i class='bi bi-gear'></i> Lab Controls</h6>
                  <div class='btn-group' role='group'>
                    <button type='button' class='btn btn-success ${isStarted ? 'disabled' : ''}' onclick="window.workersApp.handleStartLab('${region}', '${workerId}', '${escapeHtml(lab.id)}')" ${
                        isStarted ? 'disabled' : ''
                    }><i class='bi bi-play-fill'></i> Start Lab</button>
                    <button type='button' class='btn btn-warning ${!isStarted ? 'disabled' : ''}' onclick="window.workersApp.handleStopLab('${region}', '${workerId}', '${escapeHtml(lab.id)}', '${escapeHtml(lab.title || lab.id)}')" ${
                        !isStarted ? 'disabled' : ''
                    }><i class='bi bi-stop-fill'></i> Stop Lab</button>
                    <button type='button' class='btn btn-danger' onclick="window.workersApp.handleWipeLab('${region}', '${workerId}', '${escapeHtml(lab.id)}', '${escapeHtml(lab.title || lab.id)}')"><i class='bi bi-trash-fill'></i> Wipe Lab</button>
                  </div>
                  <div class='mt-2'><small class='text-muted'><i class='bi bi-info-circle'></i> Stop and Wipe operations require confirmation</small></div>
                </div></div></div>
              </div>
            </div>
          </div>
        </div>`;
        });
        html += '</div>';
        labsContent.innerHTML = html;
        initializeDateTooltips();
    } catch (error) {
        labsContent.innerHTML = `<div class='alert alert-danger'><i class='bi bi-exclamation-triangle'></i> Failed to load labs: ${escapeHtml(error.message)}</div>`;
    }
}

export async function handleStartLab(region, workerId, labId) {
    try {
        showToast('Starting lab...', 'info');
        await workersApi.startLab(region, workerId, labId);
        showToast('Lab started successfully', 'success');
        await loadLabsTab();
        // Poll for state transition if backend applies change asynchronously
        await waitForLabState(region, workerId, labId, 'STARTED', 5000).catch(() => {});
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to start lab: ${error.message}`, 'danger');
    }
}

export async function handleStopLab(region, workerId, labId, labTitle) {
    const confirmed = await confirmDialog('Stop Lab', `Are you sure you want to stop lab "${labTitle}"?`, 'This will stop all running nodes in the lab.', 'warning');
    if (!confirmed) return;
    try {
        showToast('Stopping lab...', 'info');
        await workersApi.stopLab(region, workerId, labId);
        showToast('Lab stopped successfully', 'success');
        await loadLabsTab();
        await waitForLabState(region, workerId, labId, 'STOPPED', 5000).catch(() => {});
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to stop lab: ${error.message}`, 'danger');
    }
}

export async function handleWipeLab(region, workerId, labId, labTitle) {
    const confirmed = await confirmDialog('Wipe Lab', `Are you sure you want to wipe lab "${labTitle}"?`, 'This will perform a factory reset on all nodes. This action cannot be undone!', 'danger');
    if (!confirmed) return;
    try {
        showToast('Wiping lab...', 'info');
        await workersApi.wipeLab(region, workerId, labId);
        showToast('Lab wiped successfully', 'success');
        await loadLabsTab();
        await waitForLabState(region, workerId, labId, 'DEFINED_ON_CORE', 7000).catch(() => {});
        await loadLabsTab();
    } catch (error) {
        showToast(`Failed to wipe lab: ${error.message}`, 'danger');
    }
}

// Helper: Poll labs until a specific lab reaches desired state (best-effort)
async function waitForLabState(region, workerId, labId, desiredState, timeoutMs = 5000, pollIntervalMs = 600) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        try {
            const labs = await workersApi.getWorkerLabs(region, workerId);
            const target = labs.find(l => l.id === labId);
            if (target && target.state === desiredState) return true;
        } catch (e) {
            // swallow transient errors
        }
        await new Promise(r => setTimeout(r, pollIntervalMs));
    }
    throw new Error('waitForLabState timeout');
}
