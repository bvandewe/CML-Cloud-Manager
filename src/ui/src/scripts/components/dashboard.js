/**
 * Dashboard Component
 * Manages the main task dashboard functionality
 */

import * as bootstrap from 'bootstrap';
import { fetchTasks, createTask as createTaskAPI, updateTask as updateTaskAPI, deleteTask as deleteTaskAPI, fetchTask } from '../api/tasks.js';
import { showAlert, showConfirm, showSuccessToast } from './modals.js';
import { canEditTask, getCurrentUserRoles } from './permissions.js';
import { renderTaskCards } from './task-card.js';

/**
 * Load and render tasks
 */
export async function loadTasks() {
    try {
        const tasks = await fetchTasks();
        const container = document.getElementById('tasks-container');
        renderTaskCards(tasks, container, handleEditTask, handleDeleteTask);
    } catch (error) {
        console.error('Failed to load tasks:', error);
        const container = document.getElementById('tasks-container');
        container.innerHTML = '<div class="col"><p class="text-danger">Failed to load tasks. Please try again or contact support.</p></div>';
    }
}

/**
 * Handle task editing
 * @param {string} taskId - Task ID to edit
 */
async function handleEditTask(taskId) {
    try {
        const task = await fetchTask(taskId);

        // Check if user can edit this task
        if (!canEditTask(task)) {
            showAlert('Permission Denied', 'You do not have permission to edit this task.', 'warning');
            return;
        }

        // Populate edit modal with task data
        document.getElementById('edit-task-id').value = task.id;
        document.getElementById('edit-task-title').value = task.title;
        document.getElementById('edit-task-description').value = task.description;
        document.getElementById('edit-task-status').value = task.status;
        document.getElementById('edit-task-priority').value = task.priority;
        document.getElementById('edit-task-assignee').value = task.assignee_id || '';
        document.getElementById('edit-task-department').value = task.department || '';

        // Show/hide fields based on user permissions
        const roles = getCurrentUserRoles();
        const isAdmin = roles.includes('admin');
        const isManager = roles.includes('manager');

        // Only admins and managers can assign tasks to others
        const assigneeSection = document.getElementById('edit-assignee-section');
        assigneeSection.style.display = isAdmin || isManager ? 'block' : 'none';

        // Only admins can change department
        const departmentSection = document.getElementById('edit-department-section');
        departmentSection.style.display = isAdmin ? 'block' : 'none';

        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('editTaskModal'));
        modal.show();
    } catch (error) {
        showAlert('Error Loading Task', 'Failed to load task details: ' + error.message, 'error');
    }
}

/**
 * Handle edit task form submission
 */
export async function handleUpdateTask() {
    const taskId = document.getElementById('edit-task-id').value;
    const title = document.getElementById('edit-task-title').value;
    const description = document.getElementById('edit-task-description').value;
    const status = document.getElementById('edit-task-status').value;
    const priority = document.getElementById('edit-task-priority').value;
    const assigneeId = document.getElementById('edit-task-assignee').value || null;
    const department = document.getElementById('edit-task-department').value || null;

    try {
        await updateTaskAPI(taskId, {
            title,
            description,
            status,
            priority,
            assignee_id: assigneeId,
            department,
        });

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('editTaskModal'));
        modal.hide();

        // Show success toast
        showSuccessToast('Task updated successfully!');

        // Reload tasks
        await loadTasks();
    } catch (error) {
        showAlert('Error Updating Task', 'Failed to update task: ' + error.message, 'error');
    }
}

/**
 * Handle task deletion
 * @param {string} taskId - Task ID to delete
 */
async function handleDeleteTask(taskId) {
    showConfirm('Delete Task', 'Are you sure you want to delete this task? This action cannot be undone.', async () => {
        try {
            await deleteTaskAPI(taskId);
            showSuccessToast('Task deleted successfully!');
            await loadTasks();
        } catch (error) {
            showAlert('Error Deleting Task', 'Failed to delete task: ' + error.message, 'error');
        }
    });
}

/**
 * Handle create task form submission
 */
export async function handleCreateTask() {
    const title = document.getElementById('task-title').value;
    const description = document.getElementById('task-description').value;
    const status = document.getElementById('task-status').value;
    const priority = document.getElementById('task-priority').value;
    const assigneeId = document.getElementById('task-assignee').value.trim();
    const department = document.getElementById('task-department').value.trim();

    try {
        const taskData = {
            title,
            description,
            status,
            priority,
        };

        // Add optional fields only if they have values
        if (assigneeId) {
            taskData.assignee_id = assigneeId;
        }
        if (department) {
            taskData.department = department;
        }

        await createTaskAPI(taskData);

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('createTaskModal'));
        modal.hide();

        // Reset form
        document.getElementById('create-task-form').reset();

        // Show success toast
        showSuccessToast('Task created successfully!');

        // Reload tasks
        await loadTasks();
    } catch (error) {
        showAlert('Error Creating Task', 'Failed to create task: ' + error.message, 'error');
    }
}
