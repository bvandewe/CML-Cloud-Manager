/**
 * Notifications Module
 * Handles toast notifications using Bootstrap
 */

import * as bootstrap from 'bootstrap';

/**
 * Show a toast notification
 * @param {string} message - Message to display
 * @param {string} type - Type of toast: success, error, warning, info
 * @param {number} duration - Duration in ms (default: 3000)
 */
export function showToast(message, type = 'info', duration = 3000) {
    // Create toast container if it doesn't exist
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }

    // Determine icon and color based on type
    const config = {
        success: { icon: 'bi-check-circle-fill', bg: 'bg-success' },
        error: { icon: 'bi-x-circle-fill', bg: 'bg-danger' },
        warning: { icon: 'bi-exclamation-triangle-fill', bg: 'bg-warning' },
        info: { icon: 'bi-info-circle-fill', bg: 'bg-info' },
    };

    const { icon, bg } = config[type] || config.info;

    // Create toast element
    const toastId = `toast-${Date.now()}`;
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${bg} text-white">
                <i class="bi ${icon} me-2"></i>
                <strong class="me-auto">${capitalizeType(type)}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);

    // Initialize and show toast
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: duration,
    });

    toast.show();

    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

/**
 * Capitalize first letter of type
 */
function capitalizeType(type) {
    return type.charAt(0).toUpperCase() + type.slice(1);
}

/**
 * Show a loading toast
 * @param {string} message - Message to display
 * @returns {Object} Toast instance with dismiss method
 */
export function showLoadingToast(message) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }

    const toastId = `toast-${Date.now()}`;
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-primary text-white">
                <span class="spinner-border spinner-border-sm me-2" role="status"></span>
                <strong class="me-auto">Loading</strong>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: false,
    });

    toast.show();

    return {
        dismiss: () => {
            toast.hide();
            setTimeout(() => toastElement.remove(), 300);
        },
    };
}
