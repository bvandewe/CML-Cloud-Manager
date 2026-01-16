"""Value Object for CML Metrics."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CpuStats:
    """Value Object for CPU statistics."""

    load: list[float] = field(default_factory=list)
    count: int | None = None
    percent: float | None = None
    model: str | None = None
    predicted: int | None = None


@dataclass(frozen=True)
class MemoryStats:
    """Value Object for Memory statistics."""

    total: int | None = None
    free: int | None = None
    used: int | None = None


@dataclass(frozen=True)
class DiskStats:
    """Value Object for Disk statistics."""

    total: int | None = None
    free: int | None = None
    used: int | None = None


@dataclass(frozen=True)
class DomInfoStats:
    """Value Object for Domain Info statistics."""

    allocated_cpus: int | None = None
    allocated_memory: int | None = None
    total_nodes: int | None = None
    total_orphans: int | None = None
    running_nodes: int | None = None
    running_orphans: int | None = None


@dataclass(frozen=True)
class CMLSystemInfoComputeStats:
    """Value Object for CML system information Compute stats."""

    cpu: CpuStats | None = None
    memory: MemoryStats | None = None
    disk: DiskStats | None = None
    dominfo: DomInfoStats | None = None


@dataclass(frozen=True)
class CMLSystemInfoCompute:
    """Value Object for CML system information Compute."""

    hostname: str | None = None
    is_controller: bool | None = None
    stats: CMLSystemInfoComputeStats | None = None


@dataclass(frozen=True)
class CMLSystemInfo:
    """Value Object for CML system information."""

    cpu_count: int | None = None
    cpu_utilization: float | None = None  # from all_cpu_percent
    memory_total: int | None = None  # from all_memory_total
    memory_free: int | None = None  # from all_memory_free
    memory_used: int | None = None  # from all_memory_used
    disk_total: int | None = None  # from all_disk_total
    disk_free: int | None = None  # from all_disk_free
    disk_used: int | None = None  # from all_disk_used
    controller_disk_total: int | None = None
    controller_disk_free: int | None = None
    controller_disk_used: int | None = None
    allocated_cpus: int | None = None
    allocated_memory: int | None = None
    total_nodes: int | None = None
    running_nodes: int | None = None
    computes: dict[str, CMLSystemInfoCompute] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class CMLSystemHealth:
    """Value Object for CML system health."""

    valid: bool = False
    is_licensed: bool = False
    is_enterprise: bool = False
    computes: dict[str, Any] = field(default_factory=dict)
    controller: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class CMLMetrics:
    """Value Object representing CML system metrics."""

    version: str | None = None
    ready: bool = False
    uptime_seconds: int | None = None
    labs_count: int = 0

    system_info: CMLSystemInfo | None = None
    system_health: CMLSystemHealth | None = None

    last_synced_at: datetime | None = None

    def get_utilization(self) -> tuple[float | None, float | None, float | None]:
        """Calculate CPU, memory, and storage utilization.

        Returns:
            Tuple of (cpu_util, mem_util, storage_util) percentages or None.
        """
        # 1. Try direct fields from system_info first
        if self.system_info:
            cpu_util = self.system_info.cpu_utilization
            mem_util = None
            storage_util = None

            if self.system_info.memory_total and self.system_info.memory_used and self.system_info.memory_total > 0:
                mem_util = (self.system_info.memory_used / self.system_info.memory_total) * 100

            if self.system_info.disk_total and self.system_info.disk_used and self.system_info.disk_total > 0:
                storage_util = (self.system_info.disk_used / self.system_info.disk_total) * 100

            if cpu_util is not None or mem_util is not None or storage_util is not None:
                return cpu_util, mem_util, storage_util

        # 2. Fallback to parsing nested stats in system_info.computes
        if not self.system_info:
            return None, None, None

        stats = None
        computes = self.system_info.computes

        if computes:
            # Try to extract from 'computes' collection
            # Handle both dict-like objects (values()) and lists
            if hasattr(computes, "values"):
                try:
                    first_compute = next(iter(computes.values()))
                    stats = first_compute.stats
                except StopIteration:
                    pass

        if not stats:
            return None, None, None

        cpu_util = None
        mem_util = None
        storage_util = None

        if stats.cpu and stats.cpu.percent is not None:
            cpu_util = stats.cpu.percent

        if stats.memory and stats.memory.total and stats.memory.used:
            if stats.memory.total > 0:
                mem_util = (stats.memory.used / stats.memory.total) * 100

        if stats.disk and stats.disk.total and stats.disk.used:
            if stats.disk.total > 0:
                storage_util = (stats.disk.used / stats.disk.total) * 100

        return cpu_util, mem_util, storage_util

    @staticmethod
    def calculate_utilization_from_stats(stats: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
        """Calculate utilization metrics from a stats dictionary."""
        cpu_util = None
        mem_util = None
        storage_util = None

        # CPU
        cpu_stats = stats.get("cpu", {})
        if "percent" in cpu_stats:
            cpu_util = float(cpu_stats["percent"])
        elif "user_percent" in cpu_stats and "system_percent" in cpu_stats:
            try:
                cpu_util = float(cpu_stats["user_percent"]) + float(cpu_stats["system_percent"])
            except (ValueError, TypeError):
                pass

        # Memory
        mem_stats = stats.get("memory", {})
        if "total" in mem_stats and "used" in mem_stats:
            try:
                total = float(mem_stats["total"])
                used = float(mem_stats["used"])
                if total > 0:
                    mem_util = (used / total) * 100
            except (ValueError, TypeError):
                pass
        elif "total" in mem_stats and "free" in mem_stats:
            try:
                total = float(mem_stats["total"])
                free = float(mem_stats["free"])
                if total > 0:
                    mem_util = ((total - free) / total) * 100
            except (ValueError, TypeError):
                pass
        elif "total_kb" in mem_stats and "available_kb" in mem_stats:
            try:
                total = float(mem_stats["total_kb"])
                avail = float(mem_stats["available_kb"])
                if total > 0:
                    mem_util = ((total - avail) / total) * 100
            except (ValueError, TypeError):
                pass

        # Storage
        disk_stats = stats.get("disk", {})
        if "total" in disk_stats and "used" in disk_stats:
            try:
                total = float(disk_stats["total"])
                used = float(disk_stats["used"])
                if total > 0:
                    storage_util = (used / total) * 100
            except (ValueError, TypeError):
                pass
        elif "capacity_kb" in disk_stats and "size_kb" in disk_stats:
            try:
                capacity = float(disk_stats["capacity_kb"])
                size = float(disk_stats["size_kb"])
                if capacity > 0:
                    storage_util = (size / capacity) * 100
            except (ValueError, TypeError):
                pass

        return cpu_util, mem_util, storage_util
