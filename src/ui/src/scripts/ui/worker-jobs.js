// worker-jobs.js
// Extracted jobs tab logic

import * as systemApi from '../api/system.js';
import { showToast } from './notifications.js';
import { escapeHtml } from '../components/escape.js';

export async function loadJobsTab() {
    const jobsContent = document.getElementById('worker-details-jobs');
    if (!jobsContent) return;
    jobsContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading scheduler jobs...</p></div>';
    try {
        const jobs = await systemApi.getSchedulerJobs();
        if (!Array.isArray(jobs) || jobs.length === 0) {
            jobsContent.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle"></i> No scheduler jobs found</div>';
            return;
        }
        let html = '<div class="table-responsive"><table class="table table-hover"><thead><tr><th>Job ID</th><th>Command</th><th>Next Run</th><th>Trigger</th><th>Status</th></tr></thead><tbody>';
        jobs.forEach(job => {
            const nextRun = job.next_run_time || 'N/A';
            const statusBadge = job.pending ? '<span class="badge bg-warning">Pending</span>' : '<span class="badge bg-success">Scheduled</span>';
            html += `<tr><td><code class='small'>${escapeHtml(job.id)}</code></td><td>${escapeHtml(job.command || job.name || 'Unknown')}</td><td>${escapeHtml(nextRun)}</td><td><small class='text-muted'>${escapeHtml(
                job.trigger || 'N/A'
            )}</small></td><td>${statusBadge}</td></tr>`;
        });
        html += '</tbody></table></div>';
        jobsContent.innerHTML = html;
    } catch (error) {
        console.error('[worker-jobs] Failed to load scheduler jobs:', error);
        jobsContent.innerHTML = `<div class='alert alert-danger'><i class='bi bi-exclamation-circle'></i> ${escapeHtml(error.message || 'Failed to load scheduler jobs')}</div>`;
    }
}
