"""Domain event handlers for CML Worker events that broadcast SSE updates.

These handlers translate domain events into lightweight SSE messages consumed by
frontend components for real-time UI updates.
"""

from __future__ import annotations

import logging
from datetime import datetime

from neuroglia.mediation import DomainEventHandler

from application.services.sse_event_relay import SSEEventRelay
from domain.events.cml_worker import (
    CMLWorkerCreatedDomainEvent,
    CMLWorkerImportedDomainEvent,
    CMLWorkerStatusUpdatedDomainEvent,
    CMLWorkerTelemetryUpdatedDomainEvent,
    CMLWorkerTerminatedDomainEvent,
)
from domain.events.worker_metrics_events import CMLMetricsUpdatedDomainEvent
from domain.repositories.cml_worker_repository import CMLWorkerRepository

log = logging.getLogger(__name__)


def _utc_iso(dt: datetime) -> str:
    return dt.isoformat() + "Z"


class CMLWorkerCreatedDomainEventHandler(DomainEventHandler[CMLWorkerCreatedDomainEvent]):
    def __init__(self, sse_relay: SSEEventRelay, repository: CMLWorkerRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: CMLWorkerCreatedDomainEvent) -> None:  # type: ignore[override]
        # Original specific event
        await self._sse_relay.broadcast_event(
            event_type="worker.created",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "region": notification.aws_region,
                "status": notification.status.value,
                "instance_type": notification.instance_type,
                "created_at": _utc_iso(notification.created_at),
            },
            source="domain.cml_worker",
        )
        # Snapshot event
        await _broadcast_worker_snapshot(
            self._repository,
            self._sse_relay,
            notification.aggregate_id,
            reason="created",
        )
        log.info("Broadcasted worker.created + snapshot for %s", notification.aggregate_id)
        return None


class CMLWorkerImportedDomainEventHandler(DomainEventHandler[CMLWorkerImportedDomainEvent]):
    """Handle worker imported event by notifying UI and scheduling initial data refresh."""

    def __init__(
        self,
        sse_relay: SSEEventRelay,
        repository: CMLWorkerRepository,
        scheduler,
    ):
        from application.services.background_scheduler import BackgroundTaskScheduler

        self._sse_relay = sse_relay
        self._repository = repository
        self._scheduler: BackgroundTaskScheduler = scheduler

    async def handle_async(self, notification: CMLWorkerImportedDomainEvent) -> None:  # type: ignore[override]
        """Broadcast worker.imported SSE event and schedule immediate data collection."""
        from datetime import timedelta, timezone

        from application.jobs.on_demand_worker_data_refresh_job import OnDemandWorkerDataRefreshJob

        # Map EC2 instance_state to CMLWorkerStatus for consistency
        status_str = notification.instance_state
        if notification.instance_state == "running":
            status_str = "running"
        elif notification.instance_state == "stopped":
            status_str = "stopped"
        elif notification.instance_state == "stopping":
            status_str = "stopping"
        elif notification.instance_state == "pending":
            status_str = "pending"
        else:
            status_str = "unknown"

        # Broadcast imported event to UI
        await self._sse_relay.broadcast_event(
            event_type="worker.imported",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "region": notification.aws_region,
                "status": status_str,
                "instance_type": notification.instance_type,
                "aws_instance_id": notification.aws_instance_id,
                "imported_at": _utc_iso(notification.created_at),
            },
            source="domain.cml_worker",
        )

        # Broadcast snapshot for full worker data
        await _broadcast_worker_snapshot(
            self._repository,
            self._sse_relay,
            notification.aggregate_id,
            reason="imported",
        )

        log.info(
            f"Broadcasted worker.imported + snapshot for {notification.aggregate_id}, "
            f"scheduling initial data collection"
        )

        # Schedule immediate data refresh job, bypassing command validation checks
        # Newly imported workers need their data collected regardless of status/throttling
        try:
            job_id = f"import_refresh_{notification.aggregate_id}"
            job = OnDemandWorkerDataRefreshJob(worker_id=notification.aggregate_id)
            job.__task_id__ = job_id
            job.__task_name__ = "OnDemandWorkerDataRefreshJob"
            job.__background_task_type__ = "scheduled"
            # Schedule 2 seconds in the future to ensure import transaction completes
            job.__scheduled_at__ = datetime.now(timezone.utc) + timedelta(seconds=2)

            await self._scheduler.enqueue_task_async(job)

            log.info(
                f"✅ Scheduled initial data collection for imported worker {notification.aggregate_id} "
                f"(job_id: {job_id}, eta: 2s)"
            )
        except Exception as e:
            log.error(
                f"❌ Error scheduling data collection for imported worker {notification.aggregate_id}: {e}",
                exc_info=True,
            )

        return None


