"""Scheduler Service - Main Entry Point.

This service handles LabletInstance placement decisions using leader election
for high availability. Only the elected leader runs the scheduling loop.
"""

import asyncio
import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager

from application.services.scheduler_service import SchedulerService
from application.settings import Settings
from integration.services.control_plane_client import ControlPlaneApiClient
from integration.services.etcd_client import EtcdStateStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SchedulerApplication:
    """Main scheduler application."""

    def __init__(self):
        self.settings = Settings()
        self.instance_id = os.getenv("SCHEDULER_INSTANCE_ID", str(uuid.uuid4())[:8])
        self.shutdown_event = asyncio.Event()
        self.scheduler_service: SchedulerService | None = None

    async def start_async(self):
        """Start the scheduler application."""
        logger.info(f"Starting Scheduler Service (instance: {self.instance_id})")

        # Initialize clients
        etcd_client = EtcdStateStore(
            host=self.settings.ETCD_HOST,
            port=self.settings.ETCD_PORT,
        )
        api_client = ControlPlaneApiClient(
            base_url=self.settings.CONTROL_PLANE_API_URL,
        )

        # Initialize scheduler service
        self.scheduler_service = SchedulerService(
            etcd_client=etcd_client,
            api_client=api_client,
            instance_id=self.instance_id,
            settings=self.settings,
        )

        # Start the scheduler
        await self.scheduler_service.start_async()

        logger.info("Scheduler Service started successfully")

        # Wait for shutdown signal
        await self.shutdown_event.wait()

    async def stop_async(self):
        """Stop the scheduler application."""
        logger.info("Stopping Scheduler Service...")

        if self.scheduler_service:
            await self.scheduler_service.stop_async()

        self.shutdown_event.set()
        logger.info("Scheduler Service stopped")


def main():
    """Main entry point."""
    app = SchedulerApplication()

    # Set up signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler():
        logger.info("Received shutdown signal")
        loop.create_task(app.stop_async())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        loop.run_until_complete(app.start_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
