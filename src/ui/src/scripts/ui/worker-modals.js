// worker-modals.js
// Extracted modal setup & license/delete functionality

import * as workersApi from '../api/workers.js';
import { showToast } from './notifications.js';
import { isAdmin } from '../utils/roles.js';
import { renderLicenseRegistration, renderLicenseAuthorization, renderLicenseFeatures, renderLicenseTransport } from '../components/workerLicensePanel.js';
import { fetchWorkerDetails, removeWorker } from '../store/workerStore.js';
import * as bootstrap from 'bootstrap';

export function showLicenseModal(workerId, region) {
    const idEl = document.getElementById('license-worker-id');
    const regionEl = document.getElementById('license-worker-region');
    if (!idEl || !regionEl) {
        showToast('License form missing', 'error');
        return;
    }
    idEl.value = workerId;
    regionEl.value = region;
    new bootstrap.Modal(document.getElementById('registerLicenseModal')).show();
}

export async function showLicenseDetailsModal() {
    const modal = document.getElementById('workerDetailsModal');
    const workerId = modal?.dataset.workerId;
    const region = modal?.dataset.workerRegion;
    if (!workerId || !region) {
        showToast('No worker selected', 'error');
        return;
    }
    try {
        const worker = await fetchWorkerDetails(region, workerId);
        const licenseData = worker.cml_license_info;
        if (!licenseData) {
            showToast('No license information available', 'warning');
            return;
        }
        const licenseModalElement = document.getElementById('licenseDetailsModal');
        if (!licenseModalElement) {
            showToast('License modal missing', 'error');
            return;
        }
        const registrationContent = document.getElementById('license-registration-content');
        const authorizationContent = document.getElementById('license-authorization-content');
        const featuresContent = document.getElementById('license-features-content');
        const transportContent = document.getElementById('license-transport-content');
        if (!registrationContent || !authorizationContent || !featuresContent || !transportContent) {
            showToast('License modal content missing', 'error');
            return;
        }
        registrationContent.innerHTML = renderLicenseRegistration(licenseData.registration || {});
        authorizationContent.innerHTML = renderLicenseAuthorization(licenseData.authorization || {});
        featuresContent.innerHTML = renderLicenseFeatures(licenseData.features || []);
        transportContent.innerHTML = renderLicenseTransport(licenseData.transport || {}, licenseData.udi || {});
        new bootstrap.Modal(licenseModalElement).show();
    } catch (err) {
        console.error('[worker-modals] License details error:', err);
        showToast('Failed to load license details', 'error');
    }
}

export function setupDeleteWorkerModal() {
    const submitBtn = document.getElementById('submit-delete-worker-btn');
    if (!submitBtn) return;
    submitBtn.addEventListener('click', async () => {
        const workerId = document.getElementById('delete-worker-id')?.value;
        const region = document.getElementById('delete-worker-region')?.value;
        const terminateInstance = document.getElementById('delete-terminate-instance')?.checked || false;
        if (!workerId || !region) {
            showToast('Missing worker information', 'error');
            return;
        }
        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deleting...';
            await workersApi.deleteWorker(region, workerId, terminateInstance);
            const action = terminateInstance ? 'deleted and terminated' : 'deleted';
            showToast(`Worker ${action} successfully`, 'success');
            bootstrap.Modal.getInstance(document.getElementById('deleteWorkerModal'))?.hide();
            document.getElementById('delete-worker-form')?.reset();
            removeWorker(workerId);
        } catch (error) {
            console.error('[worker-modals] Delete error:', error);
            showToast(error.message || 'Failed to delete worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-trash"></i> Delete Worker';
        }
    });
}

export function showDeleteModal(workerId, region, name) {
    if (!isAdmin()) {
        showToast('Permission denied', 'error');
        return;
    }
    const idEl = document.getElementById('delete-worker-id');
    const regionEl = document.getElementById('delete-worker-region');
    const nameEl = document.getElementById('delete-worker-name');
    const terminateEl = document.getElementById('delete-terminate-instance');
    if (!idEl || !regionEl || !nameEl || !terminateEl) {
        showToast('Delete modal missing elements', 'error');
        return;
    }
    idEl.value = workerId;
    regionEl.value = region;
    nameEl.textContent = name;
    terminateEl.checked = false;
    new bootstrap.Modal(document.getElementById('deleteWorkerModal')).show();
}

