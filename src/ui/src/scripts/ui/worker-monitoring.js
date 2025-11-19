// worker-monitoring.js
// Extracted monitoring tab logic

import * as systemApi from '../api/system.js';
import { escapeHtml } from '../components/escape.js';

export async function loadMonitoringTab() {
    const monitoringContent = document.getElementById('worker-details-monitoring');
    if (!monitoringContent) return;
    monitoringContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading monitoring status...</p></div>';
    try {
        const status = await systemApi.getWorkerMonitoringStatus();
        let html = `<div class='row mb-4'>
      <div class='col-md-6'><div class='card'><div class='card-body'>
        <h6 class='card-subtitle mb-2 text-muted'>Scheduler Status</h6>
        <p class='card-text'><strong>Running:</strong> <span class='badge ${status.scheduler_running ? 'bg-success' : 'bg-danger'}'>${status.scheduler_running ? 'Yes' : 'No'}</span></p>
        <p class='card-text'><strong>Status:</strong> <span class='badge ${status.status === 'active' ? 'bg-success' : status.status === 'inactive' ? 'bg-secondary' : 'bg-danger'}'>${escapeHtml(status.status)}</span></p>
      </div></div></div>
      <div class='col-md-6'><div class='card'><div class='card-body'>
        <h6 class='card-subtitle mb-2 text-muted'>Monitoring Jobs</h6>
        <p class='card-text'><strong>Active Jobs:</strong> ${status.monitoring_job_count || 0}</p>
      </div></div></div>
    </div>`;
        if (status.jobs && Array.isArray(status.jobs) && status.jobs.length) {
            html += `<h6 class='mb-3'>Active Monitoring Jobs</h6><div class='table-responsive'><table class='table table-sm table-hover'><thead><tr><th>Job ID</th><th>Name</th><th>Next Run</th></tr></thead><tbody>`;
            status.jobs.forEach(job => {
                html += `<tr><td><code class='small'>${escapeHtml(job.id)}</code></td><td>${escapeHtml(job.name)}</td><td>${escapeHtml(job.next_run_time || 'N/A')}</td></tr>`;
            });
            html += '</tbody></table></div>';
        }
        monitoringContent.innerHTML = html;
    } catch (error) {
        console.error('[worker-monitoring] Failed to load monitoring status:', error);
        monitoringContent.innerHTML = `<div class='alert alert-danger'><i class='bi bi-exclamation-circle'></i> ${escapeHtml(error.message || 'Failed to load monitoring status')}</div>`;
    }
}
