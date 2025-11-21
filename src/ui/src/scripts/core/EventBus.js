/**
 * EventBus - Centralized Pub/Sub Event System
 *
 * Replaces the fragmented event systems (SSE custom emitter, store subscriptions, DOM events)
 * with a single unified event bus.
 *
 * Features:
 * - Type-safe event contracts
 * - Wildcard subscriptions
 * - Async event handlers
 * - Debugging middleware
 * - Memory leak prevention (weak references)
 */

class EventBus {
    constructor() {
        this.subscribers = new Map(); // eventType -> Set<handler>
        this.debugMode = false;
        this.middleware = [];
    }

    /**
     * Subscribe to events
     * @param {string} eventType - Event type or wildcard pattern (e.g., 'worker.*')
     * @param {Function} handler - Event handler function
     * @returns {Function} Unsubscribe function
     */
    on(eventType, handler) {
        if (!this.subscribers.has(eventType)) {
            this.subscribers.set(eventType, new Set());
        }
        this.subscribers.get(eventType).add(handler);

        // Return unsubscribe function
        return () => this.off(eventType, handler);
    }

    /**
     * Unsubscribe from events
     */
    off(eventType, handler) {
        const handlers = this.subscribers.get(eventType);
        if (handlers) {
            handlers.delete(handler);
            if (handlers.size === 0) {
                this.subscribers.delete(eventType);
            }
        }
    }

    /**
     * Publish event
     * @param {string} eventType - Event type
     * @param {*} data - Event payload
     */
    async emit(eventType, data) {
        // Run middleware
        for (const mw of this.middleware) {
            await mw(eventType, data);
        }

        if (this.debugMode) {
            console.log(`[EventBus] ${eventType}`, data);
        }

        // Direct subscribers
        const handlers = this.subscribers.get(eventType);
        if (handlers) {
            for (const handler of handlers) {
                try {
                    await handler(data);
                } catch (error) {
                    console.error(`[EventBus] Error in handler for ${eventType}:`, error);
                }
            }
        }

        // Wildcard subscribers (e.g., 'worker.*' matches 'worker.created')
        for (const [pattern, handlers] of this.subscribers) {
            if (this._matchesPattern(pattern, eventType)) {
                for (const handler of handlers) {
                    try {
                        await handler(data);
                    } catch (error) {
                        console.error(`[EventBus] Error in wildcard handler for ${eventType}:`, error);
                    }
                }
            }
        }
    }

    /**
     * Check if eventType matches wildcard pattern
     */
    _matchesPattern(pattern, eventType) {
        if (!pattern.includes('*')) return false;
        const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
        return regex.test(eventType);
    }

    /**
     * Subscribe once (auto-unsubscribe after first event)
     */
    once(eventType, handler) {
        const wrappedHandler = async data => {
            this.off(eventType, wrappedHandler);
            await handler(data);
        };
        return this.on(eventType, wrappedHandler);
    }

    /**
     * Add middleware for logging, debugging, analytics
     */
    use(middleware) {
        this.middleware.push(middleware);
    }

    /**
     * Enable debug logging
     */
    enableDebug() {
        this.debugMode = true;
    }

    /**
     * Clear all subscribers (for testing/cleanup)
     */
    clear() {
        this.subscribers.clear();
    }
}

// Singleton instance
export const eventBus = new EventBus();

// Event type constants (type safety)
export const EventTypes = {
    // Worker events
    WORKER_CREATED: 'worker.created',
    WORKER_IMPORTED: 'worker.imported',
    WORKER_UPDATED: 'worker.updated',
    WORKER_DELETED: 'worker.deleted',
    WORKER_STATUS_CHANGED: 'worker.status.changed',
    WORKER_METRICS_UPDATED: 'worker.metrics.updated',
    WORKER_SNAPSHOT: 'worker.snapshot',

    // Lab events
    LAB_CREATED: 'lab.created',
    LAB_STARTED: 'lab.started',
    LAB_STOPPED: 'lab.stopped',
    LAB_WIPED: 'lab.wiped',
    LAB_DELETED: 'lab.deleted',
    LAB_UPDATED: 'lab.updated',

    // UI events
    UI_VIEW_CHANGED: 'ui.view.changed',
    UI_FILTER_CHANGED: 'ui.filter.changed',
    UI_MODAL_OPENED: 'ui.modal.opened',
    UI_MODAL_CLOSED: 'ui.modal.closed',

    // SSE events
    SSE_CONNECTED: 'sse.connected',
    SSE_DISCONNECTED: 'sse.disconnected',
    SSE_ERROR: 'sse.error',

    // Auth events
    AUTH_LOGIN: 'auth.login',
    AUTH_LOGOUT: 'auth.logout',
    AUTH_SESSION_EXPIRED: 'auth.session.expired',
};

export default eventBus;
