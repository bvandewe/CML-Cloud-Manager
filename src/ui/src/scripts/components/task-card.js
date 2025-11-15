/**
 * Task Card Component
 * Handles rendering and interaction of individual task cards
 */

import * as bootstrap from 'bootstrap';
import { marked } from 'marked';
import { canEditTask, canDeleteTasks } from './permissions.js';

// Configure marked for safe rendering
marked.setOptions({
    breaks: true,
    gfm: true,
});

/**
 * Create task card HTML
 * @param {Object} task - Task object
 * @param {boolean} showDeleteButton - Whether to show delete button
 * @returns {string} - HTML string for task card
 */
export function createTaskCardHTML(task, showDeleteButton) {
    const priorityBadge =
        {
            low: 'success',
            medium: 'warning',
            high: 'danger',
        }[task.priority] || 'secondary';

    const statusBadge =
        {
            pending: 'secondary',
            in_progress: 'info',
            completed: 'success',
        }[task.status] || 'secondary';

    const canEdit = canEditTask(task);
    const departmentBadge = task.department || '';

    // Format timestamps for tooltip
    const createdAt = new Date(task.created_at).toLocaleString();
    const updatedAt = task.updated_at ? new Date(task.updated_at).toLocaleString() : 'Never';
    const tooltipText = `<strong>Created:</strong> ${createdAt}<br><strong>Updated:</strong> ${updatedAt}`;

    // Create card footer with action icons
    let cardFooter = '';
    if (canEdit || showDeleteButton) {
        const editIcon = canEdit
            ? `
            <i class="bi bi-pencil text-primary edit-task-icon"
               style="cursor: pointer; font-size: 1.1rem;"
               data-task-id="${task.id}"
               title="Edit task"></i>`
            : '';

        const infoIcon = `
            <i class="bi bi-info-circle text-secondary info-task-icon"
               style="cursor: pointer; font-size: 1.1rem;"
               data-bs-toggle="tooltip"
               data-bs-placement="top"
               data-bs-html="true"
               title="${tooltipText}"
               tabindex="0"></i>`;

        const deleteIcon = showDeleteButton
            ? `
            <i class="bi bi-trash text-danger delete-task-icon"
               style="cursor: pointer; font-size: 1.1rem;"
               data-task-id="${task.id}"
               title="Delete task"></i>`
            : '';

        cardFooter = `
            <div class="card-footer bg-transparent border-top py-2 collapsed">
                <div class="d-flex justify-content-between align-items-center">
                    ${editIcon}
                    ${infoIcon}
                    ${deleteIcon}
                </div>
            </div>`;
    }

    // Render description as markdown HTML
    const descriptionHtml = marked.parse(task.description || '');

    return `
        <div class="col-md-4 mb-3">
            <div class="card h-100" data-card-id="${task.id}">
                <div class="card-header task-header" style="cursor: pointer;" data-task-id="${task.id}">
                    <h5 class="card-title mb-2 fw-bold">${task.title}</h5>
                    <div class="d-flex gap-2">
                        <span class="badge bg-${priorityBadge}" style="font-size: 0.7rem;">${task.priority}</span>
                        <span class="badge bg-${statusBadge}" style="font-size: 0.7rem;">${task.status}</span>
                        ${departmentBadge ? `<span class="badge bg-secondary" style="font-size: 0.7rem;">${departmentBadge}</span>` : ''}
                    </div>
                </div>
                <div class="card-body task-body collapsed" style="cursor: pointer;" data-task-id="${task.id}" data-can-edit="${canEdit}">
                    <div class="task-description">${descriptionHtml}</div>
                    ${task.assignee_id ? `<small class="text-muted d-block mt-2">Assigned to: ${task.assignee_id}</small>` : ''}
                </div>
                ${cardFooter}
            </div>
        </div>
    `;
}

/**
 * Setup card interactions after rendering
 * @param {Function} onEditTask - Callback for edit task action
 * @param {Function} onDeleteTask - Callback for delete task action
 */
export function setupCardInteractions(onEditTask, onDeleteTask) {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(
        tooltipTriggerEl =>
            new bootstrap.Tooltip(tooltipTriggerEl, {
                html: true,
                trigger: 'hover focus',
                delay: { show: 100, hide: 100 },
            })
    );

    // Attach event listeners to card headers for toggling body/footer
    const headers = document.querySelectorAll('.task-header');

    headers.forEach(header => {
        // Set initial rounded corners for collapsed state
        header.style.borderRadius = 'var(--bs-card-border-radius)';

        header.addEventListener('click', e => {
            e.stopPropagation();

            // Get the clicked header and its parent card
            const clickedHeader = e.currentTarget;
            const card = clickedHeader.closest('.card');

            if (!card) return;

            const body = card.querySelector('.task-body');
            const footer = card.querySelector('.card-footer');

            if (!body) return;

            // Check if currently collapsed using CSS class
            const isCurrentlyCollapsed = body.classList.contains('collapsed');

            // Toggle visibility of THIS card only using CSS classes
            body.classList.toggle('collapsed');

            if (footer) {
                footer.classList.toggle('collapsed');
            }

            // Toggle header border radius based on expanded/collapsed state
            if (isCurrentlyCollapsed) {
                // When expanding, remove bottom border radius
                clickedHeader.style.borderRadius = '';
            } else {
                // When collapsing, add rounded corners to all sides
                clickedHeader.style.borderRadius = 'var(--bs-card-border-radius)';
            }
        });
    });

    // Attach event listeners to card bodies for opening edit modal
    document.querySelectorAll('.task-body').forEach(body => {
        body.addEventListener('click', e => {
            e.stopPropagation();
            const canEdit = e.currentTarget.getAttribute('data-can-edit') === 'true';
            if (canEdit) {
                const taskId = e.currentTarget.getAttribute('data-task-id');
                onEditTask(taskId);
            }
        });
    });

    // Attach event listeners to edit icons
    document.querySelectorAll('.edit-task-icon').forEach(icon => {
        icon.addEventListener('click', e => {
            e.stopPropagation();
            const taskId = e.currentTarget.getAttribute('data-task-id');
            onEditTask(taskId);
        });
    });

    // Attach event listeners to delete icons
    document.querySelectorAll('.delete-task-icon').forEach(icon => {
        icon.addEventListener('click', e => {
            e.stopPropagation();
            const taskId = e.currentTarget.getAttribute('data-task-id');
            onDeleteTask(taskId);
        });
    });
}

/**
 * Render tasks to container
 * @param {Array} tasks - Array of task objects
 * @param {HTMLElement} container - Container element
 * @param {Function} onEditTask - Callback for edit task action
 * @param {Function} onDeleteTask - Callback for delete task action
 */
export function renderTaskCards(tasks, container, onEditTask, onDeleteTask) {
    container.innerHTML = '';

    if (tasks.length === 0) {
        container.innerHTML = '<div class="col"><p class="text-muted">No tasks found.</p></div>';
        return;
    }

    const showDeleteButton = canDeleteTasks();
    let allCardsHtml = '';

    tasks.forEach(task => {
        allCardsHtml += createTaskCardHTML(task, showDeleteButton);
    });

    // Set all cards at once
    container.innerHTML = allCardsHtml;

    // Setup interactions
    setupCardInteractions(onEditTask, onDeleteTask);
}
