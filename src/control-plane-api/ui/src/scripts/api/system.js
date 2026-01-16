/**
 * System monitoring API client
 *
 * Provides functions for querying system internals including:
 * - APScheduler jobs and status
 * - Worker monitoring status
 * - System health checks
 * - Metrics collectors
 */

import { apiRequest } from './client.js';

/**
 * Get all APScheduler jobs
 * @returns {Promise<Array>} Array of scheduler job objects
 */
export async function getSchedulerJobs() {
    const response = await apiRequest('/api/system/scheduler/jobs', {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Get APScheduler status and statistics
 * @returns {Promise<Object>} Scheduler status object
 */
export async function getSchedulerStatus() {
    const response = await apiRequest('/api/system/scheduler/status', {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Get worker monitoring service status
 * @returns {Promise<Object>} Worker monitoring status object
 */
export async function getWorkerMonitoringStatus() {
    const response = await apiRequest('/api/system/monitoring/workers', {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Get overall system health status
 * @returns {Promise<Object>} System health object
 */
export async function getSystemHealth() {
    const response = await apiRequest('/api/system/health', {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Get metrics collectors status
 * @returns {Promise<Object>} Metrics collectors status object
 */
export async function getMetricsCollectorsStatus() {
    const response = await apiRequest('/api/system/metrics/collectors', {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Trigger a scheduled job to run immediately
 * @param {string} jobId - The job ID to trigger
 * @returns {Promise<Object>} Result object
 */
export async function triggerJob(jobId) {
    const response = await apiRequest(`/api/system/scheduler/jobs/${jobId}/trigger`, {
        method: 'POST',
    });
    return await response.json();
}
