/**
 * metricsPanel.js
 * Pure rendering for metrics utilization bars.
 */

import { escapeHtml } from './escape.js';

function barColor(val) {
    if (val == null) return 'bg-secondary';
    if (val > 80) return 'bg-danger';
    if (val > 60) return 'bg-warning';
    return 'bg-success';
}

export function renderMetrics(worker) {
    if (!worker) return '<div class="alert alert-warning">Metrics unavailable</div>';
    let cpu = worker.cpu_utilization;
    let mem = worker.memory_utilization;
    let disk = worker.storage_utilization;
    // Fallback to CML system stats if present (handles multiple key patterns)
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

    const metricBlock = (label, value, type) => {
        if (value == null) {
            return `<div class="col-md-4"><div class="alert alert-sm alert-warning py-1 mb-2"><i class="bi bi-info-circle"></i> No ${escapeHtml(label)} data</div></div>`;
        }
        const color = barColor(value);
        return `<div class="col-md-4">
      <h6 class="text-muted mb-2">${escapeHtml(label)}</h6>
      <div class="progress" style="height:20px" aria-label="${escapeHtml(label)} utilization">
        <div class="progress-bar ${color}" role="progressbar" style="width:${value.toFixed(1)}%;" aria-valuenow="${value.toFixed(1)}" aria-valuemin="0" aria-valuemax="100">${value.toFixed(1)}%</div>
      </div>
    </div>`;
    };

    return `<div class="row g-3" aria-label="Utilization metrics" role="group">
    ${metricBlock('CPU', cpu, 'cpu')}
    ${metricBlock('Memory', mem, 'memory')}
    ${metricBlock('Disk', disk, 'disk')}
  </div>`;
}
