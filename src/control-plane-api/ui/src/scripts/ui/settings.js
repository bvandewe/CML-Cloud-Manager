import { apiRequest } from '../api/client.js';
import * as bootstrap from 'bootstrap';

export async function initializeSettingsView() {
    console.log('[Settings] Initializing view');

    const saveBtn = document.getElementById('save-settings-btn');
    if (saveBtn) {
        // Remove existing listeners to prevent duplicates if re-initialized
        const newBtn = saveBtn.cloneNode(true);
        saveBtn.parentNode.replaceChild(newBtn, saveBtn);
        newBtn.addEventListener('click', saveSettings);
    }

    await loadSettings();
}

async function loadSettings() {
    try {
        const response = await apiRequest('/api/settings');
        const settings = await response.json();
        populateForms(settings);
    } catch (error) {
        console.error('[Settings] Failed to load settings:', error);
        // alert('Failed to load settings');
    }
}

function populateForms(settings) {
    // Worker Provisioning
    if (settings.worker_provisioning) {
        const form = document.getElementById('worker-provisioning-form');
        if (form) {
            form.elements['ami_name_default'].value = settings.worker_provisioning.ami_name_default || '';
            form.elements['instance_type'].value = settings.worker_provisioning.instance_type || '';
            form.elements['security_group_ids'].value = (settings.worker_provisioning.security_group_ids || []).join(', ');
            form.elements['subnet_id'].value = settings.worker_provisioning.subnet_id || '';
        }
    }

    // Monitoring & Idle Detection
    const monitoringForm = document.getElementById('monitoring-form');
    if (monitoringForm) {
        if (settings.monitoring) {
            monitoringForm.elements['worker_metrics_poll_interval_seconds'].value = settings.monitoring.worker_metrics_poll_interval_seconds || 300;
        }
        if (settings.idle_detection) {
            monitoringForm.elements['enabled'].checked = settings.idle_detection.enabled;
            monitoringForm.elements['timeout_minutes'].value = settings.idle_detection.timeout_minutes || 60;
        }
    }
}

async function saveSettings() {
    const workerForm = document.getElementById('worker-provisioning-form');
    const monitoringForm = document.getElementById('monitoring-form');

    const workerProvisioning = {
        ami_name_default: workerForm.elements['ami_name_default'].value,
        instance_type: workerForm.elements['instance_type'].value,
        security_group_ids: workerForm.elements['security_group_ids'].value
            .split(',')
            .map(s => s.trim())
            .filter(s => s),
        subnet_id: workerForm.elements['subnet_id'].value || null,
    };

    const monitoring = {
        worker_metrics_poll_interval_seconds: parseInt(monitoringForm.elements['worker_metrics_poll_interval_seconds'].value),
    };

    const idleDetection = {
        enabled: monitoringForm.elements['enabled'].checked,
        timeout_minutes: parseInt(monitoringForm.elements['timeout_minutes'].value),
    };

    const payload = {
        worker_provisioning: workerProvisioning,
        monitoring: monitoring,
        idle_detection: idleDetection,
    };

    try {
        await apiRequest('/api/settings', {
            method: 'PUT',
            body: JSON.stringify(payload),
        });

        const modalEl = document.getElementById('settingsSavedModal');
        if (modalEl) {
            new bootstrap.Modal(modalEl).show();
        } else {
            alert('Settings saved successfully');
        }
    } catch (error) {
        console.error('[Settings] Failed to save settings:', error);

        const alertModalEl = document.getElementById('alertModal');
        if (alertModalEl) {
            document.getElementById('alert-modal-title').textContent = 'Error';
            document.getElementById('alert-modal-message').textContent = 'Failed to save settings';
            new bootstrap.Modal(alertModalEl).show();
        } else {
            alert('Failed to save settings');
        }
    }
}
