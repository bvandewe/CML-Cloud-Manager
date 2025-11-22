/**
 * SSE (Server-Sent Events) Client for Real-Time UI Updates
 *
 * Subscribes to server-sent events and automatically updates the UI
 * when worker metrics, labs, or status changes occur.
 */

import { showToast } from '../ui/notifications.js';

class SSEClient {
    constructor() {
        this.eventSource = null;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.eventHandlers = {};
        this.statusHandlers = [];
        this.reconnectTimer = null;
        this.isIntentionalDisconnect = false;

        // Setup cleanup handlers
        this._setupCleanupHandlers();
    }

    /**
     * Connect to the SSE endpoint
     */
    connect() {
        if (this.eventSource) {
            console.log('SSE: Already connected');
            return;
        }

        console.log('SSE: Connecting to /api/events/stream...');

        try {
            this.eventSource = new EventSource('/api/events/stream', {
                withCredentials: true,
            });

            this.eventSource.addEventListener('connected', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Connected', data);
                this.isConnected = true;
                this.reconnectDelay = 1000; // Reset reconnect delay
                this.reconnectAttempts = 0;
                showToast('Realtime connected', 'success');
                this._notifyStatus('connected');
            });

            this.eventSource.addEventListener('heartbeat', event => {
                const data = JSON.parse(event.data);
                console.debug('SSE: Heartbeat', data.timestamp);
            });

            // Worker snapshot event (complete worker state)
            this.eventSource.addEventListener('worker.snapshot', event => {
                console.log('[sse-client] EventSource received worker.snapshot, raw event.data:', event.data.substring(0, 200));
                const data = JSON.parse(event.data);
                console.log('[sse-client] Parsed worker.snapshot data:', {
                    type: data.type,
                    source: data.source,
                    hasData: !!data.data,
                    worker_id: data.data?.worker_id,
                    license_status: data.data?.license_status,
                    cml_license_info: data.data?.cml_license_info,
                });
                console.log('SSE: Worker snapshot', data);
                this.emit('worker.snapshot', data.data);
            });

            // Worker metrics updated event
            this.eventSource.addEventListener('worker.metrics.updated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker metrics updated', data);
                this.emit('worker.metrics.updated', data.data);
            });

            // Worker labs updated event
            this.eventSource.addEventListener('worker.labs.updated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker labs updated', data);
                this.emit('worker.labs.updated', data.data);
            });

            // Worker status changed event
            this.eventSource.addEventListener('worker.status.updated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker status updated', data);
                this.emit('worker.status.updated', data.data);
            });

            // Worker created event
            this.eventSource.addEventListener('worker.created', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker created', data);
                this.emit('worker.created', data.data);
                showToast(`Worker created: ${data.data.name}`, 'info');
            });

            // Worker imported event
            this.eventSource.addEventListener('worker.imported', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker imported', data);
                this.emit('worker.imported', data.data);
                showToast(`Worker imported: ${data.data.name}`, 'success');
            });

            // Worker terminated event
            this.eventSource.addEventListener('worker.terminated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker terminated', data);
                this.emit('worker.terminated', data.data);
                showToast(`Worker terminated: ${data.data.name}`, 'warning');
            });

            // Worker activity updated event
            this.eventSource.addEventListener('worker.activity.updated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker activity updated', data);
                this.emit('worker.activity.updated', data.data);
            });

            // Worker paused event
            this.eventSource.addEventListener('worker.paused', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker paused', data);
                this.emit('worker.paused', data.data);
            });

            // Worker resumed event
            this.eventSource.addEventListener('worker.resumed', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker resumed', data);
                this.emit('worker.resumed', data.data);
            });

            // Worker refresh throttled event
            this.eventSource.addEventListener('worker.refresh.throttled', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker refresh throttled', data);
                const retryMsg = data.data.retry_after_seconds ? ` Please wait ${data.data.retry_after_seconds}s.` : '';
                showToast(`Refresh rate limited.${retryMsg}`, 'warning');
                this.emit('worker.refresh.throttled', data.data);
            });

            // Worker data refreshed event (signals UI to reload from DB)
            this.eventSource.addEventListener('worker.data.refreshed', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker data refreshed', data);
                this.emit('worker.data.refreshed', data.data);
            });

            // System shutdown event - server is restarting or shutting down
            this.eventSource.addEventListener('system.sse.shutdown', event => {
                console.log('SSE: System shutdown received', event.data);
                showToast('Server restarting, reconnecting...', 'warning');
                // Close connection immediately to allow server to shutdown cleanly
                this.disconnect();
                // Attempt to reconnect after a short delay
                setTimeout(() => {
                    console.log('SSE: Attempting to reconnect after shutdown...');
                    this.connect();
                }, 2000);
            });

            // License registration started event
            this.eventSource.addEventListener('worker.license.registration.started', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: License registration started', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`License registration started for ${workerName}`, 'info');
                this.emit('worker.license.registration.started', data.data);
            });

            // License registration completed event
            this.eventSource.addEventListener('worker.license.registration.completed', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: License registration completed', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`✅ License registered successfully for ${workerName}! Click to dismiss.`, 'success', 0);
                this.emit('worker.license.registration.completed', data.data);
            });

            // License registration failed event
            this.eventSource.addEventListener('worker.license.registration.failed', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: License registration failed', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                const reason = data.data.reason || 'Unknown error';
                showToast(`License registration failed for ${workerName}: ${reason}`, 'error', 8000);
                this.emit('worker.license.registration.failed', data.data);
            });

            // License deregistered event
            this.eventSource.addEventListener('worker.license.deregistered', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: License deregistered', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`License deregistered from ${workerName}`, 'info');
                this.emit('worker.license.deregistered', data.data);
            });

            // Error handling
            this.eventSource.addEventListener('error', event => {
                console.error('SSE: Error event', event);
                if (this.eventSource && this.eventSource.readyState === EventSource.CLOSED) {
                    console.log('SSE: Connection closed, will attempt to reconnect...');
                    this.isConnected = false;
                    this._notifyStatus('disconnected');
                    this.handleReconnect();
                } else {
                    this._notifyStatus('error');
                }
            });

            this.eventSource.onerror = error => {
                console.error('SSE: Connection error', error);
                this.isConnected = false;
                this._notifyStatus('error');
                if (this.eventSource && this.eventSource.readyState === EventSource.CLOSED) {
                    this._notifyStatus('disconnected');
                    this.handleReconnect();
                } else {
                    this.handleReconnect();
                }
            };
        } catch (error) {
            console.error('SSE: Failed to connect', error);
            this._notifyStatus('error');
            this.handleReconnect();
        }
    }

    /**
     * Handle reconnection with exponential backoff
     */
    handleReconnect() {
        // Don't reconnect if this was an intentional disconnect
        if (this.isIntentionalDisconnect) {
            console.log('SSE: Skipping reconnection (intentional disconnect)');
            return;
        }

        this.disconnect();

        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);

        console.log(`SSE: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})...`);

        this._notifyStatus('reconnecting');
        this.reconnectTimer = setTimeout(() => {
            if (!this.isConnected && !this.isIntentionalDisconnect) {
                this.connect();
            }
        }, delay);
    }

    /**
     * Disconnect from SSE endpoint
     */
    disconnect() {
        if (this.eventSource) {
            console.log('SSE: Disconnecting...');
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
            this._notifyStatus('disconnected');
        }

        // Clear any pending reconnection timer
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    /**
     * Register an event handler
     * @param {string} eventType - Event type to listen for
     * @param {Function} handler - Handler function
     */
    on(eventType, handler) {
        if (!this.eventHandlers[eventType]) {
            this.eventHandlers[eventType] = [];
        }
        this.eventHandlers[eventType].push(handler);
    }

    /**
     * Unregister an event handler
     * @param {string} eventType - Event type
     * @param {Function} handler - Handler function to remove
     */
    off(eventType, handler) {
        if (this.eventHandlers[eventType]) {
            this.eventHandlers[eventType] = this.eventHandlers[eventType].filter(h => h !== handler);
        }
    }

    /**
     * Emit an event to registered handlers
     * @param {string} eventType - Event type
     * @param {object} data - Event data
     */
    emit(eventType, data) {
        console.log('[sse-client] emit() called:', {
            eventType,
            hasHandlers: !!this.eventHandlers[eventType],
            handlerCount: this.eventHandlers[eventType]?.length || 0,
            data:
                eventType === 'worker.snapshot'
                    ? {
                          worker_id: data?.worker_id,
                          license_status: data?.license_status,
                          cml_license_info: data?.cml_license_info,
                      }
                    : 'other',
        });

        if (this.eventHandlers[eventType]) {
            this.eventHandlers[eventType].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`SSE: Error in event handler for ${eventType}:`, error);
                }
            });
        } else {
            console.warn(`[sse-client] No handlers registered for event type: ${eventType}`);
        }
    }

    /**
     * Check if SSE is connected
     * @returns {boolean} Connection status
     */
    isConnectedStatus() {
        return this.isConnected && this.eventSource && this.eventSource.readyState === EventSource.OPEN;
    }

    /**
     * Register a status handler callback
     * @param {Function} handler
     */
    onStatus(handler) {
        this.statusHandlers.push(handler);
    }

    /**
     * Internal: notify status handlers
     */
    _notifyStatus(status) {
        this.statusHandlers.forEach(h => {
            try {
                h(status);
            } catch (e) {
                console.error('SSE: status handler error', e);
            }
        });
    }

    /**
     * Setup cleanup handlers for page lifecycle events
     */
    _setupCleanupHandlers() {
        // Gracefully disconnect when page is about to unload (refresh, close, navigate)
        window.addEventListener('beforeunload', () => {
            console.log('SSE: Page unloading, closing connection gracefully');
            this.isIntentionalDisconnect = true;
            this.disconnect();
        });

        // Handle page visibility changes (tab switching)
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('SSE: Page hidden, maintaining connection');
                // Keep connection alive but could reduce polling if needed
            } else {
                console.log('SSE: Page visible');
                // Ensure connection is active when page becomes visible
                if (!this.isConnectedStatus() && !this.isIntentionalDisconnect) {
                    console.log('SSE: Reconnecting after page became visible');
                    this.connect();
                }
            }
        });

        // Handle page freeze/resume events (mobile browsers, background tabs)
        window.addEventListener('freeze', () => {
            console.log('SSE: Page frozen, disconnecting');
            this.isIntentionalDisconnect = true;
            this.disconnect();
        });

        window.addEventListener('resume', () => {
            console.log('SSE: Page resumed, reconnecting');
            this.isIntentionalDisconnect = false;
            if (!this.isConnectedStatus()) {
                this.connect();
            }
        });
    }
}

// Global SSE client instance
const sseClient = new SSEClient();

export default sseClient;
export { sseClient };
