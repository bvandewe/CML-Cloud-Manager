# TODO

## Testing CML API Integration

- [ ] Verify RefreshWorkerMetricsCommand integration
- [ ] Check `cml_*` fields populated in worker state
- [ ] Confirm OTEL metrics show labs_count
- [ ] Test token expiration/refresh (wait 1+ hours)

---

## Future Enhancements

### Real-Time UI Updates via Server-Sent Events (SSE)

**Priority:** High (defer until after Labs tab and metrics are complete)

**Rationale:**

- Worker metrics are updated by scheduled jobs (every 5 minutes)
- Users need real-time updates without manual refresh
- CloudEventBus infrastructure already in place

**Implementation Plan:**

1. **Backend SSE Endpoint** (`/api/workers/events`)
   - Subscribe to CloudEventBus for worker-related events
   - Stream events as Server-Sent Events
   - Filter events per user's access level (admin vs regular user)
   - Handle authentication via session cookies
   - Implement reconnection logic and heartbeat

2. **Events to Stream:**
   - `CMLMetricsUpdatedDomainEvent` - Worker metrics refreshed
   - `WorkerStatusChangedDomainEvent` - Worker status changed
   - `WorkerCreatedDomainEvent` - New worker created
   - `WorkerTerminatedDomainEvent` - Worker terminated
   - `LabsUpdatedDomainEvent` - Labs data refreshed (future)

3. **Frontend EventSource Client:**
   - Subscribe to SSE endpoint on dashboard load
   - Auto-update worker cards/table on events
   - Auto-refresh open worker details modal
   - Show toast notifications for important events
   - Handle reconnection on connection loss

4. **Benefits:**
   - Automatic UI updates when scheduled jobs complete
   - Real-time status changes without polling
   - Better user experience with live data
   - Reduced server load (vs polling every N seconds)

**Dependencies:**

- Complete Labs tab implementation
- Finalize all worker metrics collection
- Standardize event payload structure

### UI Updates

- Display source-separated metrics in worker details modal
- Show EC2, CloudWatch, CML sections independently
- Add "Enable Detailed Monitoring" button for admins

### OTEL Metrics Enhancement

- Add more gauges for CML-specific metrics
- Track dominfo statistics (allocated CPUs, memory)
- Export to Prometheus/Grafana

### Time-Series Storage (if needed)

- Implement MongoDB time-series collection
- Store historical metric samples
- Create history API endpoints
