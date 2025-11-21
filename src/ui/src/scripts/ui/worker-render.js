// worker-render.js
// Rendering & statistics functions extracted from workers.js

import { escapeHtml } from '../components/escape.js';
import { getStatusBadgeClass, getServiceStatusBadgeClass, getCpuProgressClass, getMemoryProgressClass, getDiskProgressClass } from '../components/status-badges.js';
import { initializeDateTooltips, formatDateWithRelative, formatDate } from '../utils/dates.js';
import { isAdmin } from '../utils/roles.js';
import { renderMetrics } from '../components/metricsPanel.js';
import { getTiming } from '../store/workerStore.js';

let getWorkersDataRef = () => [];
let globalTimingInterval = null;
let globalTimingInitialized = false;
let transitionUpdateInterval = null;
export function bindRenderDependencies({ getWorkersData }) {
    getWorkersDataRef = getWorkersData;
}

export function updateStatistics() {
    const workersData = getWorkersDataRef();
    const total = workersData.length;
    const running = workersData.filter(w => w.status === 'running').length;
    const stopped = workersData.filter(w => w.status === 'stopped').length;
    const totalEl = document.getElementById('total-workers-count');
    if (totalEl) totalEl.textContent = total;
    const runningEl = document.getElementById('running-workers-count');
    if (runningEl) runningEl.textContent = running;
    const stoppedEl = document.getElementById('stopped-workers-count');
    if (stoppedEl) stoppedEl.textContent = stopped;
    const deriveCpuPercent = w => {
        if (w.cpu_utilization != null) return w.cpu_utilization;
        if (w.cml_system_info) {
            const firstCompute = Object.values(w.cml_system_info)[0];
            const percent = firstCompute?.stats?.cpu?.percent;
            if (percent != null) return parseFloat(percent);
        }
        return null;
    };
    const deriveMemoryPercent = w => {
        if (w.memory_utilization != null) return w.memory_utilization;
        if (w.cml_system_info) {
            const firstCompute = Object.values(w.cml_system_info)[0];
            const stats = firstCompute?.stats?.memory;
            if (stats?.total && stats?.used != null) return (stats.used / stats.total) * 100;
        }
        return null;
    };
    const deriveDiskPercent = w => {
        if (w.storage_utilization != null) return w.storage_utilization;
        if (w.cml_system_info) {
            const firstCompute = Object.values(w.cml_system_info)[0];
            const stats = firstCompute?.stats?.disk;
            if (stats?.total && stats?.used != null) return (stats.used / stats.total) * 100;
        }
        return null;
    };
    const cpuPercents = workersData.map(deriveCpuPercent).filter(v => v != null);
    const avgCpu = cpuPercents.length ? (cpuPercents.reduce((s, v) => s + v, 0) / cpuPercents.length).toFixed(1) : 0;
    const avgCpuEl = document.getElementById('avg-cpu-usage');
    if (avgCpuEl) avgCpuEl.textContent = `${avgCpu}%`;
    const memPercents = workersData.map(deriveMemoryPercent).filter(v => v != null);
    const avgMem = memPercents.length ? (memPercents.reduce((s, v) => s + v, 0) / memPercents.length).toFixed(1) : 0;
    const avgMemEl = document.getElementById('avg-memory-usage');
    if (avgMemEl) avgMemEl.textContent = `${avgMem}%`;
    const diskPercents = workersData.map(deriveDiskPercent).filter(v => v != null);
    const avgDisk = diskPercents.length ? (diskPercents.reduce((s, v) => s + v, 0) / diskPercents.length).toFixed(1) : 0;
    const avgDiskEl = document.getElementById('avg-disk-usage');
    if (avgDiskEl) avgDiskEl.textContent = `${avgDisk}%`;

    // Global timing indicators (across all workers) for main view
    ensureGlobalTimingIndicators();
    updateGlobalTimingIndicators(workersData);
}

