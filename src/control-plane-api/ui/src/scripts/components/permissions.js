/**
 * Permission Utilities
 * Handles user role checks and permissions
 */

/**
 * Get current user roles from user info
 * @returns {Array<string>} - Array of user roles
 */
export function getCurrentUserRoles() {
    // User info is stored in localStorage during authentication
    const rolesJson = localStorage.getItem('user_roles');
    if (rolesJson) {
        try {
            return JSON.parse(rolesJson);
        } catch {
            return [];
        }
    }

    return [];
}

/**
 * Check if user can edit tasks based on role and assignment
 * @param {Object} task - Task object
 * @returns {boolean}
 */
export function canEditTask(task) {
    const roles = getCurrentUserRoles();
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.sub || userInfo.user_id;

    // Admins can edit any task
    if (roles.includes('admin')) {
        return true;
    }

    // Managers can edit tasks in their department
    if (roles.includes('manager') && userInfo.department && task.department === userInfo.department) {
        return true;
    }

    // Users can edit tasks assigned to them
    if (userId && task.assignee_id === userId) {
        return true;
    }

    return false;
}

/**
 * Check if user can delete tasks (admin or manager role)
 * @returns {boolean}
 */
export function canDeleteTasks() {
    const roles = getCurrentUserRoles();
    return roles.includes('admin') || roles.includes('manager');
}
