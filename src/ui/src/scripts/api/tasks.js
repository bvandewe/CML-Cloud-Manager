/**
 * Tasks API Module
 * Handles all task-related API operations
 */

import { apiRequest } from './client.js';

/**
 * Load all tasks
 * @returns {Promise<Array>} - Array of tasks
 */
export async function fetchTasks() {
    const response = await apiRequest('/api/tasks/');
    return await response.json();
}

/**
 * Create a new task
 * @param {Object} taskData - Task data (title, description, priority)
 * @returns {Promise<Object>} - Created task
 */
export async function createTask(taskData) {
    const response = await apiRequest('/api/tasks/', {
        method: 'POST',
        body: JSON.stringify(taskData),
    });

    if (!response.ok) {
        throw new Error('Failed to create task');
    }

    return await response.json();
}

/**
 * Update a task
 * @param {string} taskId - Task ID
 * @param {Object} updates - Task updates
 * @returns {Promise<Object>} - Updated task
 */
export async function updateTask(taskId, updates) {
    const response = await apiRequest(`/api/tasks/${taskId}/`, {
        method: 'PUT',
        body: JSON.stringify(updates),
    });

    if (!response.ok) {
        throw new Error('Failed to update task');
    }

    return await response.json();
}

/**
 * Delete a task
 * @param {string} taskId - Task ID
 * @returns {Promise<void>}
 */
export async function deleteTask(taskId) {
    const response = await apiRequest(`/api/tasks/${taskId}/`, {
        method: 'DELETE',
    });

    if (!response.ok) {
        throw new Error('Failed to delete task');
    }
}

/**
 * Get a single task by ID
 * @param {string} taskId - Task ID
 * @returns {Promise<Object>} - Task object
 */
export async function fetchTask(taskId) {
    const response = await apiRequest(`/api/tasks/${taskId}/`);

    if (!response.ok) {
        throw new Error('Failed to fetch task');
    }

    return await response.json();
}