class CMLWorkerStatusUpdatedDomainEventHandler(DomainEventHandler[CMLWorkerStatusUpdatedDomainEvent]):
    def __init__(self, sse_relay: SSEEventRelay, repository: CMLWorkerRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: CMLWorkerStatusUpdatedDomainEvent) -> None:  # type: ignore[override]
        # Include transition initiation timestamp if present so UI can start elapsed timer immediately
        event_data = {
            "worker_id": notification.aggregate_id,
            "old_status": notification.old_status.value,
            "new_status": notification.new_status.value,
            "updated_at": _utc_iso(notification.updated_at),
        }
        if getattr(notification, "transition_initiated_at", None):
            event_data["transition_initiated_at"] = _utc_iso(notification.transition_initiated_at)
        await self._sse_relay.broadcast_event(
            event_type="worker.status.updated",
            data=event_data,
            source="domain.cml_worker",
        )
        await _broadcast_worker_snapshot(
            self._repository,
            self._sse_relay,
            notification.aggregate_id,
            reason="status_updated",
        )
        log.info(
            "Broadcasted worker.status.updated + snapshot for %s",
            notification.aggregate_id,
        )
        return None


class CMLWorkerTerminatedDomainEventHandler(DomainEventHandler[CMLWorkerTerminatedDomainEvent]):
    def __init__(self, sse_relay: SSEEventRelay, repository: CMLWorkerRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: CMLWorkerTerminatedDomainEvent) -> None:  # type: ignore[override]
        await self._sse_relay.broadcast_event(
            event_type="worker.terminated",
            data={
                "worker_id": notification.aggregate_id,
                "name": notification.name,
                "terminated_at": _utc_iso(notification.terminated_at),
            },
            source="domain.cml_worker",
        )
        await _broadcast_worker_snapshot(
            self._repository,
            self._sse_relay,
            notification.aggregate_id,
            reason="terminated",
        )
        log.info("Broadcasted worker.terminated + snapshot for %s", notification.aggregate_id)
        return None


class CMLWorkerTelemetryUpdatedDomainEventHandler(DomainEventHandler[CMLWorkerTelemetryUpdatedDomainEvent]):
    def __init__(self, sse_relay: SSEEventRelay, repository: CMLWorkerRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: CMLWorkerTelemetryUpdatedDomainEvent) -> None:  # type: ignore[override]
        event_data = {
            "worker_id": notification.aggregate_id,
            "last_activity_at": _utc_iso(notification.last_activity_at),
            "active_labs_count": notification.active_labs_count,
            "cpu_utilization": notification.cpu_utilization,
            "memory_utilization": notification.memory_utilization,
            "updated_at": _utc_iso(notification.updated_at),
        }
        if notification.poll_interval is not None:
            event_data["poll_interval"] = notification.poll_interval
        if notification.next_refresh_at is not None:
            event_data["next_refresh_at"] = _utc_iso(notification.next_refresh_at)

        await self._sse_relay.broadcast_event(
            event_type="worker.metrics.updated",
            data=event_data,
            source="domain.cml_worker",
        )
        await _broadcast_worker_snapshot(
            self._repository,
            self._sse_relay,
            notification.aggregate_id,
            reason="telemetry_updated",
        )
        log.debug(
            "Broadcasted worker.metrics.updated + snapshot for %s",
            notification.aggregate_id,
        )
        return None


class CMLMetricsUpdatedDomainEventHandler(DomainEventHandler[CMLMetricsUpdatedDomainEvent]):
    """Broadcast SSE events when CML metrics (system stats) are updated.

    Domain already suppresses insignificant changes; this handler simply
    derives utilization from current state and broadcasts the event plus snapshot.
    """

    def __init__(self, sse_relay: SSEEventRelay, repository: CMLWorkerRepository):
        self._sse_relay = sse_relay
        self._repository = repository

    async def handle_async(self, notification: CMLMetricsUpdatedDomainEvent) -> None:  # type: ignore[override]
        worker = await self._repository.get_by_id_async(notification.aggregate_id)
        cpu_util = None
        mem_util = None
        storage_util = None
        poll_interval = None
        next_refresh_at_iso = None
        if worker:
            s = worker.state
            poll_interval = s.poll_interval
            if s.next_refresh_at:
                next_refresh_at_iso = s.next_refresh_at.isoformat() + "Z"
            if s.cml_system_info:
                first_compute = next(iter(s.cml_system_info.values()), {})
                stats = first_compute.get("stats", {})
                disk_stats = stats.get("disk", {})
                mem_stats = stats.get("memory", {})
                cpu_stats = stats.get("cpu", {})
                if cpu_stats:
                    up = cpu_stats.get("user_percent")
                    sp = cpu_stats.get("system_percent")
                    if up is not None and sp is not None:
                        try:
                            cpu_util = float(up) + float(sp)
                        except (TypeError, ValueError):
                            pass
                if mem_stats:
                    total_kb = mem_stats.get("total_kb") or mem_stats.get("total")
                    available_kb = mem_stats.get("available_kb") or mem_stats.get("free")
                    if isinstance(total_kb, (int, float)) and isinstance(available_kb, (int, float)) and total_kb > 0:
                        used_kb = total_kb - available_kb
                        mem_util = (used_kb / total_kb) * 100
                size_kb = disk_stats.get("size_kb") or disk_stats.get("used")
                capacity_kb = disk_stats.get("capacity_kb") or disk_stats.get("total")
                if isinstance(size_kb, (int, float)) and isinstance(capacity_kb, (int, float)) and capacity_kb > 0:
                    storage_util = (size_kb / capacity_kb) * 100

        payload = {
            "worker_id": notification.aggregate_id,
            "cml_version": notification.cml_version,
            "labs_count": notification.labs_count,
            "cpu_utilization": cpu_util,
            "memory_utilization": mem_util,
            "storage_utilization": storage_util,
            "updated_at": _utc_iso(notification.updated_at),
        }
        if poll_interval is not None:
            payload["poll_interval"] = poll_interval
        if next_refresh_at_iso:
            payload["next_refresh_at"] = next_refresh_at_iso

        await self._sse_relay.broadcast_event(
            event_type="worker.metrics.updated",
            data=payload,
            source="domain.cml_worker.cml_metrics",
        )
        # Note: Snapshot broadcast removed - metrics event already contains relevant data
        # Snapshots are only broadcast for significant state changes (status, license, etc.)
        log.debug(
            "Broadcasted worker.metrics.updated (CML metrics) for %s",
            notification.aggregate_id,
        )
        return None


