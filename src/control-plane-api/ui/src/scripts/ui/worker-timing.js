// worker-timing.js
// Extracted timing & countdown utilities for worker details modal.

import { getActiveWorker, getTiming, updateTiming } from '../store/workerStore.js';
import { formatDateWithRelative, initializeDateTooltips } from '../utils/dates.js';

let metricsCountdownInterval = null;

export function ensureTimingHeader(modalElement) {
    if (!modalElement) return;
    const header = modalElement.querySelector('.modal-header');
    if (!header) return;
    if (!header.querySelector('#metrics-last-refreshed')) {
        const timingWrapper = document.createElement('div');
        timingWrapper.className = 'ms-auto d-flex align-items-center gap-3 small';
        timingWrapper.innerHTML = `
      <div id="metrics-last-refreshed" class="text-muted" title="Last metrics refresh">
        <i class="bi bi-clock-history"></i> <span class="last-refreshed-time">--</span>
      </div>
      <div id="metrics-countdown-wrapper" class="text-muted" title="Time until next metrics poll">
        <i class="bi bi-hourglass-split"></i> <span id="metrics-countdown">--:--</span>
      </div>`;
        header.appendChild(timingWrapper);
    }
}

export function updateLastRefreshedDisplay() {
    const el = document.querySelector('#metrics-last-refreshed .last-refreshed-time');
    if (!el) return;
    const active = getActiveWorker();
    if (!active) {
        el.textContent = '--';
        return;
    }
    const timing = getTiming(active.id);
    if (!timing || !timing.lastRefreshedAt) {
        el.textContent = '--';
        return;
    }
    const formatted = formatDateWithRelative(timing.lastRefreshedAt);
    if (el.textContent !== formatted) {
        el.innerHTML = formatted;
        initializeDateTooltips();
    }
}

export function startMetricsCountdown() {
    stopMetricsCountdown();
    updateLastRefreshedDisplay();
    const active = getActiveWorker();
    const timing = active ? getTiming(active.id) : null;
    if (!timing || !timingHasNext(timing)) {
        setCountdownText('--:--');
        return;
    }
    updateMetricsCountdownDisplay();
    metricsCountdownInterval = setInterval(updateMetricsCountdownDisplay, 1000);
}

export function stopMetricsCountdown() {
    if (metricsCountdownInterval) {
        clearInterval(metricsCountdownInterval);
        metricsCountdownInterval = null;
    }
}

export function resetMetricsCountdown(data) {
    const active = getActiveWorker();
    if (active && data) {
        updateTiming(active.id, {
            poll_interval: data.poll_interval || data.cloudwatch_poll_interval || 300,
            next_refresh_at: data.next_refresh_at || data.cloudwatch_next_refresh_at || new Date(Date.now() + (data.poll_interval || 300) * 1000).toISOString(),
            last_refreshed_at: new Date().toISOString(),
        });
    }
    updateLastRefreshedDisplay();
    stopMetricsCountdown();
    startMetricsCountdown();
}

function updateMetricsCountdownDisplay() {
    const active = getActiveWorker();
    const timing = active ? getTiming(active.id) : null;
    if (!timing || !timingHasNext(timing)) {
        setCountdownText('--:--');
        return;
    }
    const now = Date.now();
    const nextRefreshTime = new Date(timing.nextRefreshAt).getTime();
    const remainingMs = nextRefreshTime - now;
    if (remainingMs <= 0) {
        setCountdownText('Refreshing...');
        return;
    }
    const remainingSeconds = Math.floor(remainingMs / 1000);
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;
    setCountdownText(`${minutes}:${seconds.toString().padStart(2, '0')}`);
}

function setCountdownText(text) {
    const countdownElement = document.getElementById('metrics-countdown');
    if (countdownElement) countdownElement.textContent = text;
}

function timingHasNext(timing) {
    return !!timing.nextRefreshAt;
}
