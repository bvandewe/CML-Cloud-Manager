/**
 * SSEService - Refactored Server-Sent Events Client
 *
 * Integrates with EventBus instead of custom event emitter.
 * Cleaner, more maintainable SSE handling.
 */

import { eventBus, EventTypes } from '../core/EventBus.js';

export class SSEService {
    constructor() {
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.reconnectTimer = null;
        this.isIntentionalDisconnect = false;
    }

    /**
     * Connect to SSE endpoint
     */
    connect() {
        if (this.eventSource) {
            console.log('[SSE] Already connected');
            return;
        }

        console.log('[SSE] Connecting to /api/events/stream...');

        try {
            this.eventSource = new EventSource('/api/events/stream', {
                withCredentials: true,
            });

            // Connection established
            this.eventSource.addEventListener('connected', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Connected', data);
                this.isConnected = true;
                this.reconnectDelay = 1000;
                this.reconnectAttempts = 0;

                eventBus.emit(EventTypes.SSE_CONNECTED, data);
            });

            // Heartbeat
            this.eventSource.addEventListener('heartbeat', event => {
                const data = JSON.parse(event.data);
                console.debug('[SSE] Heartbeat', data.timestamp);
            });

            // Worker events - map to EventBus
            this.eventSource.addEventListener('worker.snapshot', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker snapshot', data);
                eventBus.emit(EventTypes.WORKER_SNAPSHOT, data.data);
            });

            this.eventSource.addEventListener('worker.metrics.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker metrics updated', data);
                eventBus.emit(EventTypes.WORKER_METRICS_UPDATED, data.data);
            });

            this.eventSource.addEventListener('worker.status.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker status updated', data);
                eventBus.emit(EventTypes.WORKER_STATUS_CHANGED, data.data);
            });

            this.eventSource.addEventListener('worker.created', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker created', data);
                eventBus.emit(EventTypes.WORKER_CREATED, data.data);
            });

            this.eventSource.addEventListener('worker.imported', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker imported', data);
                eventBus.emit(EventTypes.WORKER_IMPORTED, data.data);
            });

            this.eventSource.addEventListener('worker.labs.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker labs updated', data);
                eventBus.emit(EventTypes.LAB_UPDATED, data.data);
            });

            // Error handling
            this.eventSource.onerror = error => {
                console.error('[SSE] Connection error', error);
                this.isConnected = false;

                eventBus.emit(EventTypes.SSE_ERROR, { error });

                if (!this.isIntentionalDisconnect) {
                    this.scheduleReconnect();
                }
            };
        } catch (error) {
            console.error('[SSE] Failed to connect:', error);
            eventBus.emit(EventTypes.SSE_ERROR, { error });
            this.scheduleReconnect();
        }
    }

    /**
     * Disconnect from SSE
     */
    disconnect() {
        this.isIntentionalDisconnect = true;

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.isConnected = false;
            console.log('[SSE] Disconnected');

            eventBus.emit(EventTypes.SSE_DISCONNECTED, {});
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        if (this.reconnectTimer || this.isIntentionalDisconnect) {
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), this.maxReconnectDelay);

        console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
            this.connect();
        }, delay);
    }

    /**
     * Get connection status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
        };
    }
}

// Singleton instance
export const sseService = new SSEService();

export default sseService;