# --- Snapshot Helper & Additional Event Handlers ---


async def _broadcast_worker_snapshot(
    repository: CMLWorkerRepository,
    relay: SSEEventRelay,
    worker_id: str,
    reason: str | None = None,
) -> None:
    try:
        worker = await repository.get_by_id_async(worker_id)
        if not worker:
            return
        s = worker.state
        # Derive utilization from CML stats if available
        cpu_util = s.cloudwatch_cpu_utilization
        mem_util = s.cloudwatch_memory_utilization
        storage_util = None
        if s.cml_system_info:
            first_compute = next(iter(s.cml_system_info.values()), {})
            stats = first_compute.get("stats", {})
            disk_stats = stats.get("disk", {})
            mem_stats = stats.get("memory", {})
            cpu_stats = stats.get("cpu", {})
            # CPU (prefer CML percent sum if present)
            if cpu_stats:
                user_percent = cpu_stats.get("user_percent")
                system_percent = cpu_stats.get("system_percent")
                if user_percent is not None and system_percent is not None:
                    cpu_util = user_percent + system_percent
            # Memory utilization from total/available
            if mem_stats:
                total_kb = mem_stats.get("total_kb") or mem_stats.get("total")
                available_kb = mem_stats.get("available_kb") or mem_stats.get("free")
                if isinstance(total_kb, (int, float)) and isinstance(available_kb, (int, float)) and total_kb > 0:
                    used_kb = total_kb - available_kb
                    mem_util = (used_kb / total_kb) * 100
            # Disk utilization
            size_kb = disk_stats.get("size_kb") or disk_stats.get("used")
            capacity_kb = disk_stats.get("capacity_kb") or disk_stats.get("total")
            if isinstance(size_kb, (int, float)) and isinstance(capacity_kb, (int, float)) and capacity_kb > 0:
                storage_util = (size_kb / capacity_kb) * 100

        snapshot = {
            "worker_id": s.id,
            "name": s.name,
            "region": s.aws_region,
            "status": s.status.value,
            "service_status": s.service_status.value,
            "instance_type": s.instance_type,
            "aws_instance_id": s.aws_instance_id,
            "public_ip": s.public_ip,
            "private_ip": s.private_ip,
            "aws_tags": s.aws_tags,
            "ami_id": s.ami_id,
            "ami_name": s.ami_name,
            "ami_description": s.ami_description,
            "ami_creation_date": s.ami_creation_date,
            "https_endpoint": s.https_endpoint,
            "license_status": s.license_status.value if s.license_status else None,
            "cml_version": s.cml_version,
            "cml_ready": s.cml_ready,
            "cml_uptime_seconds": s.cml_uptime_seconds,
            "cml_labs_count": s.cml_labs_count,
            "cml_license_info": s.cml_license_info,
            "cml_system_health": s.cml_system_health,
            "cpu_utilization": cpu_util,
            "memory_utilization": mem_util,
            "storage_utilization": storage_util,
            "poll_interval": s.poll_interval,
            "next_refresh_at": (s.next_refresh_at.isoformat() if s.next_refresh_at else None),
            "updated_at": s.updated_at.isoformat() + "Z" if s.updated_at else None,
            "terminated_at": (s.terminated_at.isoformat() + "Z" if s.terminated_at else None),
            "start_initiated_at": (s.start_initiated_at.isoformat() + "Z" if s.start_initiated_at else None),
            "stop_initiated_at": (s.stop_initiated_at.isoformat() + "Z" if s.stop_initiated_at else None),
        }
        if reason:
            snapshot["_reason"] = reason
        await relay.broadcast_event(
            event_type="worker.snapshot",
            data=snapshot,
            source="domain.cml_worker.snapshot",
        )
    except Exception as e:
        log.warning("Failed to broadcast worker snapshot for %s: %s", worker_id, e)
