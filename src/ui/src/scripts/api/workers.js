/**
 * Workers API Client
 * Handles all API calls related to CML Workers
 */

import { apiRequest } from './client.js';

/**
 * List all CML Workers in a region
 * @param {string} region - AWS region
 * @param {string|null} status - Optional status filter
 * @returns {Promise<Array>}
 */
export async function listWorkers(region = 'us-east-1', status = null) {
    const params = status ? `?status=${status}` : '';
    const response = await apiRequest(`/api/workers/region/${region}/workers${params}`, {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Get worker details by ID
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @returns {Promise<Object>}
 */
export async function getWorkerDetails(region, workerId) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}`, {
        method: 'GET',
    });
    return await response.json();
}

/**
 * Create a new CML Worker
 * @param {string} region - AWS region
 * @param {Object} workerData - Worker creation data
 * @returns {Promise<Object>}
 */
export async function createWorker(region, workerData) {
    const response = await apiRequest(`/api/workers/region/${region}/workers`, {
        method: 'POST',
        body: JSON.stringify(workerData),
    });
    return await response.json();
}

/**
 * Import an existing EC2 instance as a CML Worker
 * @param {string} region - AWS region
 * @param {Object} importData - Import parameters
 * @returns {Promise<Object>}
 */
export async function importWorker(region, importData) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/import`, {
        method: 'POST',
        body: JSON.stringify(importData),
    });
    return await response.json();
}

/**
 * Start a CML Worker
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @returns {Promise<Object>}
 */
export async function startWorker(region, workerId) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/start`, {
        method: 'POST',
    });
    return await response.json();
}

/**
 * Stop a CML Worker
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @returns {Promise<Object>}
 */
export async function stopWorker(region, workerId) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/stop`, {
        method: 'POST',
    });
    return await response.json();
}

/**
 * Terminate a CML Worker
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @returns {Promise<void>}
 */
export async function terminateWorker(region, workerId) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}`, {
        method: 'DELETE',
    });
    // DELETE may return 204 No Content
    if (response.status === 204) return;
    return await response.json();
}

/**
 * Register CML license for a worker
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {string} licenseToken - CML license token
 * @returns {Promise<Object>}
 */
export async function registerLicense(region, workerId, licenseToken) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/license`, {
        method: 'POST',
        body: JSON.stringify({ license_token: licenseToken }),
    });
    return await response.json();
}

/**
 * Refresh worker state from AWS and ensure monitoring is active
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @returns {Promise<Object>}
 */
export async function refreshWorker(region, workerId) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/refresh`, {
        method: 'POST',
    });
    return await response.json();
}

/**
 * Update worker tags
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {Object} tags - Tags to update
 * @returns {Promise<Object>}
 */
export async function updateWorkerTags(region, workerId, tags) {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/tags`, {
        method: 'PUT',
        body: JSON.stringify({ tags }),
    });
    return await response.json();
}

/**
 * Get worker resources utilization
 * @param {string} region - AWS region
 * @param {string} workerId - Worker UUID
 * @param {string} startTime - Relative start time: '30s', '1m', '5m', or '10m'
 * @returns {Promise<Object>}
 */
export async function getWorkerResources(region, workerId, startTime = '5m') {
    const response = await apiRequest(`/api/workers/region/${region}/workers/${workerId}/resources?start_time=${startTime}`, {
        method: 'GET',
    });
    return await response.json();
}
