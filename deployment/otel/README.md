# OpenTelemetry Observability Stack

This directory contains the configuration for the OpenTelemetry (OTEL) observability stack.

## Components

- **OTEL Collector**: Receives metrics, logs, and traces from the application and infrastructure.
- **Prometheus**: Time-series database for storing metrics.
- **Loki**: Log aggregation system.
- **Tempo**: Distributed tracing backend.

## Configuration

### OTEL Collector (`otel-collector-config.yaml`)

Configured with the following receivers:

- **OTLP**: Receives telemetry from the application.
- **Host Metrics**: Collects CPU, memory, disk, and network stats from the host.
- **Docker Stats**: Collects container resource usage.
- **Redis**: Collects Redis performance metrics.
- **MongoDB**: Collects MongoDB performance metrics.

### Loki (`loki-config.yaml`)

Configured for local storage of logs with a 7-day retention period.

## Data Flow

1. **Application** -> **OTEL Collector** (OTLP)
2. **Infrastructure** -> **OTEL Collector** (Receivers)
3. **OTEL Collector** -> **Prometheus** (Metrics)
4. **OTEL Collector** -> **Loki** (Logs)
5. **OTEL Collector** -> **Tempo** (Traces)
6. **Grafana** queries Prometheus, Loki, and Tempo for visualization.
