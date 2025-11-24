/**
 * workerOverview.js
 * Pure rendering for worker AWS overview section.
 */

import { formatDateWithRelative } from '../utils/dates.js';
import { escapeHtml } from './escape.js';
import { isAdmin } from '../utils/roles.js';
import { getStatusBadgeClass, getServiceStatusBadgeClass } from './status-badges.js';

export function renderWorkerOverview(worker) {
    if (!worker) return '<div class="alert alert-warning">Worker data unavailable</div>';
    return `
    <div class="row" aria-label="Worker basic information" role="group">
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">Basic Information</h5>
        <table class="table table-sm table-borderless" aria-label="Basic worker attributes">
          <tr><td class="text-muted" width="40%">Name:</td><td><strong>${escapeHtml(worker.name || 'N/A')}</strong></td></tr>
          <tr><td class="text-muted">Worker ID:</td><td><code class="small">${worker.id}</code></td></tr>
          <tr><td class="text-muted">Instance ID:</td><td>${
              worker.aws_instance_id
                  ? `<code class="small">${worker.aws_instance_id}</code> <a href="https://${worker.aws_region}.console.aws.amazon.com/ec2/home?region=${worker.aws_region}#InstanceDetails:instanceId=${worker.aws_instance_id}" target="_blank" class="text-decoration-none ms-1" title="View in AWS Console" aria-label="Open in AWS Console"><i class="bi bi-box-arrow-up-right text-primary"></i></a>`
                  : '<span class="text-muted">N/A</span>'
          }</td></tr>
          <tr><td class="text-muted">Region:</td><td><span class="badge bg-secondary">${worker.aws_region}</span></td></tr>
          <tr><td class="text-muted">Instance Type:</td><td><span class="badge bg-info">${worker.instance_type}</span></td></tr>
          <tr><td class="text-muted">Status:</td><td><span class="badge ${getStatusBadgeClass(worker.status)}">${worker.status}</span>
            ${
                worker.status === 'pending' && worker.start_initiated_at
                    ? (() => {
                          try {
                              const startedMs = Date.parse(worker.start_initiated_at);
                              const diffSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
                              const m = Math.floor(diffSec / 60);
                              const s = diffSec % 60;
                              return `<div class='small text-muted mt-1 transition-duration' data-init-ts='${worker.start_initiated_at}' data-type='start'>Starting (<span class='elapsed'>${m}m ${s}s</span>)</div>`;
                          } catch (_) {
                              return `<div class='small text-muted mt-1'>Starting...</div>`;
                          }
                      })()
                    : ''
            }
            ${
                worker.status === 'stopping' && worker.stop_initiated_at
                    ? (() => {
                          try {
                              const stopMs = Date.parse(worker.stop_initiated_at);
                              const diffSec = Math.max(0, Math.floor((Date.now() - stopMs) / 1000));
                              const m = Math.floor(diffSec / 60);
                              const s = diffSec % 60;
                              return `<div class='small text-muted mt-1 transition-duration' data-init-ts='${worker.stop_initiated_at}' data-type='stop'>Stopping (<span class='elapsed'>${m}m ${s}s</span>)</div>`;
                          } catch (_) {
                              return `<div class='small text-muted mt-1'>Stopping...</div>`;
                          }
                      })()
                    : ''
            }
          </td></tr>
                    <tr><td class="text-muted">Service Status:</td><td><span class="badge ${getServiceStatusBadgeClass(worker.service_status)}">${worker.service_status}</span></td></tr>
        </table>
      </div>
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">AMI Information</h5>
        <table class="table table-sm table-borderless" aria-label="AMI information">
          <tr><td class="text-muted" width="40%">AMI ID:</td><td>${
              worker.ami_id
                  ? `<code class="small">${worker.ami_id}</code> <a href="https://${worker.aws_region}.console.aws.amazon.com/ec2/home?region=${worker.aws_region}#ImageDetails:imageId=${worker.ami_id}" target="_blank" class="text-decoration-none ms-1" title="View AMI in AWS Console" aria-label="Open AMI in AWS Console"><i class="bi bi-box-arrow-up-right text-primary"></i></a>`
                  : '<span class="text-muted">N/A</span>'
          }</td></tr>
          <tr><td class="text-muted">AMI Name:</td><td>${escapeHtml(worker.ami_name || 'N/A')}</td></tr>
          <tr><td class="text-muted">Description:</td><td>${escapeHtml(worker.ami_description || 'N/A')}</td></tr>
          <tr><td class="text-muted">Created:</td><td>${worker.ami_creation_date ? formatDateWithRelative(worker.ami_creation_date) : '<span class="text-muted">N/A</span>'}</td></tr>
        </table>
      </div>
    </div>
    <div class="row mt-3" aria-label="Network information" role="group">
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">Network</h5>
        <table class="table table-sm table-borderless" aria-label="Network attributes">
          <tr><td class="text-muted" width="40%">Public IP:</td><td>${worker.public_ip || '<span class="text-muted">N/A</span>'}</td></tr>
          <tr><td class="text-muted">Private IP:</td><td>${worker.private_ip || '<span class="text-muted">N/A</span>'}</td></tr>
          <tr><td class="text-muted">HTTPS Endpoint:</td><td>${
              worker.https_endpoint
                  ? `<a href="${worker.https_endpoint}" target="_blank" class="text-decoration-none" aria-label="Open HTTPS endpoint">${worker.https_endpoint} <i class="bi bi-box-arrow-up-right"></i></a>`
                  : '<span class="text-muted">N/A</span>'
          }</td></tr>
        </table>
      </div>
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">Tags</h5>
        <div id="worker-tags-section" aria-label="AWS EC2 Instance Tags">
          <div id="worker-tags-list" class="mb-2">
            ${(() => {
                const tags = worker.aws_tags || {};
                const keys = Object.keys(tags);
                if (!keys.length) return '<span class="text-muted">No tags found</span>';
                return keys
                    .map(
                        k =>
                            `<span class="badge bg-light text-dark border me-1 mb-1 tag-item" data-tag-key="${escapeHtml(k)}" title="${escapeHtml(k)}: ${escapeHtml(tags[k])}">${escapeHtml(k)}: ${escapeHtml(tags[k])}${
                                isAdmin()
                                    ? ' <button type="button" class="btn btn-sm btn-outline-danger ms-1 p-0 px-1 remove-tag-btn" data-remove-tag="' + escapeHtml(k) + '" aria-label="Remove tag ' + escapeHtml(k) + '"><i class="bi bi-x"></i></button>'
                                    : ''
                            }</span>`
                    )
                    .join('');
            })()}
          </div>
          ${
              isAdmin()
                  ? `<form id="add-tag-form" class="row g-2" autocomplete="off" aria-label="Add tag form">
            <div class="col-5"><input type="text" class="form-control form-control-sm" id="new-tag-key" placeholder="Key" aria-label="Tag key" required maxlength="128"></div>
            <div class="col-5"><input type="text" class="form-control form-control-sm" id="new-tag-value" placeholder="Value" aria-label="Tag value" required maxlength="256"></div>
            <div class="col-2 d-grid"><button type="submit" class="btn btn-sm btn-outline-success" id="add-tag-btn" aria-label="Add tag"><i class="bi bi-plus"></i> Add</button></div>
            <div class="col-12"><div id="add-tag-feedback" class="small text-muted" aria-live="polite"></div></div>
          </form>`
                  : ''
          }
        </div>
      </div>
    </div>
    <div class="row mt-3" aria-label="Lifecycle information" role="group">
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">Lifecycle</h5>
        <table class="table table-sm table-borderless" aria-label="Lifecycle timestamps">
          <tr><td class="text-muted" width="40%"><i class="bi bi-plus-circle"></i> Created:</td><td>${formatDateWithRelative(worker.created_at)}</td></tr>
          <tr><td class="text-muted"><i class="bi bi-arrow-repeat"></i> Updated:</td><td>${formatDateWithRelative(worker.updated_at)}</td></tr>
          <tr><td class="text-muted"><i class="bi bi-clock-history"></i> Last Refreshed:</td><td>${worker.last_refreshed_at ? formatDateWithRelative(worker.last_refreshed_at) : '<span class="text-muted">N/A</span>'}</td></tr>
          <tr><td class="text-muted"><i class="bi bi-hourglass-split"></i> Next Refresh:</td><td>${worker.next_refresh_at ? formatDateWithRelative(worker.next_refresh_at) : '<span class="text-muted">N/A</span>'}</td></tr>
          <tr><td class="text-muted"><i class="bi bi-x-circle"></i> Terminated:</td><td>${worker.terminated_at ? formatDateWithRelative(worker.terminated_at) : '<span class="text-muted">N/A</span>'}</td></tr>
        </table>
      </div>
      <div class="col-md-6">
        <h5 class="border-bottom pb-2 mb-3">Activity & Usage</h5>
        <table class="table table-sm table-borderless" aria-label="Activity and usage statistics">
          <tr><td class="text-muted" width="40%">Pause Count:</td><td>${worker.pause_count || 0}</td></tr>
          <tr><td class="text-muted">Resume Count:</td><td>${worker.resume_count || 0}</td></tr>
          <tr><td class="text-muted">Idle Detection:</td><td>${worker.is_idle_detection_enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>'}</td></tr>
          <tr><td class="text-muted">Last Activity:</td><td>${worker.last_activity_at ? formatDateWithRelative(worker.last_activity_at) : '<span class="text-muted">N/A</span>'}</td></tr>
        </table>
      </div>
    </div>
  `;
}
