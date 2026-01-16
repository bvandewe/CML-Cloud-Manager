"""Scheduler Service Settings."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Configuration settings for the Scheduler Service."""

    # etcd Configuration
    ETCD_HOST: str = os.getenv("ETCD_HOST", "localhost")
    ETCD_PORT: int = int(os.getenv("ETCD_PORT", "2379"))
    ETCD_USERNAME: str | None = os.getenv("ETCD_USERNAME")
    ETCD_PASSWORD: str | None = os.getenv("ETCD_PASSWORD")

    # Control Plane API
    CONTROL_PLANE_API_URL: str = os.getenv("CONTROL_PLANE_API_URL", "http://localhost:8080")

    # Leader Election
    LEADER_LEASE_TTL: int = int(os.getenv("LEADER_LEASE_TTL", "15"))
    LEADER_KEY: str = os.getenv("LEADER_KEY", "/ccm/scheduler/leader")

    # Scheduling
    RECONCILE_INTERVAL: int = int(os.getenv("RECONCILE_INTERVAL", "30"))
    TIMESLOT_LEAD_TIME_MINUTES: int = int(os.getenv("TIMESLOT_LEAD_TIME_MINUTES", "35"))

    # Health Check
    HEALTH_PORT: int = int(os.getenv("HEALTH_PORT", "8081"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # OpenTelemetry
    OTEL_SERVICE_NAME: str = os.getenv("OTEL_SERVICE_NAME", "scheduler")
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
