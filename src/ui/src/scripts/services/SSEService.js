/**
 * SSEService - Refactored Server-Sent Events Client
 *
 * Integrates with EventBus instead of custom event emitter.
 * Cleaner, more maintainable SSE handling.
 */

import { eventBus, EventTypes } from '../core/EventBus.js';
import { showToast } from '../ui/notifications.js';

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
                showToast('Realtime connected', 'success');

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
                // Extract worker from envelope structure: {worker_id, reason, worker: {...}}
                const workerData = data.data?.worker || data.data;
                // Ensure id field is set (use worker_id if id is missing)
                if (workerData && !workerData.id && data.data?.worker_id) {
                    workerData.id = data.data.worker_id;
                }

                // Normalize metrics from nested structures if top-level fields are missing
                // This handles the case where backend sends raw state (nested metrics) instead of DTO
                if (workerData) {
                    const getMetric = field => {
                        return workerData.cml_system_info?.[field] ?? workerData.metrics?.system_info?.[field];
                    };

                    if (workerData.cpu_utilization === undefined) {
                        workerData.cpu_utilization = getMetric('cpu_utilization');
                    }
                    if (workerData.memory_utilization === undefined) {
                        workerData.memory_utilization = getMetric('memory_utilization');
                    }
                    if (workerData.storage_utilization === undefined) {
                        workerData.storage_utilization = getMetric('storage_utilization');
                    }
                }

                eventBus.emit(EventTypes.WORKER_SNAPSHOT, workerData);
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
                showToast(`Worker created: ${data.data.name}`, 'info');
                eventBus.emit(EventTypes.WORKER_CREATED, data.data);
            });

            this.eventSource.addEventListener('worker.imported', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker imported', data);
                showToast(`Worker imported: ${data.data.name}`, 'success');
                eventBus.emit(EventTypes.WORKER_IMPORTED, data.data);
            });

            this.eventSource.addEventListener('worker.labs.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker labs updated', data);
                eventBus.emit(EventTypes.LAB_UPDATED, data.data);
            });

            // Worker terminated event
            this.eventSource.addEventListener('worker.terminated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker terminated', data);
                showToast(`Worker terminated: ${data.data.name}`, 'warning');
                eventBus.emit(EventTypes.WORKER_TERMINATED, data.data);
            });

            // Worker activity updated event
            this.eventSource.addEventListener('worker.activity.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker activity updated', data);
                eventBus.emit(EventTypes.WORKER_ACTIVITY_UPDATED, data.data);
            });

            // Worker idle detection toggled event
            this.eventSource.addEventListener('worker.idle_detection.toggled', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker idle detection toggled', data);
                eventBus.emit(EventTypes.WORKER_IDLE_DETECTION_TOGGLED, data.data);
            });

            // Worker paused event
            this.eventSource.addEventListener('worker.paused', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker paused', data);
                eventBus.emit(EventTypes.WORKER_PAUSED, data.data);
            });

            // Worker resumed event
            this.eventSource.addEventListener('worker.resumed', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker resumed', data);
                eventBus.emit(EventTypes.WORKER_RESUMED, data.data);
            });

            // Worker endpoint updated event - fired when HTTPS endpoint changes (e.g., after resume)
            this.eventSource.addEventListener('worker.endpoint.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker endpoint updated', data);
                eventBus.emit(EventTypes.WORKER_ENDPOINT_UPDATED, data.data);
            });

            // Worker EC2 details updated event - fired when EC2 instance details change
            this.eventSource.addEventListener('worker.ec2_details.updated', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker EC2 details updated', data);
                eventBus.emit(EventTypes.WORKER_EC2_DETAILS_UPDATED, data.data);
            });

            // Worker refresh throttled event
            this.eventSource.addEventListener('worker.refresh.throttled', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker refresh throttled', data);
                const retryMsg = data.data.retry_after_seconds ? ` Please wait ${data.data.retry_after_seconds}s.` : '';
                showToast(`Refresh rate limited.${retryMsg}`, 'warning');
                eventBus.emit(EventTypes.WORKER_REFRESH_THROTTLED, data.data);
            });

            // Worker data refreshed event (signals UI to reload from DB)
            this.eventSource.addEventListener('worker.data.refreshed', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Worker data refreshed', data);
                eventBus.emit(EventTypes.WORKER_DATA_REFRESHED, data.data);
            });

            // Workers refresh job completed event (auto-import job finished)
            this.eventSource.addEventListener('workers.refresh.completed', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Workers refresh completed', data);
                const eventData = data.data || data;
                if (eventData.status === 'success') {
                    if (eventData.total_imported > 0) {
                        showToast(`Workers refresh complete: ${eventData.total_imported} new worker(s) imported.`, 'success');
                    }
                } else if (eventData.error) {
                    showToast(`Workers refresh failed: ${eventData.error}`, 'error');
                }
                eventBus.emit(EventTypes.WORKERS_REFRESH_COMPLETED, eventData);
            });

            // System shutdown event - server is restarting or shutting down
            this.eventSource.addEventListener('system.sse.shutdown', event => {
                console.log('[SSE] System shutdown received', event.data);
                showToast('Server restarting, reconnecting...', 'warning');
                eventBus.emit(EventTypes.SYSTEM_SSE_SHUTDOWN, {});
                // Close connection immediately to allow server to shutdown cleanly
                this.disconnect();
                // Attempt to reconnect after a short delay
                setTimeout(() => {
                    console.log('[SSE] Attempting to reconnect after shutdown...');
                    this.connect();
                }, 2000);
            });

            // License registration started event
            this.eventSource.addEventListener('worker.license.registration.started', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] License registration started', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`License registration started for ${workerName}`, 'info');
                eventBus.emit(EventTypes.WORKER_LICENSE_REGISTRATION_STARTED, data.data);
            });

            // License registration completed event
            this.eventSource.addEventListener('worker.license.registration.completed', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] License registration completed', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`✅ License registered successfully for ${workerName}! Click to dismiss.`, 'success', 0);
                eventBus.emit(EventTypes.WORKER_LICENSE_REGISTRATION_COMPLETED, data.data);
            });

            // License registration failed event
            this.eventSource.addEventListener('worker.license.registration.failed', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] License registration failed', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                const reason = data.data.reason || 'Unknown error';
                showToast(`License registration failed for ${workerName}: ${reason}`, 'error', 8000);
                eventBus.emit(EventTypes.WORKER_LICENSE_REGISTRATION_FAILED, data.data);
            });

            // License deregistered event
            this.eventSource.addEventListener('worker.license.deregistered', event => {
                const data = JSON.parse(event.data);
                console.log('[SSE] License deregistered', data);
                const workerName = data.data.worker_name || data.data.worker_id;
                showToast(`License deregistered from ${workerName}`, 'info');
                eventBus.emit(EventTypes.WORKER_LICENSE_DEREGISTERED, data.data);
            });

            this.eventSource.addEventListener('auth.session.expired', event => {
                console.warn('[SSE] Session expired event received');
                eventBus.emit(EventTypes.AUTH_SESSION_EXPIRED, {});
                this.disconnect();
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
