/**
 * Theme Switcher Service
 * Handles light/dark theme toggling with localStorage persistence
 */

const THEME_KEY = 'cml-theme';
const DARK_THEME = 'dark';
const LIGHT_THEME = 'light';

/**
 * Get the current theme from localStorage or default to light
 * @returns {string} Current theme ('light' or 'dark')
 */
export function getCurrentTheme() {
    return localStorage.getItem(THEME_KEY) || LIGHT_THEME;
}

/**
 * Set the theme
 * @param {string} theme - Theme to set ('light' or 'dark')
 */
export function setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
}

/**
 * Toggle between light and dark themes
 * @returns {string} New theme
 */
export function toggleTheme() {
    const currentTheme = getCurrentTheme();
    const newTheme = currentTheme === DARK_THEME ? LIGHT_THEME : DARK_THEME;
    setTheme(newTheme);
    return newTheme;
}

/**
 * Apply theme to the document
 * @param {string} theme - Theme to apply
 */
function applyTheme(theme) {
    const html = document.documentElement;
    const themeIcon = document.getElementById('theme-icon');

    if (theme === DARK_THEME) {
        // Dark theme: white on black
        html.setAttribute('data-bs-theme', 'dark');
        if (themeIcon) {
            themeIcon.className = 'bi bi-sun-fill';
        }
    } else {
        // Light theme: black on white (Bootstrap default)
        html.setAttribute('data-bs-theme', 'light');
        if (themeIcon) {
            themeIcon.className = 'bi bi-moon-fill';
        }
    }
}

/**
 * Initialize theme on page load
 */
export function initializeTheme() {
    const savedTheme = getCurrentTheme();
    applyTheme(savedTheme);

    // Setup theme toggle button
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            toggleTheme();
        });
    }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeTheme);
} else {
    initializeTheme();
}
