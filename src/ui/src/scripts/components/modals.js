/**
 * Modal Utilities
 * Handles modal dialogs and toast notifications
 */

import * as bootstrap from 'bootstrap';

/**
 * Show alert modal
 * @param {string} title - Modal title
 * @param {string} message - Alert message
 * @param {string} type - Alert type ('error', 'warning', 'info', 'success')
 */
export function showAlert(title, message, type = 'error') {
    const modal = document.getElementById('alertModal');
    const titleElement = document.getElementById('alert-modal-title');
    const messageElement = document.getElementById('alert-modal-message');
    const iconElement = document.getElementById('alert-modal-icon');

    titleElement.textContent = title;
    messageElement.textContent = message;

    // Update icon based on type
    const iconMap = {
        error: 'bi-x-circle text-danger',
        warning: 'bi-exclamation-triangle text-warning',
        info: 'bi-info-circle text-info',
        success: 'bi-check-circle text-success',
    };

    iconElement.className = `bi ${iconMap[type] || iconMap.error} me-2`;

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Show confirmation modal
 * @param {string} title - Modal title
 * @param {string} message - Confirmation message
 * @param {Function} onConfirm - Callback function when confirmed
 */
export function showConfirm(title, message, onConfirm) {
    const modal = document.getElementById('confirmModal');
    const titleElement = document.getElementById('confirm-modal-title');
    const messageElement = document.getElementById('confirm-modal-message');
    const confirmButton = document.getElementById('confirm-modal-action');

    titleElement.textContent = title;
    messageElement.textContent = message;

    // Remove any existing event listeners
    const newConfirmButton = confirmButton.cloneNode(true);
    confirmButton.parentNode.replaceChild(newConfirmButton, confirmButton);

    // Add new event listener
    newConfirmButton.addEventListener('click', () => {
        const bsModal = bootstrap.Modal.getInstance(modal);
        bsModal.hide();
        onConfirm();
    });

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

/**
 * Show success toast message
 * @param {string} message - Message to display
 */
export function showSuccessToast(message = 'Task updated successfully!') {
    const toastElement = document.getElementById('success-toast');
    const messageElement = document.getElementById('toast-message');
    messageElement.textContent = message;

    const toast = new bootstrap.Toast(toastElement);
    toast.show();
}
