import { apiRequest } from '../api/client.js';
import { login } from '../ui/auth.js';

class SessionManager {
    constructor() {
        this.checkInterval = null;
        this.warningShown = false;
        this.bannerId = 'session-warning-banner';
    }

    async init() {
        await this.checkSession();
        // Check session status every minute
        this.checkInterval = setInterval(() => this.checkSession(), 60000);
    }

    async checkSession() {
        try {
            const response = await apiRequest('/api/auth/session');
            const data = await response.json();

            if (!data.authenticated) {
                // If not authenticated, client.js handles 401, but if it returns 200 with auth=false
                // (e.g. public endpoint or logic), we might need to handle it.
                // But get_session_info returns 200 even if not authenticated (if no cookie).
                // If we are in the app, we expect to be authenticated.
                // However, we don't want to force login if we are already on login page.
                // But SessionManager is likely initialized in main.js which runs on all pages?
                // We should check if we are already on login page.
                return;
            }

            const expiresInSeconds = data.expires_in_seconds;
            const warningMinutes = data.session_expiration_warning_minutes || 5;
            const warningSeconds = warningMinutes * 60;

            if (expiresInSeconds !== null) {
                if (expiresInSeconds <= 0) {
                    this.handleExpiration();
                } else if (expiresInSeconds <= warningSeconds) {
                    this.showWarning(expiresInSeconds);
                } else {
                    this.hideWarning();
                }
            }
        } catch (error) {
            console.error('Session check failed:', error);
        }
    }

    showWarning(secondsRemaining) {
        const minutes = Math.floor(secondsRemaining / 60);
        const seconds = secondsRemaining % 60;
        const timeString = `${minutes}:${seconds.toString().padStart(2, '0')}`;

        if (this.warningShown) {
            // Update timer if needed
            const timerEl = document.getElementById('session-timer');
            if (timerEl) {
                timerEl.textContent = timeString;
            }
            return;
        }

        this.warningShown = true;

        // Create banner
        const banner = document.createElement('div');
        banner.id = this.bannerId;
        banner.className = 'alert alert-warning fixed-top m-0 text-center d-flex justify-content-center align-items-center';
        banner.style.zIndex = '9999';
        banner.innerHTML = `
            <span class="me-3">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                Your session will expire in <strong id="session-timer">${timeString}</strong>.
            </span>
            <button id="extend-session-btn" class="btn btn-sm btn-primary me-2">Extend Session</button>
            <button type="button" class="btn-close" aria-label="Close"></button>
        `;

        document.body.prepend(banner);

        // Add event listeners
        document.getElementById('extend-session-btn').addEventListener('click', () => this.extendSession());

        // Handle dismiss
        banner.querySelector('.btn-close').addEventListener('click', () => {
            banner.remove();
            // We keep warningShown = true so it doesn't pop up again immediately on next check
            // unless we want it to.
            // If we want it to reappear, we should set warningShown = false.
            // But if it checks every minute, it will reappear every minute.
            // Let's keep it dismissed until we decide otherwise (e.g. critical threshold).
            // For now, just dismiss.
        });
    }

    hideWarning() {
        const banner = document.getElementById(this.bannerId);
        if (banner) {
            banner.remove();
        }
        this.warningShown = false;
    }

    async extendSession() {
        try {
            await apiRequest('/api/auth/extend-session', { method: 'POST' });
            this.hideWarning();
            await this.checkSession(); // Update status immediately
        } catch (error) {
            console.error('Failed to extend session:', error);
        }
    }

    stop() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
        this.hideWarning();
    }

    handleExpiration() {
        this.hideWarning();
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
        }
        // Redirect to login (using auth.js login which redirects to Keycloak,
        // or showLoginForm which shows login form?
        // Requirement: "redirects to the login view and hides everything else"
        // showLoginForm does that.
        // But if session is really expired, we might want to refresh the page or go to /api/auth/login
        // to start a new flow.
        // client.js uses showLoginForm().
        // Let's use showLoginForm() too.
        import('../ui/auth.js').then(({ showLoginForm }) => {
            showLoginForm();
        });
    }
}

export const sessionManager = new SessionManager();
