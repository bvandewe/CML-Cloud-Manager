# TODO

## Zero State Admin

1. Import CML worker from AWS region by AMI name: add btn in "CML Workers" view next to "Refresh" btn.


Next Steps (Future Work):
Test the CML API Integration:

Deploy and test with a real CML worker instance
Verify /api/v0/system_stats endpoint works
Check authentication and SSL handling
UI Updates:

Display source-separated metrics in worker details modal
Show EC2, CloudWatch, CML sections independently
Add "Enable Detailed Monitoring" button for admins
OTEL Metrics Enhancement:

Add more gauges for CML-specific metrics
Track dominfo statistics (allocated CPUs, memory)
Export to Prometheus/Grafana
Time-Series Storage (if needed):

Implement MongoDB time-series collection
Store historical metric samples
Create history API endpoints
