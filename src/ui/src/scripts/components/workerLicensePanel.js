// workerLicensePanel.js
// Pure rendering helpers for worker license details modal tabs.

export function renderLicenseRegistration(reg) {
    if (!reg) reg = {};
    const status = reg.status || 'UNKNOWN';
    const statusBadge = status === 'COMPLETED' ? 'success' : status === 'FAILED' ? 'danger' : 'warning';
    const registerTime = reg.register_time || {};
    const renewTime = reg.renew_time || {};
    return `
    <div class="card">
      <div class="card-body">
        <div class="row mb-3">
          <div class="col-md-6"><h6 class="text-muted mb-2">Status</h6><span class="badge bg-${statusBadge} fs-6">${status}</span></div>
          <div class="col-md-6"><h6 class="text-muted mb-2">Expires</h6><p class="mb-0">${reg.expires || 'N/A'}</p></div>
        </div>
        <div class="row mb-3">
          <div class="col-md-6"><h6 class="text-muted mb-2">Smart Account</h6><p class="mb-0">${reg.smart_account || 'N/A'}</p></div>
          <div class="col-md-6"><h6 class="text-muted mb-2">Virtual Account</h6><p class="mb-0">${reg.virtual_account || 'N/A'}</p></div>
        </div>
        ${registerTime.attempted || registerTime.succeeded ? renderTimeBlock('Register Time', registerTime) : ''}
        ${renewTime.scheduled || renewTime.attempted ? renderTimeBlock('Renew Time', renewTime) : ''}
      </div>
    </div>`;
}

function renderTimeBlock(title, t) {
    return `
    <div class="mt-4">
      <h6 class="text-muted mb-3">${title}</h6>
      <table class="table table-sm table-borderless">
        <tr><td class="text-muted" style="width:40%">Scheduled:</td><td>${t.scheduled || 'N/A'}</td></tr>
        <tr><td class="text-muted">Attempted:</td><td>${t.attempted || 'N/A'}</td></tr>
        <tr><td class="text-muted">Succeeded:</td><td>${t.succeeded || 'N/A'}</td></tr>
        ${t.status ? `<tr><td class="text-muted">Status:</td><td><span class="badge bg-${t.status === 'SUCCEEDED' ? 'success' : 'secondary'}">${t.status}</span></td></tr>` : ''}
        ${t.failure ? `<tr><td class="text-muted">Failure:</td><td>${t.failure}</td></tr>` : ''}
      </table>
    </div>`;
}

export function renderLicenseAuthorization(auth) {
    if (!auth) auth = {};
    const status = auth.status || 'UNKNOWN';
    const statusBadge = status === 'IN_COMPLIANCE' ? 'success' : status === 'OUT_OF_COMPLIANCE' ? 'danger' : 'warning';
    const renewTime = auth.renew_time || {};
    return `
    <div class="card">
      <div class="card-body">
        <div class="row mb-3">
          <div class="col-md-6"><h6 class="text-muted mb-2">Status</h6><span class="badge bg-${statusBadge} fs-6">${status.replace('_', ' ')}</span></div>
          <div class="col-md-6"><h6 class="text-muted mb-2">Expires</h6><p class="mb-0">${auth.expires || 'N/A'}</p></div>
        </div>
        ${renewTime.scheduled || renewTime.attempted ? renderTimeBlock('Renew Time', renewTime) : ''}
      </div>
    </div>`;
}

export function renderLicenseFeatures(features) {
    if (!features || features.length === 0) {
        return '<div class="alert alert-info"><i class="bi bi-info-circle"></i> No features available</div>';
    }
    return `<div class="table-responsive"><table class="table table-hover"><thead><tr><th>Feature Name</th><th>Status</th><th>In Use</th><th>Range</th><th>Version</th></tr></thead><tbody>${features
        .map(f => {
            const badge = f.status === 'IN_COMPLIANCE' ? 'success' : f.status === 'INIT' ? 'secondary' : 'warning';
            const range = f.min !== undefined && f.max !== undefined ? `${f.min} - ${f.max}` : 'N/A';
            return `<tr><td><strong>${f.name || 'Unknown'}</strong>${f.description ? `<br><small class='text-muted'>${f.description}</small>` : ''}</td><td><span class='badge bg-${badge}'>${f.status || 'N/A'}</span></td><td>${
                f.in_use !== undefined ? f.in_use : 'N/A'
            }</td><td>${range}</td><td>${f.version || 'N/A'}</td></tr>`;
        })
        .join('')}</tbody></table></div>`;
}

export function renderLicenseTransport(transport, udi) {
    transport = transport || {};
    udi = udi || {};
    return `
    <div class="card mb-3"><div class="card-header bg-light"><h6 class="mb-0"><i class="bi bi-hdd-network me-2"></i>Smart Software Manager (SSM)</h6></div><div class="card-body"><table class="table table-sm table-borderless"><tr><td class="text-muted" style="width:30%">SSMS URL:</td><td class="font-monospace small">${
        transport.ssms || 'N/A'
    }</td></tr><tr><td class="text-muted">Default SSMS:</td><td class="font-monospace small">${transport.default_ssms || 'N/A'}</td></tr>${
        transport.proxy && (transport.proxy.server || transport.proxy.port) ? `<tr><td class='text-muted'>Proxy:</td><td>${transport.proxy.server || 'None'}${transport.proxy.port ? ':' + transport.proxy.port : ''}</td></tr>` : ''
    }</table></div></div><div class="card"><div class="card-header bg-light"><h6 class="mb-0"><i class="bi bi-fingerprint me-2"></i>Unique Device Identifier (UDI)</h6></div><div class="card-body"><table class="table table-sm table-borderless"><tr><td class="text-muted" style="width:30%">Hostname:</td><td>${
        udi.hostname || 'N/A'
    }</td></tr><tr><td class="text-muted">Product UUID:</td><td class="font-monospace small">${udi.product_uuid || 'N/A'}</td></tr></table></div></div>`;
}
