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

            // Worker terminated event
            this.eventSource.addEventListener('worker.terminated', event => {
                const data = JSON.parse(event.data);
                console.log('SSE: Worker terminated', data);
                this.emit('worker.terminated', data.data);
                showToast(`Worker terminated: ${data.data.name}`, 'warning');
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
        this.disconnect();

        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);

        console.log(`SSE: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})...`);

        this._notifyStatus('reconnecting');
        setTimeout(() => {
            if (!this.isConnected) {
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
        if (this.eventHandlers[eventType]) {
            this.eventHandlers[eventType].forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`SSE: Error in event handler for ${eventType}:`, error);
                }
            });
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
}

// Global SSE client instance
const sseClient = new SSEClient();

export default sseClient;
export { sseClient };
