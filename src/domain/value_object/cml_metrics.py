"""Value Object for CML Metrics."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CMLMetrics:
    """Value Object representing CML system metrics."""

    version: str | None = None
    ready: bool = False
    uptime_seconds: int | None = None
    labs_count: int = 0
    system_info: dict[str, Any] | None = None
    system_health: dict[str, Any] | None = None
    last_synced_at: datetime | None = None

    def get_utilization(self) -> tuple[float | None, float | None, float | None]:
        """Calculate CPU, memory, and storage utilization from system_info.

        Returns:
            Tuple of (cpu_util, mem_util, storage_util) percentages or None.
        """
        if not self.system_info or not isinstance(self.system_info, dict):
            return None, None, None

        # Extract stats from the first value in system_info (CML API structure)
        first_value = next(iter(self.system_info.values()), {})
        if not isinstance(first_value, dict):
            return None, None, None

        stats = first_value.get("stats", {})
        return self.calculate_utilization_from_stats(stats)

    @staticmethod
    def calculate_utilization_from_stats(stats: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
        """Calculate utilization metrics from a stats dictionary."""
        if not isinstance(stats, dict):
            return None, None, None

        cpu_util = None
        mem_util = None
        storage_util = None

        cpu_stats = stats.get("cpu", {})
        mem_stats = stats.get("memory", {})
        disk_stats = stats.get("disk", {})

        # CPU Calculation
        if cpu_stats:
            up = cpu_stats.get("user_percent")
            sp = cpu_stats.get("system_percent")
            if up is not None and sp is not None:
                try:
                    cpu_util = float(up) + float(sp)
                except (TypeError, ValueError):
                    cpu_util = None

        # Memory Calculation
        if mem_stats:
            total_kb = mem_stats.get("total_kb") or mem_stats.get("total")
            available_kb = mem_stats.get("available_kb") or mem_stats.get("free")

            has_valid_values = isinstance(total_kb, (int, float)) and isinstance(available_kb, (int, float))
            if has_valid_values and total_kb > 0:
                used_kb = total_kb - available_kb
                mem_util = (used_kb / total_kb) * 100

        # Storage Calculation
        if disk_stats:
            size_kb = disk_stats.get("size_kb") or disk_stats.get("used")
            capacity_kb = disk_stats.get("capacity_kb") or disk_stats.get("total")

            has_valid_values = isinstance(size_kb, (int, float)) and isinstance(capacity_kb, (int, float))
            if has_valid_values and capacity_kb > 0:
                storage_util = (size_kb / capacity_kb) * 100

        return cpu_util, mem_util, storage_util
