"""Business metrics for Cml Cloud Manager."""
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# Counters
tasks_created = meter.create_counter(
    name="cml_cloud_manager.tasks.created",
    description="Total tasks created",
    unit="1"
)

tasks_completed = meter.create_counter(
    name="cml_cloud_manager.tasks.completed",
    description="Total tasks completed",
    unit="1"
)

tasks_failed = meter.create_counter(
    name="cml_cloud_manager.tasks.failed",
    description="Total task failures",
    unit="1"
)

# Histograms
task_processing_time = meter.create_histogram(
    name="cml_cloud_manager.task.processing_time",
    description="Time to process tasks",
    unit="ms"
)
