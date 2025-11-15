"""Business metrics for Starter App."""
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# Counters
tasks_created = meter.create_counter(
    name="starter_app.tasks.created",
    description="Total tasks created",
    unit="1"
)

tasks_completed = meter.create_counter(
    name="starter_app.tasks.completed",
    description="Total tasks completed",
    unit="1"
)

tasks_failed = meter.create_counter(
    name="starter_app.tasks.failed",
    description="Total task failures",
    unit="1"
)

# Histograms
task_processing_time = meter.create_histogram(
    name="starter_app.task.processing_time",
    description="Time to process tasks",
    unit="ms"
)
