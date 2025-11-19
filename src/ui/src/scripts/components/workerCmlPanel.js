// workerCmlPanel.js
// Pure rendering helpers for worker CML system information and labs summary.

export function renderCmlSystemInfo(info) {
    info = info || {};
    const version = info.version || 'N/A';
    const build = info.build_number || 'N/A';
    const license = info.license_model || 'N/A';
    const edition = info.edition || 'N/A';
    return `
    <div class="card mb-3">
      <div class="card-header bg-light"><h6 class="mb-0"><i class="bi bi-info-circle me-2"></i>CML System Information</h6></div>
      <div class="card-body">
        <div class="row mb-2"><div class="col-md-4"><span class="text-muted">Version</span><div>${version}</div></div><div class="col-md-4"><span class="text-muted">Build</span><div>${build}</div></div><div class="col-md-4"><span class="text-muted">Edition</span><div>${edition}</div></div></div>
        <div class="row"><div class="col-md-4"><span class="text-muted">License Model</span><div>${license}</div></div><div class="col-md-4"><span class="text-muted">Nodes Allowed</span><div>${
            info.nodes_allowed ?? 'N/A'
        }</div></div><div class="col-md-4"><span class="text-muted">Nodes Used</span><div>${info.nodes_used ?? 'N/A'}</div></div></div>
      </div>
    </div>`;
}

export function renderLabSummary(labs) {
    labs = Array.isArray(labs) ? labs : [];
    if (labs.length === 0) {
        return '<div class="alert alert-info"><i class="bi bi-diagram-3 me-1"></i>No labs found on this worker.</div>';
    }
    return `
    <div class="table-responsive">
      <table class="table table-sm table-hover align-middle">
        <thead><tr><th>Name</th><th>Status</th><th>Nodes</th><th>Created</th><th>Modified</th></tr></thead>
        <tbody>
          ${labs
              .map(l => {
                  const badge = l.state === 'DEFINED' ? 'secondary' : l.state === 'STARTING' ? 'warning' : l.state === 'RUNNING' ? 'success' : l.state === 'STOPPED' ? 'info' : 'dark';
                  return `<tr><td>${l.name || '(unnamed)'}</td><td><span class='badge bg-${badge}'>${l.state || 'N/A'}</span></td><td>${l.node_count ?? 'N/A'}</td><td>${l.created || 'N/A'}</td><td>${l.modified || 'N/A'}</td></tr>`;
              })
              .join('')}
        </tbody>
      </table>
    </div>`;
}
