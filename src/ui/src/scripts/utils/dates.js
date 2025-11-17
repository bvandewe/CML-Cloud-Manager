/**
 * Date Utility Functions
 * Provides date formatting and relative time utilities
 */

/**
 * Calculate relative time from a date to now
 * @param {Date} date - The date to compare
 * @returns {string} Relative time string (e.g., "2 hours ago", "in 3 days")
 */
export function getRelativeTime(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);
    const diffWeek = Math.floor(diffDay / 7);
    const diffMonth = Math.floor(diffDay / 30);
    const diffYear = Math.floor(diffDay / 365);

    const isFuture = diffMs < 0;
    const prefix = isFuture ? 'in ' : '';
    const suffix = isFuture ? '' : ' ago';

    const absDiffSec = Math.abs(diffSec);
    const absDiffMin = Math.abs(diffMin);
    const absDiffHour = Math.abs(diffHour);
    const absDiffDay = Math.abs(diffDay);
    const absDiffWeek = Math.abs(diffWeek);
    const absDiffMonth = Math.abs(diffMonth);
    const absDiffYear = Math.abs(diffYear);

    if (absDiffSec < 10) {
        return 'just now';
    } else if (absDiffSec < 60) {
        return `${prefix}${absDiffSec} second${absDiffSec !== 1 ? 's' : ''}${suffix}`;
    } else if (absDiffMin < 60) {
        return `${prefix}${absDiffMin} minute${absDiffMin !== 1 ? 's' : ''}${suffix}`;
    } else if (absDiffHour < 24) {
        return `${prefix}${absDiffHour} hour${absDiffHour !== 1 ? 's' : ''}${suffix}`;
    } else if (absDiffDay < 7) {
        return `${prefix}${absDiffDay} day${absDiffDay !== 1 ? 's' : ''}${suffix}`;
    } else if (absDiffWeek < 5) {
        return `${prefix}${absDiffWeek} week${absDiffWeek !== 1 ? 's' : ''}${suffix}`;
    } else if (absDiffMonth < 12) {
        return `${prefix}${absDiffMonth} month${absDiffMonth !== 1 ? 's' : ''}${suffix}`;
    } else {
        return `${prefix}${absDiffYear} year${absDiffYear !== 1 ? 's' : ''}${suffix}`;
    }
}

/**
 * Format a date string with an info icon showing relative time
 * @param {string} dateString - ISO date string
 * @returns {string} HTML string with formatted date and relative time tooltip
 */
export function formatDateWithRelative(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        const formatted = date.toLocaleString();
        const relative = getRelativeTime(date);

        // Generate unique ID for tooltip
        const uniqueId = `date-tooltip-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        return `${formatted} <i class="bi bi-info-circle text-muted date-tooltip-icon"
                data-bs-toggle="tooltip"
                data-bs-placement="top"
                data-bs-title="${relative}"
                data-tooltip-id="${uniqueId}"
                style="cursor: help;"></i>`;
    } catch (e) {
        return dateString;
    }
}

/**
 * Initialize Bootstrap tooltips for date icons
 * Should be called after rendering content with date tooltips
 */
export function initializeDateTooltips() {
    // Import bootstrap dynamically to avoid circular dependencies
    import('bootstrap').then(bootstrap => {
        const tooltipElements = document.querySelectorAll('.date-tooltip-icon');

        tooltipElements.forEach(element => {
            // Dispose existing tooltip if any
            const existingTooltip = bootstrap.Tooltip.getInstance(element);
            if (existingTooltip) {
                existingTooltip.dispose();
            }

            // Create new tooltip
            const tooltip = new bootstrap.Tooltip(element, {
                trigger: 'hover',
                container: 'body',
            });

            // Ensure tooltip is hidden when mouse leaves
            element.addEventListener('mouseleave', () => {
                tooltip.hide();
            });
        });
    });
}

/**
 * Format a date string (without relative time, for backward compatibility)
 * @param {string} dateString - ISO date string
 * @returns {string} Formatted date string
 */
export function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}
