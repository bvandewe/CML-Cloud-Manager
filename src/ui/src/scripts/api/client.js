/**
 * API Client Module
 * Handles all HTTP requests to the backend API
 */

/**
 * Make an authenticated API request
 * @param {string} url - The API endpoint URL
 * @param {Object} options - Fetch options (method, headers, body, etc.)
 * @returns {Promise<Response>} - The fetch response
 */
export async function apiRequest(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include', // Always send cookies
    });

    if (response.status === 401) {
        // Session expired - trigger login redirect
        const { showLoginForm } = await import('../ui/auth.js');
        showLoginForm();
        throw new Error('Authentication required');
    }

    return response;
}

/**
 * Check if user is authenticated
 * @returns {Promise<Object|null>} - User object or null
 */
export async function checkAuth() {
    try {
        const response = await fetch('/api/auth/user', {
            credentials: 'include', // Send session cookie
        });

        if (response.ok) {
            const user = await response.json();
            return user;
        }

        return null;
    } catch {
        return null;
    }
}
