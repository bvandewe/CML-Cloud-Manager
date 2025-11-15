/**
 * Tasks UI Module
 * Re-exports from modular components for backward compatibility
 */

export { loadTasks, handleCreateTask, handleUpdateTask } from '../components/dashboard.js';
export { renderTaskCards } from '../components/task-card.js';
export { showAlert, showConfirm, showSuccessToast } from '../components/modals.js';
export { getCurrentUserRoles, canEditTask, canDeleteTasks } from '../components/permissions.js';
