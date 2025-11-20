/**
 * Application Entry Point
 * Main application initialization and event handling
 */

import { checkAuth } from './api/client.js';
import { login, logout, showLoginForm, showDashboard } from './ui/auth.js';
import { loadTasks, handleCreateTask, handleUpdateTask } from './ui/tasks.js';
import { initializeWorkersView } from './ui/workers.js';
import { initializeSystemView } from './ui/system.js';
import { initializeTheme } from './services/theme.js';

// Current user and active view
let currentUser = null;
let activeView = 'tasks';

// Session monitoring
let sessionCheckInterval = null;
let sessionWarningShown = false;
const SESSION_CHECK_INTERVAL = 60000; // Check every 1 minute
const SESSION_WARNING_THRESHOLD = 300; // Warn when 5 minutes remaining
const SESSION_REFRESH_INTERVAL = 1800000; // Refresh every 30 minutes during activity

/**
 * Check session expiration and warn/redirect as needed
 */
async function checkSessionExpiration() {
    try {
        const response = await fetch('/api/auth/session', {
            credentials: 'include',
        });

        if (!response.ok) {
            // API error - stop monitoring and redirect to login
            stopSessionMonitoring();
            showLoginForm();
            return;
        }

        const sessionInfo = await response.json();

        if (!sessionInfo.authenticated) {
            // Session expired - redirect to login
            console.log('[Session] Session expired, redirecting to login');
            stopSessionMonitoring();
            const { showToast } = await import('./ui/notifications.js');
            showToast('Your session has expired. Please log in again.', 'warning');
            showLoginForm();
            return;
        }

        const expiresInSeconds = sessionInfo.expires_in_seconds;
        if (expiresInSeconds !== null && expiresInSeconds <= SESSION_WARNING_THRESHOLD) {
            // Session expiring soon - warn user once
            if (!sessionWarningShown) {
                sessionWarningShown = true;
                const { showToast } = await import('./ui/notifications.js');
                const minutes = Math.ceil(expiresInSeconds / 60);
                showToast(`Your session will expire in ${minutes} minute${minutes !== 1 ? 's' : ''}. Please save your work.`, 'warning');
            }
        }

        // Auto-redirect when session expires
        if (expiresInSeconds !== null && expiresInSeconds <= 0) {
            console.log('[Session] Session expired, redirecting to login');
            stopSessionMonitoring();
            const { showToast } = await import('./ui/notifications.js');
            showToast('Your session has expired. Please log in again.', 'warning');
            showLoginForm();
        }
    } catch (error) {
        console.error('[Session] Error checking session expiration:', error);
        // Continue monitoring - transient errors shouldn't force logout
    }
}

/**
 * Start monitoring session expiration
 */
function startSessionMonitoring() {
    if (sessionCheckInterval) {
        return; // Already monitoring
    }

    console.log('[Session] Starting session monitoring');
    sessionWarningShown = false;

    // Check immediately
    checkSessionExpiration();

    // Then check periodically
    sessionCheckInterval = setInterval(checkSessionExpiration, SESSION_CHECK_INTERVAL);
}

/**
 * Stop monitoring session expiration
 */
function stopSessionMonitoring() {
    if (sessionCheckInterval) {
        console.log('[Session] Stopping session monitoring');
        clearInterval(sessionCheckInterval);
        sessionCheckInterval = null;
        sessionWarningShown = false;
    }
}

/**
 * Initialize the application
 */
async function initializeApp() {
    // Check if user is authenticated
    const user = await checkAuth();

    if (user) {
        // User is logged in - show dashboard
        currentUser = user;
        showDashboard(user);

        // Show navigation
        const mainNav = document.getElementById('main-nav');
        if (mainNav) {
            mainNav.style.display = 'flex';
        }

        // Start session monitoring
        startSessionMonitoring();

        // Show default view - changed to workers for debugging
        console.log('[APP] Showing default view: workers');
        showView('workers');
    } else {
        // Not logged in - show login button
        stopSessionMonitoring();
        showLoginForm();
    }
}

/**
 * Show specific view
 * @param {string} view - View name: 'tasks', 'workers', or 'system'
 */
function showView(view) {
    console.log('[APP showView] Called with view:', view);
    activeView = view;

    // Hide all sections
    const dashboardSection = document.getElementById('dashboard-section');
    const workersSection = document.getElementById('workers-section');
    const systemSection = document.getElementById('system-view');

    if (dashboardSection) dashboardSection.style.display = 'none';
    if (workersSection) workersSection.style.display = 'none';
    if (systemSection) systemSection.style.display = 'none';

    // Update nav links
    const navTasks = document.getElementById('nav-tasks');
    const navWorkers = document.getElementById('nav-workers');
    const navSystem = document.getElementById('nav-system');

    if (navTasks) navTasks.classList.remove('active');
    if (navWorkers) navWorkers.classList.remove('active');
    if (navSystem) navSystem.classList.remove('active');

    // Show selected section
    if (view === 'tasks') {
        console.log('[APP showView] Showing tasks view');
        if (dashboardSection) dashboardSection.style.display = 'block';
        if (navTasks) navTasks.classList.add('active');
        loadTasks();
    } else if (view === 'workers') {
        console.log('[APP showView] Showing workers view');
        if (workersSection) workersSection.style.display = 'block';
        if (navWorkers) navWorkers.classList.add('active');
        console.log('[APP showView] Calling initializeWorkersView with user:', currentUser);
        initializeWorkersView(currentUser);
        console.log('[APP showView] initializeWorkersView completed');
    } else if (view === 'system') {
        console.log('[APP showView] Showing system view');
        if (systemSection) systemSection.style.display = 'block';
        if (navSystem) navSystem.classList.add('active');
        initializeSystemView();
    }
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Login button (redirect to Keycloak)
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn) {
        loginBtn.addEventListener('click', login);
    }

    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            stopSessionMonitoring();
            logout();
        });
    }

    // Navigation links
    const navTasks = document.getElementById('nav-tasks');
    if (navTasks) {
        navTasks.addEventListener('click', e => {
            e.preventDefault();
            showView('tasks');
        });
    }

    const navWorkers = document.getElementById('nav-workers');
    if (navWorkers) {
        navWorkers.addEventListener('click', e => {
            e.preventDefault();
            showView('workers');
        });
    }

    const navSystem = document.getElementById('nav-system');
    if (navSystem) {
        navSystem.addEventListener('click', e => {
            e.preventDefault();
            showView('system');
        });
    }

    // Create task button
    const submitTaskBtn = document.getElementById('submit-task-btn');
    if (submitTaskBtn) {
        submitTaskBtn.addEventListener('click', handleCreateTask);
    }

    // Edit task button
    const submitEditTaskBtn = document.getElementById('submit-edit-task-btn');
    if (submitEditTaskBtn) {
        submitEditTaskBtn.addEventListener('click', handleUpdateTask);
    }
}

/**
 * Application startup
 */
document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    await initializeApp();
});