export function setupLicenseModal() {
    const form = document.getElementById('register-license-form');
    const submitBtn = document.getElementById('submit-register-license-btn');
    if (!form || !submitBtn) return;
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
            bootstrap.Modal.getInstance(document.getElementById('registerLicenseModal'))?.hide();
            form.reset();
            setTimeout(() => window.workersApp.refreshWorkers?.(), 1000);
        } catch (error) {
            console.error('[worker-modals] License register error:', error);
            showToast(error.message || 'Failed to register license', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-key"></i> Register License';
        }
    });
}

export function setupCreateWorkerModal() {
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
            const data = { name, instance_type: instanceType };
            if (ami) data.ami_id = ami;
            if (cmlVersion) data.cml_version = cmlVersion;
            await workersApi.createWorker(region, data);
            showToast('Worker creation initiated', 'success');
            bootstrap.Modal.getInstance(document.getElementById('createWorkerModal'))?.hide();
            document.getElementById('create-worker-form')?.reset();
            setTimeout(() => window.workersApp.refreshWorkers?.(), 2000);
        } catch (error) {
            console.error('[worker-modals] Create worker error:', error);
            showToast(error.message || 'Failed to create worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-plus-circle"></i> Create Worker';
        }
    });
}

export function setupImportWorkerModal() {
    const submitBtn = document.getElementById('submit-import-worker-btn');
    if (!submitBtn) return;

    const byInstanceRadio = document.getElementById('import-by-instance');
    const byAmiRadio = document.getElementById('import-by-ami');
    const instanceGroup = document.getElementById('instance-id-group');
    const amiGroup = document.getElementById('ami-name-group');
    const nameGroup = document.getElementById('worker-name-group');
    const importAllCheckbox = document.getElementById('import-all-instances');

    function updateImportModeUI() {
        const byInstance = byInstanceRadio?.checked;
        if (byInstance) {
            instanceGroup && (instanceGroup.style.display = 'block');
            amiGroup && (amiGroup.style.display = 'none');
            nameGroup && (nameGroup.style.display = 'block');
        } else {
            instanceGroup && (instanceGroup.style.display = 'none');
            amiGroup && (amiGroup.style.display = 'block');
            if (importAllCheckbox?.checked) {
                nameGroup && (nameGroup.style.display = 'none');
            } else {
                nameGroup && (nameGroup.style.display = 'block');
            }
        }
    }

    byInstanceRadio?.addEventListener('change', updateImportModeUI);
    byAmiRadio?.addEventListener('change', updateImportModeUI);
    importAllCheckbox?.addEventListener('change', updateImportModeUI);
    // Initial state
    updateImportModeUI();

    submitBtn.addEventListener('click', async () => {
        const region = document.getElementById('import-region')?.value; // corrected ID
        const importMethodInstance = byInstanceRadio?.checked;
        const instanceId = document.getElementById('import-instance-id')?.value?.trim();
        const amiName = document.getElementById('import-ami-name')?.value?.trim();
        const name = document.getElementById('import-worker-name')?.value?.trim();
        const importAll = importAllCheckbox?.checked || false;

        // Validation
        if (!region) {
            showToast('Please select a region', 'error');
            return;
        }
        if (importMethodInstance) {
            if (!instanceId) {
                showToast('Instance ID required', 'error');
                return;
            }
        } else {
            // AMI mode
            if (!amiName) {
                showToast('AMI name pattern required', 'error');
                return;
            }
        }
        if (importMethodInstance && !name) {
            showToast('Worker name required for single instance import', 'error');
            return;
        }
        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Importing...';
            const data = {};
            if (importMethodInstance) {
                data.aws_instance_id = instanceId;
                if (name) data.name = name;
            } else {
                data.ami_name = amiName;
                if (importAll) {
                    data.import_all = true;
                } else if (name) {
                    data.name = name;
                }
            }
            await workersApi.importWorker(region, data);
            showToast(importAll ? 'Bulk import initiated' : 'Worker import initiated', 'success');
            bootstrap.Modal.getInstance(document.getElementById('importWorkerModal'))?.hide();
            document.getElementById('import-worker-form')?.reset();
            setTimeout(() => window.workersApp.refreshWorkers?.(), 2000);
        } catch (error) {
            console.error('[worker-modals] Import worker error:', error);
            showToast(error.message || 'Failed to import worker', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="bi bi-upload"></i> Import Worker';
            updateImportModeUI(); // reset visibility after form reset
        }
    });
}
