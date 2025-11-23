import * as bootstrap from 'bootstrap';

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
    // Close all open Bootstrap modals
    const openModals = document.querySelectorAll('.modal.show');
    openModals.forEach(modalElement => {
        const modalInstance = bootstrap.Modal.getInstance(modalElement);
        if (modalInstance) {
            modalInstance.hide();
        } else {
            // Fallback: manually hide if instance not found
            modalElement.classList.remove('show');
            modalElement.style.display = 'none';
            modalElement.setAttribute('aria-hidden', 'true');
            modalElement.removeAttribute('aria-modal');
            modalElement.removeAttribute('role');
        }
    });

    // Remove any lingering modal backdrops
    const backdrops = document.querySelectorAll('.modal-backdrop');
    backdrops.forEach(backdrop => backdrop.remove());

    // Reset body classes that Bootstrap adds for modals
    document.body.classList.remove('modal-open');
    document.body.style.overflow = '';
    document.body.style.paddingRight = '';

    // Show login, hide dashboard
    document.getElementById('login-section').style.display = 'flex';
    document.getElementById('dashboard-section').style.display = 'none';
    document.getElementById('logout-btn').style.display = 'none';
    document.getElementById('user-info').textContent = '';

    // Hide demo users info if not in dev environment
    const demoUsersInfo = document.getElementById('demo-users-info');
    if (demoUsersInfo) {
        const env = (window.APP_CONFIG && window.APP_CONFIG.environment) || 'development';
        if (!env.startsWith('dev')) {
            demoUsersInfo.style.display = 'none';
        } else {
            demoUsersInfo.style.display = 'block';
        }
    }

    // Hide all other sections
    const workersSection = document.getElementById('workers-section');
    const systemView = document.getElementById('system-view');
    const mainNav = document.getElementById('main-nav');
    if (workersSection) workersSection.style.display = 'none';
    if (systemView) systemView.style.display = 'none';
    if (mainNav) mainNav.style.display = 'none';

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
