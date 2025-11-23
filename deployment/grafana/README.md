# Grafana Dashboards

Grafana provides visualization for metrics collected by the OpenTelemetry stack.

## Dashboards

Pre-configured dashboards are located in `deployment/grafana/dashboards/`:

- **App Metrics**: Application-level metrics (request latency, error rates, active tasks).
- **Docker Metrics**: Container resource usage (CPU, memory, network).
- **Host Metrics**: Host machine statistics (load, disk usage).
- **MongoDB Metrics**: Database performance and connection stats.
- **Redis Metrics**: Cache performance and memory usage.

## Data Sources

- **Prometheus**: Primary data source for metrics.
- **Loki**: Data source for logs.
- **Tempo**: Data source for distributed traces.

## Authentication

Grafana is integrated with Keycloak for Single Sign-On (SSO).

- **Admin Role**: Users with the `admin` role in Keycloak have full admin access in Grafana.
- **Viewer Role**: Other authenticated users have viewer access.

## Access

- **URL**: `http://<host>/grafana/`
