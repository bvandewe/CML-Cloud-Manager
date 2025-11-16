/**
 * Authentication UI Module
 * Handles login/logout UI interactions
 */

/**
 * Redirect to Keycloak login
 */
export function login() {
    window.location.href = '/api/auth/login';
}

/**
 * Redirect to logout
 */
export function logout() {
    window.location.href = '/api/auth/logout';
}

/**
 * Show login form (hide dashboard)
 */
export function showLoginForm() {
    document.getElementById('login-section').style.display = 'flex';
    document.getElementById('dashboard-section').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    document.getElementById('user-info').textContent = '';

    // Clear user roles from localStorage on logout
    localStorage.removeItem('user_roles');
}

/**
 * Show dashboard (hide login form)
 * @param {Object} user - User object from auth
 */
export function showDashboard(user) {
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('dashboard-section').style.display = 'block';
    document.getElementById('logout-btn').style.display = 'block';
    document.getElementById('user-info').textContent = `${user.preferred_username || user.email} (${user.email})`;

    // Store user roles in localStorage for UI role checks
    if (user.roles) {
        localStorage.setItem('user_roles', JSON.stringify(user.roles));
    }

    // Show/hide nav items based on role - System nav is admin-only
    const isAdmin = user.roles && user.roles.includes('admin');
    const adminOnlyNavItems = document.querySelectorAll('.admin-only-nav');
    adminOnlyNavItems.forEach(item => {
        if (isAdmin) {
            item.style.display = ''; // Reset to default display
        } else {
            item.style.display = 'none';
        }
    });
}