function ensureGlobalTimingIndicators() {
    if (globalTimingInitialized) return;
    const host = document.getElementById('workers-section');
    if (!host) return;
    // Insert after SSE status if available
    const sseStatus = document.getElementById('sse-connection-status');
    const container = document.createElement('div');
    container.id = 'workers-global-timing';
    container.className = 'd-flex flex-wrap gap-3 align-items-center small mb-3';
    container.innerHTML = `
      <div id="workers-last-refreshed" class="text-muted" title="Most recent metrics refresh across workers">
        <i class="bi bi-clock-history"></i> <span class="value">--</span>
      </div>
      <div id="workers-next-refresh" class="text-muted" title="Next scheduled metrics poll (soonest)">
        <i class="bi bi-hourglass-split"></i> <span class="value">--</span>
      </div>
      <div id="workers-refresh-countdown" class="text-muted" title="Countdown to next poll">
        <i class="bi bi-stopwatch"></i> <span class="value">--:--</span>
      </div>`;
    if (sseStatus && sseStatus.nextSibling) {
        host.insertBefore(container, sseStatus.nextSibling);
    } else {
        host.prepend(container);
    }
    globalTimingInitialized = true;
}

function updateGlobalTimingIndicators(workers) {
    if (!globalTimingInitialized) return;
    const refreshedEl = document.querySelector('#workers-last-refreshed .value');
    const nextEl = document.querySelector('#workers-next-refresh .value');
    const countdownEl = document.querySelector('#workers-refresh-countdown .value');
    if (!refreshedEl || !nextEl || !countdownEl) return;
    // Build timing list with fallbacks from worker snapshot
    const timings = workers
        .map(w => {
            const timing = getTiming(w.id);
            if (timing) return timing;
            // Fallback: derive from worker fields if available
            const lastRefreshedAt = w.cloudwatch_last_collected_at || w.updated_at || null;
            const pollInterval = w.poll_interval || w.cloudwatch_poll_interval || 300; // default 5 min
            let nextRefreshAt = w.next_refresh_at || w.cloudwatch_next_refresh_at || null;
            if (!nextRefreshAt && lastRefreshedAt) {
                try {
                    nextRefreshAt = new Date(new Date(lastRefreshedAt).getTime() + pollInterval * 1000).toISOString();
                } catch (_) {
                    nextRefreshAt = null;
                }
            }
            if (!lastRefreshedAt && !nextRefreshAt) return null; // nothing usable
            return { lastRefreshedAt, nextRefreshAt };
        })
        .filter(Boolean);
    if (!timings.length) {
        refreshedEl.textContent = '--';
        nextEl.textContent = '--';
        countdownEl.textContent = '--:--';
        stopGlobalTimingInterval();
        return;
    }
    const lastRefreshed = timings
        .map(t => t.lastRefreshedAt)
        .filter(Boolean)
        .sort((a, b) => new Date(b) - new Date(a))[0];
    let nextRefresh = timings
        .map(t => t.nextRefreshAt)
        .filter(Boolean)
        .sort((a, b) => new Date(a) - new Date(b))[0];
    // Gather poll intervals to drive recurring countdown fallback
    const pollIntervals = workers
        .map(w => {
            const timing = getTiming(w.id);
            return timing?.pollInterval || w.poll_interval || w.cloudwatch_poll_interval || null;
        })
        .filter(Boolean);
    const minPollInterval = pollIntervals.length ? Math.min(...pollIntervals) : 300;
    // Fallback compute nextRefresh if missing but we have lastRefreshed
    if (!nextRefresh && lastRefreshed) {
        try {
            nextRefresh = new Date(new Date(lastRefreshed).getTime() + minPollInterval * 1000).toISOString();
        } catch (_) {
            /* ignore */
        }
    }
    refreshedEl.innerHTML = lastRefreshed ? formatDateWithRelative(lastRefreshed) : '--';
    nextEl.innerHTML = nextRefresh ? formatDateWithRelative(nextRefresh) : '--';
    initializeDateTooltips();
    startGlobalTimingInterval(nextRefresh, minPollInterval);
}

function startGlobalTimingInterval(nextRefresh, pollIntervalSeconds) {
    stopGlobalTimingInterval();
    if (!nextRefresh) return;
    const targetTs = new Date(nextRefresh).getTime();
    globalTimingInterval = setInterval(() => {
        const countdownEl = document.querySelector('#workers-refresh-countdown .value');
        if (!countdownEl) return;
        const remainingMs = targetTs - Date.now();
        if (remainingMs <= 0) {
            // Show transient refreshing state
            countdownEl.textContent = 'Refreshing...';
            // Trigger a lightweight refresh if available (store/SSE may also update soon)
            if (window.workersApp?.refreshWorkers) {
                try {
                    window.workersApp.refreshWorkers();
                } catch (e) {
                    console.warn('[worker-render] auto refresh failed', e);
                }
            }
            // Compute next target based on poll interval to continue countdown cycle
            if (pollIntervalSeconds) {
                const newTarget = Date.now() + pollIntervalSeconds * 1000;
                // Replace interval target without clearing outer interval
                // We reuse targetTs by reassignment through closure (can't directly reassign const)
            }
            stopGlobalTimingInterval();
            // Re-derive indicators on next store update; if none arrives within pollIntervalSeconds, a manual refresh keeps them cycling
            return;
        }
        const remainingSeconds = Math.floor(remainingMs / 1000);
        const minutes = Math.floor(remainingSeconds / 60);
        const seconds = remainingSeconds % 60;
        countdownEl.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }, 1000);
}

