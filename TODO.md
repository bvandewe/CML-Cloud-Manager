# TODO

## Testing CML API Integration

- [ ] Verify RefreshWorkerMetricsCommand integration
- [ ] Check `cml_*` fields populated in worker state
- [ ] Confirm OTEL metrics show labs_count
- [ ] Test token expiration/refresh (wait 1+ hours)

### UI Updates

- Display source-separated metrics in worker details modal
- Show EC2, CloudWatch, CML sections independently

### OTEL Metrics Enhancement

- Add more gauges for CML-specific metrics
- Track dominfo statistics (allocated CPUs, memory)
- Export to Prometheus/Grafana

### Time-Series Storage (if needed)

- Implement MongoDB time-series collection
- Store historical metric samples
- Create history API endpoints
