/**
 * Application Entry Point
 * Main application initialization and event handling
 *
 * MIGRATION NOTE: Supports both legacy and Web Components implementation via feature flag.
 */

import { checkAuth } from './api/client.js';
import { login, logout, showLoginForm, showDashboard } from './ui/auth.js';
import { loadTasks, handleCreateTask, handleUpdateTask } from './ui/tasks.js';
import { initializeSystemView } from './ui/system.js';
import { initializeSettingsView } from './ui/settings.js';
import { initializeTheme } from './services/theme.js';
import { sessionManager } from './services/session-manager.js';
import { eventBus, EventTypes } from './core/EventBus.js';

// Current user and active view
let currentUser = null;
let activeView = 'tasks';

/**
 * Initialize the application
 */
async function initializeApp() {
    // Set page title from config
    if (window.APP_CONFIG && window.APP_CONFIG.title) {
        document.title = window.APP_CONFIG.title;
    }

    // Set app version in footer
    const versionElement = document.getElementById('app-version');
    if (versionElement && window.APP_CONFIG && window.APP_CONFIG.version) {
        versionElement.textContent = window.APP_CONFIG.version;
    }

    // Check if user is authenticated
    const user = await checkAuth();

    if (user) {
        // User is logged in - show dashboard
        currentUser = user;
        const hasValidRole = await showDashboard(user);

        // Only proceed if user has valid role
        if (!hasValidRole) {
            console.warn('[APP] User lacks required roles, showing error page');
            return;
        }

        // Show navigation
        const mainNav = document.getElementById('main-nav');
        if (mainNav) {
            mainNav.style.display = 'flex';
        }

        // Start session monitoring
        sessionManager.init();

        // Subscribe to session expiration
        eventBus.on(EventTypes.AUTH_SESSION_EXPIRED, () => {
            console.warn('[APP] Session expired via SSE');
            sessionManager.stop();
            showLoginForm();
        });

        // Show default view - changed to workers for debugging
        console.log('[APP] Showing default view: workers');
        showView('workers');
    } else {
        // Not logged in - show login button
        sessionManager.stop();
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
    const settingsSection = document.getElementById('settings-section');

    if (dashboardSection) dashboardSection.style.display = 'none';
    if (workersSection) workersSection.style.display = 'none';
    if (systemSection) systemSection.style.display = 'none';
    if (settingsSection) settingsSection.style.display = 'none';

    // Update nav links
    const navTasks = document.getElementById('nav-tasks');
    const navWorkers = document.getElementById('nav-workers');
    const navSystem = document.getElementById('nav-system');
    const navSettings = document.getElementById('nav-settings');

    if (navTasks) navTasks.classList.remove('active');
    if (navWorkers) navWorkers.classList.remove('active');
    if (navSystem) navSystem.classList.remove('active');
    if (navSettings) navSettings.classList.remove('active');

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

        // Always use Web Components implementation
        console.log('[APP] Using Web Components implementation');
        import('./components/WorkersApp.js').then(module => {
            module.initializeWorkersView(currentUser);
        });

        console.log('[APP showView] initializeWorkersView completed');
    } else if (view === 'system') {
        console.log('[APP showView] Showing system view');
        if (systemSection) systemSection.style.display = 'block';
        if (navSystem) navSystem.classList.add('active');
        initializeSystemView();
    } else if (view === 'settings') {
        console.log('[APP showView] Showing settings view');
        if (settingsSection) settingsSection.style.display = 'block';
        if (navSettings) navSettings.classList.add('active');
        initializeSettingsView();
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
        logoutBtn.addEventListener('click', e => {
            e.preventDefault();
            sessionManager.stop();
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

    const navSettings = document.getElementById('nav-settings');
    if (navSettings) {
        navSettings.addEventListener('click', e => {
            e.preventDefault();
            showView('settings');
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
