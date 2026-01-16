"""Background worker process - ONLY runs scheduled jobs.

This process does NOT serve HTTP requests.
Executes: WorkerMetricsCollectionJob, LabsRefreshJob, AutoImportWorkersJob
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from types import FrameType

from application.services.background_scheduler import BackgroundTaskScheduler
from application.services.sse_event_relay import SSEEventRelayHostedService

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# CRITICAL: Enable background jobs BEFORE importing main
os.environ["WORKER_MONITORING_ENABLED"] = "true"

# Initialize debugger if configured
if os.environ.get("DEBUG_WORKER") == "true":
    try:
        import debugpy

        debugpy.listen(("0.0.0.0", 5679))  # nosec
        logging.info("🐛 Debugger listening on 0.0.0.0:5679")
    except Exception as e:
        logging.error(f"Failed to start debugger: {e}")

from application.settings import app_settings, configure_logging  # noqa: E402
from main import create_app  # noqa: E402

configure_logging(log_level=app_settings.log_level)
log = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


def signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully."""
    log.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


async def run_worker() -> None:
    """Run background worker with graceful shutdown."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create app (this starts lifespan and schedules jobs)
    log.info("🚀 Starting background worker process...")
    app = create_app()

    # Get scheduler from service provider
    # from application.services.background_scheduler import BackgroundTaskScheduler
    # from application.services.sse_event_relay import SSEEventRelayHostedService

    scheduler = app.state.services.get_required_service(BackgroundTaskScheduler)
    sse_relay_service = app.state.services.get_required_service(SSEEventRelayHostedService)

    # Manually start the scheduler since we are not running via Uvicorn lifespan
    await scheduler.start_async()
    await sse_relay_service.start_async()

    log.info(f"✅ Background worker started with {scheduler.get_job_count()} jobs")
    log.info("📊 Running jobs:")
    for job in scheduler.get_jobs():
        log.info(f"   - {job.name} (next run: {job.next_run_time})")

    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    except Exception as e:
        log.error(f"Worker error: {e}", exc_info=True)
    finally:
        log.info("🛑 Shutting down background worker...")
        await scheduler.stop_async()
        log.info("✅ Background worker stopped cleanly")

        log.info("🛑 Shutting down SSE event relay service...")
        await sse_relay_service.stop_async()
        log.info("✅ SSE event relay service stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    sys.exit(0)
