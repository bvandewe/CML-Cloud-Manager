"""Worker notification handler for reactive metrics event processing.

This service acts as an observer that receives metrics events emitted by
WorkerMetricsCollectionJob instances. It processes these events by:
- Logging metrics data
- Detecting threshold violations
- Forwarding events to external systems (future: webhooks, alerting)

This is a reactive observer pattern - it receives events rather than sending them.
"""

import logging
from typing import Any, Dict

from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class WorkerNotificationHandler:
    """Reactive observer for worker metrics events.

    This handler subscribes to metrics events from WorkerMetricsCollectionJob instances.
    It processes incoming metrics data by:
    - Logging metrics information
    - Checking for threshold violations (CPU, memory)
    - Detecting status changes
    - (Future) Forwarding to external notification systems

    This follows the observer pattern where the handler reacts to events
    rather than actively sending notifications.

    Attributes:
        _cpu_threshold: CPU utilization threshold for warnings (percentage)
        _memory_threshold: Memory utilization threshold for warnings (percentage)
    """

    def __init__(
        self,
        cpu_threshold: float = 90.0,
        memory_threshold: float = 90.0,
    ) -> None:
        """Initialize the reactive notification handler.

        Args:
            cpu_threshold: CPU utilization threshold for warnings (default: 90%)
            memory_threshold: Memory utilization threshold for warnings (default: 90%)
        """
        self._cpu_threshold = cpu_threshold
        self._memory_threshold = memory_threshold

        logger.info(
            f"🔔 WorkerNotificationHandler initialized (CPU threshold: {cpu_threshold}%, "
            f"Memory threshold: {memory_threshold}%)"
        )

    def __call__(self, metrics_data: Dict[str, Any]) -> None:
        """Handle incoming metrics event (observer callback).

        This method is invoked by WorkerMetricsCollectionJob when metrics are collected.
        It's a synchronous callback that processes the metrics event.

        Args:
            metrics_data: Metrics event payload containing:
                - worker_id: UUID of the worker
                - worker_name: Display name of the worker
                - timestamp: ISO format timestamp
                - status: Current worker status
                - instance_id: AWS EC2 instance ID
                - region: AWS region
                - metrics: Optional dict with cpu_utilization, memory_utilization, etc.
                - status_checks: EC2 status check results
        """
        worker_id = metrics_data.get("worker_id", "")
        worker_name = metrics_data.get("worker_name", "unknown")
        status = metrics_data.get("status", "")

        with tracer.start_as_current_span(
            "handle_worker_metrics",
            attributes={
                "worker_id": worker_id or "unknown",
                "status": status or "unknown",
            },
        ):
            try:
                # Log basic metrics info
                logger.debug(
                    f"📊 Received metrics for worker {worker_name} ({worker_id}): "
                    f"status={status}"
                )

                # Check for metrics data
                metrics = metrics_data.get("metrics")
                if not metrics:
                    logger.debug(
                        f"No CloudWatch metrics available for worker {worker_id}"
                    )
                    return

                # Extract utilization values
                cpu_util = self._parse_utilization(metrics.get("cpu_utilization"))
                memory_util = self._parse_utilization(metrics.get("memory_utilization"))

                # Check CPU threshold
                if cpu_util is not None and cpu_util > self._cpu_threshold:
                    logger.warning(
                        f"⚠️ HIGH CPU: Worker {worker_name} ({worker_id}) - {cpu_util:.1f}% "
                        f"(threshold: {self._cpu_threshold}%)"
                    )
                    self._handle_threshold_violation(
                        worker_id=worker_id,
                        worker_name=worker_name,
                        metric_type="cpu",
                        value=cpu_util,
                        threshold=self._cpu_threshold,
                    )

                # Check memory threshold
                if memory_util is not None and memory_util > self._memory_threshold:
                    logger.warning(
                        f"⚠️ HIGH MEMORY: Worker {worker_name} ({worker_id}) - {memory_util:.1f}% "
                        f"(threshold: {self._memory_threshold}%)"
                    )
                    self._handle_threshold_violation(
                        worker_id=worker_id,
                        worker_name=worker_name,
                        metric_type="memory",
                        value=memory_util,
                        threshold=self._memory_threshold,
                    )

                # Log normal metrics
                if cpu_util is not None or memory_util is not None:
                    cpu_str = f"CPU={cpu_util:.1f}%" if cpu_util else ""
                    mem_str = f"Memory={memory_util:.1f}%" if memory_util else ""
                    separator = " " if cpu_str and mem_str else ""
                    logger.info(
                        f"📈 Metrics for {worker_name} ({worker_id}): {cpu_str}{separator}{mem_str}"
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error processing metrics for worker {worker_id}: {e}",
                    exc_info=True,
                )

    def _parse_utilization(self, value: Any) -> float | None:
        """Parse utilization value from metrics.

        Args:
            value: Utilization value (could be string, float, or None)

        Returns:
            Parsed float value or None if invalid
        """
        if value is None:
            return None

        # Handle string values
        if isinstance(value, str):
            if value == "unknown - enable CloudWatch..." or not value:
                return None
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # Handle numeric values
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _handle_threshold_violation(
        self,
        worker_id: str,
        worker_name: str,
        metric_type: str,
        value: float,
        threshold: float,
    ) -> None:
        """Handle a threshold violation event.

        This is where you would integrate with external notification systems:
        - Send webhook notifications
        - Trigger PagerDuty/Opsgenie alerts
        - Post to Slack/Teams channels
        - Create incident tickets

        Args:
            worker_id: Worker UUID
            worker_name: Worker display name
            metric_type: Type of metric ('cpu' or 'memory')
            value: Current metric value
            threshold: Configured threshold
        """
        # For now, just log the violation
        # In the future, this could send to webhooks, alerting systems, etc.
        logger.warning(
            f"🚨 Threshold Violation: {worker_name} ({worker_id}) - "
            f"{metric_type.upper()} at {value:.1f}% exceeds {threshold}%"
        )

        # TODO: Future integrations
        # - await self._send_webhook_notification(...)
        # - await self._trigger_pagerduty_alert(...)
        # - await self._post_to_slack(...)