function stopGlobalTimingInterval() {
    if (globalTimingInterval) {
        clearInterval(globalTimingInterval);
        globalTimingInterval = null;
    }
}

export function renderWorkersTable() {
    console.log('[worker-render] renderWorkersTable called');
    const workersData = getWorkersDataRef() || [];
    console.log(
        '[worker-render] workersData:',
        workersData.map(w => ({
            id: w.id,
            name: w.name,
            license_status: w.license_status,
            cml_license_info: w.cml_license_info,
        }))
    );

    const tbody = document.getElementById('workers-table-body');
    if (!tbody) return;
    if (!workersData.length) {
        tbody.innerHTML = `<tr><td colspan='10' class='text-center text-muted py-4'><i class='bi bi-inbox fs-1 d-block mb-2'></i>No workers found</td></tr>`;
        return;
    }
    tbody.innerHTML = workersData
        .map(worker => {
            let cpuPct = worker.cpu_utilization;
            let memPct = worker.memory_utilization;
            let diskPct = worker.storage_utilization;
            if ((cpuPct == null || memPct == null || diskPct == null) && worker.cml_system_info) {
                const firstCompute = Object.values(worker.cml_system_info)[0];
                const stats = firstCompute?.stats || {};
                const cpuStats = stats.cpu || {};
                const memStats = stats.memory || {};
                const diskStats = stats.disk || {};
                if (cpuPct == null) {
                    if (cpuStats.percent != null) {
                        cpuPct = parseFloat(cpuStats.percent);
                    } else if (cpuStats.user_percent != null && cpuStats.system_percent != null) {
                        try {
                            cpuPct = parseFloat(cpuStats.user_percent) + parseFloat(cpuStats.system_percent);
                        } catch (_) {}
                    }
                }
                if (memPct == null) {
                    if (memStats.total && memStats.used != null) {
                        memPct = (memStats.used / memStats.total) * 100;
                    } else if (memStats.total_kb && memStats.available_kb != null) {
                        const t = memStats.total_kb;
                        const a = memStats.available_kb;
                        if (typeof t === 'number' && typeof a === 'number' && t > 0) memPct = ((t - a) / t) * 100;
                    }
                }
                if (diskPct == null) {
                    if (diskStats.total && diskStats.used != null) {
                        diskPct = (diskStats.used / diskStats.total) * 100;
                    } else if (diskStats.capacity_kb && diskStats.size_kb != null) {
                        const cap = diskStats.capacity_kb;
                        const sz = diskStats.size_kb;
                        if (typeof cap === 'number' && typeof sz === 'number' && cap > 0) diskPct = (sz / cap) * 100;
                    }
                }
            }
            const clamp = v => (v == null || isNaN(v) ? null : Math.min(100, Math.max(0, v)));
            cpuPct = clamp(cpuPct);
            memPct = clamp(memPct);
            diskPct = clamp(diskPct);
            const adminControls = isAdmin()
                ? `${
                      worker.status === 'stopped'
                          ? `<button class='btn btn-outline-success admin-only' onclick="event.stopPropagation(); window.workersApp.showStartConfirmation('${worker.id}','${worker.aws_region}','${escapeHtml(
                                worker.name
                            )}')" title='Start'><i class='bi bi-play-fill'></i></button>`
                          : ''
                  }${
                      worker.status === 'running'
                          ? `<button class='btn btn-outline-warning admin-only' onclick="event.stopPropagation(); window.workersApp.showStopConfirmation('${worker.id}','${worker.aws_region}','${escapeHtml(
                                worker.name
                            )}')" title='Stop'><i class='bi bi-stop-fill'></i></button>`
                          : ''
                  }`
                : '';
            // Transition duration display (dynamic via interval updater)
            let transitionInfo = '';
            if (worker.status === 'pending' && worker.start_initiated_at) {
                try {
                    const startedMs = Date.parse(worker.start_initiated_at);
                    const diffSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
                    const mins = Math.floor(diffSec / 60);
                    const secs = diffSec % 60;
                    transitionInfo = `<br><small class='text-muted transition-duration' data-init-ts='${worker.start_initiated_at}' data-type='start'>Starting (<span class='elapsed'>${mins}m ${secs}s</span>)</small>`;
                } catch (_) {}
            } else if (worker.status === 'stopping' && worker.stop_initiated_at) {
                try {
                    const stopMs = Date.parse(worker.stop_initiated_at);
                    const diffSec = Math.max(0, Math.floor((Date.now() - stopMs) / 1000));
                    const mins = Math.floor(diffSec / 60);
                    const secs = diffSec % 60;
                    transitionInfo = `<br><small class='text-muted transition-duration' data-init-ts='${worker.stop_initiated_at}' data-type='stop'>Stopping (<span class='elapsed'>${mins}m ${secs}s</span>)</small>`;
                } catch (_) {}
            }
            return `<tr class='cursor-pointer' data-worker-id='${worker.id}' data-worker-region='${worker.aws_region}' onclick="window.workersApp.showWorkerDetails('${worker.id}','${worker.aws_region}')">
      <td><span class='badge ${getStatusBadgeClass(worker.status)}'>${worker.status}</span>${transitionInfo}</td>
      <td><strong>${escapeHtml(worker.name)}</strong>${worker.https_endpoint ? `<br><small class='text-muted'>${worker.https_endpoint}</small>` : ''}</td>
      <td><code class='small'>${worker.aws_instance_id || 'N/A'}</code>${worker.public_ip ? `<br><small class='text-muted'>${worker.public_ip}</small>` : ''}</td>
      <td>${worker.instance_type}</td>
      <td><span class='badge bg-secondary'>${worker.aws_region}</span></td>
      <td><span class='badge ${getServiceStatusBadgeClass(worker.service_status)}'>${worker.service_status}</span></td>
      <td>${cpuPct != null ? `<div class='progress' style='height:20px;'><div class='progress-bar ${getCpuProgressClass(cpuPct)}' style='width:${cpuPct}%'>${cpuPct.toFixed(1)}%</div></div>` : '<span class="text-muted">-</span>'}</td>
      <td>${memPct != null ? `<div class='progress' style='height:20px;'><div class='progress-bar ${getMemoryProgressClass(memPct)}' style='width:${memPct}%'>${memPct.toFixed(1)}%</div></div>` : '<span class="text-muted">-</span>'}</td>
      <td>${diskPct != null ? `<div class='progress' style='height:20px;'><div class='progress-bar ${getDiskProgressClass(diskPct)}' style='width:${diskPct}%'>${diskPct.toFixed(1)}%</div></div>` : '<span class="text-muted">-</span>'}</td>
      <td><div class='btn-group btn-group-sm' role='group'>
        <button class='btn btn-outline-primary' onclick="event.stopPropagation(); window.workersApp.showWorkerDetails('${worker.id}','${worker.aws_region}')" title='View Details'><i class='bi bi-info-circle'></i></button>
        ${adminControls}
        ${
            isAdmin() && worker.status === 'running'
                ? `<button class='btn btn-outline-secondary refresh-btn admin-only' data-worker-id='${worker.id}' data-region='${worker.aws_region}' title='Refresh Metrics' onclick='event.stopPropagation()'><i class='bi bi-arrow-clockwise'></i></button>`
                : ''
        }
        ${
            isAdmin() && worker.status === 'running'
                ? `<button class='btn btn-outline-info admin-only' onclick="event.stopPropagation(); window.workersApp.showLicenseModal('${worker.id}','${worker.aws_region}','${escapeHtml(worker.name)}',${
                      worker.is_licensed || false
                  })" title='Register License'><i class='bi bi-key'></i></button>`
                : ''
        }
        <button class='btn btn-outline-danger admin-only' onclick="event.stopPropagation(); window.workersApp.showDeleteModal('${worker.id}','${worker.aws_region}','${escapeHtml(
            worker.name
        )}')" title='Delete Worker' style='display:none;'><i class='bi bi-trash'></i></button>
      </div></td>
    </tr>`;
        })
        .join('');
    initializeDateTooltips();
    if (isAdmin()) document.querySelectorAll('.admin-only').forEach(el => (el.style.display = ''));
    startTransitionDurationUpdater();
}

export function renderWorkersCards() {
    const workersData = getWorkersDataRef() || [];
    const container = document.getElementById('workers-cards-container');
    if (!container) return;
    if (!workersData.length) {
        container.innerHTML = `<div class='col-12 text-center text-muted py-5'><i class='bi bi-inbox fs-1 d-block mb-3'></i><h5>No workers available</h5><p>There are currently no CML workers available to you.</p></div>`;
        return;
    }
    const cardHtml = worker => {
        // Extract metrics with fallback logic (same as metricsPanel.js)
        let cpu = worker.cpu_utilization;
        let mem = worker.memory_utilization;
        let disk = worker.storage_utilization;

        // Fallback to CML system stats if present
        const firstCompute = worker.cml_system_info ? Object.values(worker.cml_system_info)[0] : null;
        const stats = firstCompute?.stats || {};
        const cpuStats = stats.cpu || {};
        const memStats = stats.memory || {};
        const diskStats = stats.disk || {};

        // CPU: prefer combined percent; else sum user/system percent variants
        if (cpu == null) {
            if (cpuStats.percent != null) {
                cpu = parseFloat(cpuStats.percent);
            } else if (cpuStats.user_percent != null && cpuStats.system_percent != null) {
                try {
                    cpu = parseFloat(cpuStats.user_percent) + parseFloat(cpuStats.system_percent);
                } catch (_) {
                    /* ignore parse errors */
                }
            }
        }

        // Memory: support total/used OR total_kb/available_kb
        if (mem == null) {
            if (memStats.total && memStats.used != null) {
                mem = (memStats.used / memStats.total) * 100;
            } else if (memStats.total_kb && memStats.available_kb != null) {
                const totalKb = memStats.total_kb;
                const availKb = memStats.available_kb;
                if (typeof totalKb === 'number' && typeof availKb === 'number' && totalKb > 0) {
                    mem = ((totalKb - availKb) / totalKb) * 100;
                }
            }
        }

        // Disk: support total/used OR capacity_kb/size_kb
        if (disk == null) {
            if (diskStats.total && diskStats.used != null) {
                disk = (diskStats.used / diskStats.total) * 100;
            } else if (diskStats.capacity_kb && diskStats.size_kb != null) {
                const capKb = diskStats.capacity_kb;
                const sizeKb = diskStats.size_kb;
                if (typeof capKb === 'number' && typeof sizeKb === 'number' && capKb > 0) {
                    disk = (sizeKb / capKb) * 100;
                }
            }
        }

        // Final normalization & clamping
        const clamp = v => (v == null || isNaN(v) ? null : Math.min(100, Math.max(0, v)));
        cpu = clamp(cpu);
        mem = clamp(mem);
        disk = clamp(disk);

        const statusBadgeClass = worker.status === 'running' ? 'bg-light text-success' : 'bg-light text-secondary';
        let headerClass = 'bg-secondary text-white';
        if (worker.status === 'running') headerClass = 'bg-success text-white';
        else if (worker.status === 'stopped') headerClass = 'bg-warning text-dark';
        else if (worker.status === 'pending' || worker.status === 'stopping' || worker.status === 'shutting-down') headerClass = 'bg-info text-dark';

        const cpuBar = cpu != null ? `<small class='text-muted'>CPU Usage</small><div class='progress mb-2' style='height:20px;'><div class='progress-bar ${getCpuProgressClass(cpu)}' style='width:${cpu}%'>${cpu.toFixed(1)}%</div></div>` : '';
        const memBar = mem != null ? `<small class='text-muted'>Memory Usage</small><div class='progress mb-2' style='height:20px;'><div class='progress-bar ${getMemoryProgressClass(mem)}' style='width:${mem}%'>${mem.toFixed(1)}%</div></div>` : '';
        const diskBar = disk != null ? `<small class='text-muted'>Disk Usage</small><div class='progress' style='height:20px;'><div class='progress-bar ${getDiskProgressClass(disk)}' style='width:${disk}%'>${disk.toFixed(1)}%</div></div>` : '';
        const metricsBlock = cpuBar || memBar || diskBar ? `<div class='mb-3'>${cpuBar}${memBar}${diskBar}</div>` : '';
        return `
                <div class='col-md-6 col-lg-4'>
                    <div class='card worker-card h-100 cursor-pointer ${worker.status === 'running' ? 'border-success' : 'border-secondary'}' onclick="window.workersApp.showWorkerDetails('${worker.id}','${worker.aws_region}')">
                        <div class='card-header ${headerClass}'>
                            <div class='d-flex justify-content-between align-items-center'>
                                <h5 class='card-title mb-0'><i class='bi bi-server'></i> ${escapeHtml(worker.name)}</h5>
                                <span class='badge ${statusBadgeClass}'>${worker.status}</span>
                            </div>
                        </div>
                        <div class='card-body d-flex flex-column'>
                            <div class='mb-3'>
                                <div class='d-flex justify-content-between mb-2'><span class='text-muted'><i class='bi bi-geo-alt'></i> Region</span><strong>${worker.aws_region}</strong></div>
                                <div class='d-flex justify-content-between mb-2'><span class='text-muted'><i class='bi bi-hdd'></i> Instance Type</span><strong>${worker.instance_type}</strong></div>
                                ${worker.cml_version ? `<div class='d-flex justify-content-between mb-2'><span class='text-muted'><i class='bi bi-box'></i> CML Version</span><strong>${worker.cml_version}</strong></div>` : ''}
                            </div>
                            ${metricsBlock}
                            ${
                                worker.https_endpoint && worker.status === 'running'
                                    ? `<div class='mt-auto d-grid' onclick='event.stopPropagation();'><a href='${worker.https_endpoint}' target='_blank' class='btn btn-primary'><i class='bi bi-box-arrow-up-right'></i> Access CML</a></div>`
                                    : `<div class='alert alert-warning mb-0 small'><i class='bi bi-exclamation-triangle'></i> Worker is not available</div>`
                            }
                        </div>
                        <div class='card-footer text-muted small'>
                            <div class='d-flex justify-content-between align-items-center'>
                                <span><i class='bi bi-clock'></i> ${formatDate(worker.updated_at)}</span>
                                <span class='badge bg-primary'>Click for details</span>
                            </div>
                        </div>
                    </div>
                </div>`;
    };
    container.innerHTML = workersData.map(cardHtml).join('');
    initializeDateTooltips();
}

export function applyFilters() {
    const workersData = getWorkersDataRef() || [];
    const searchTerm = document.getElementById('search-workers')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-status')?.value || '';
    let filtered = workersData;
    if (statusFilter) filtered = filtered.filter(w => w.status === statusFilter);
    if (searchTerm)
        filtered = filtered.filter(w => w.name.toLowerCase().includes(searchTerm) || w.aws_instance_id?.toLowerCase().includes(searchTerm) || w.public_ip?.toLowerCase().includes(searchTerm) || w.private_ip?.toLowerCase().includes(searchTerm));
    const original = workersData;
    window.__tmpWorkers = filtered;
    const tbody = document.getElementById('workers-table-body');
    if (tbody) {
        tbody.innerHTML = '';
    }
    const backupGet = getWorkersDataRef;
    bindRenderDependencies({ getWorkersData: () => window.__tmpWorkers });
    renderWorkersTable();
    bindRenderDependencies({ getWorkersData: backupGet });
    delete window.__tmpWorkers;
}

export function applyUserFilters() {
    const workersData = getWorkersDataRef() || [];
    const searchTerm = document.getElementById('search-workers-user')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-status-user')?.value || '';
    const sortBy = document.getElementById('sort-workers-user')?.value || 'name';
    let filtered = workersData;
    if (statusFilter) filtered = filtered.filter(w => w.status === statusFilter);
    if (searchTerm) filtered = filtered.filter(w => w.name.toLowerCase().includes(searchTerm));
    filtered.sort((a, b) => {
        if (sortBy === 'name') return a.name.localeCompare(b.name);
        if (sortBy === 'status') return a.status.localeCompare(b.status);
        if (sortBy === 'usage') return (b.cpu_utilization || 0) - (a.cpu_utilization || 0);
        return 0;
    });
    const backupGet = getWorkersDataRef;
    bindRenderDependencies({ getWorkersData: () => filtered });
    renderWorkersCards();
    bindRenderDependencies({ getWorkersData: backupGet });
}

// Periodic updater for transition durations (start/stop elapsed time)
function startTransitionDurationUpdater() {
    if (transitionUpdateInterval) return; // already running
    transitionUpdateInterval = setInterval(() => {
        const elements = document.querySelectorAll('.transition-duration');
        if (!elements.length) {
            // If no elements, stop interval to save resources
            clearInterval(transitionUpdateInterval);
            transitionUpdateInterval = null;
            return;
        }
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
}
