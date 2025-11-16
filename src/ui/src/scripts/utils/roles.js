/**
 * Role Utility Functions
 * Provides role-based access control utilities for frontend
 */

/**
 * Get user roles from localStorage
 * @returns {Array<string>} Array of user roles
 */
export function getUserRoles() {
    try {
        const roles = localStorage.getItem('user_roles');
        return roles ? JSON.parse(roles) : [];
    } catch (error) {
        console.error('Failed to get user roles:', error);
        return [];
    }
}

/**
 * Check if user has a specific role
 * @param {string} role - Role to check for
 * @returns {boolean} True if user has the role
 */
export function hasRole(role) {
    const roles = getUserRoles();
    return roles.includes(role);
}

/**
 * Check if user has any of the specified roles
 * @param {Array<string>} roles - Roles to check for
 * @returns {boolean} True if user has any of the roles
 */
export function hasAnyRole(...roles) {
    const userRoles = getUserRoles();
    return roles.some(role => userRoles.includes(role));
}

/**
 * Check if user has all of the specified roles
 * @param {Array<string>} roles - Roles to check for
 * @returns {boolean} True if user has all of the roles
 */
export function hasAllRoles(...roles) {
    const userRoles = getUserRoles();
    return roles.every(role => userRoles.includes(role));
}

/**
 * Check if user is an admin
 * @returns {boolean} True if user is admin
 */
export function isAdmin() {
    return hasRole('admin');
}

/**
 * Check if user is a manager
 * @returns {boolean} True if user is manager
 */
export function isManager() {
    return hasRole('manager');
}

/**
 * Check if user is admin or manager
 * @returns {boolean} True if user is admin or manager
 */
export function isAdminOrManager() {
    return hasAnyRole('admin', 'manager');
}
