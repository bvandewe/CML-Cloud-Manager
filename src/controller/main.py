"""Resource Controller Service - Main Entry Point.

This service handles reconciliation, auto-scaling, and cloud provider operations.
Uses leader election for high availability.
"""

import asyncio
import logging
import os
import signal
import uuid

from application.services.controller_service import ControllerService
from application.settings import Settings
from integration.providers.aws_ec2_provider import AwsEc2Provider
from integration.services.control_plane_client import ControlPlaneApiClient
from integration.services.etcd_client import EtcdStateStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ControllerApplication:
    """Main controller application."""

    def __init__(self):
        self.settings = Settings()
        self.instance_id = os.getenv("CONTROLLER_INSTANCE_ID", str(uuid.uuid4())[:8])
        self.shutdown_event = asyncio.Event()
        self.controller_service: ControllerService | None = None

    async def start_async(self):
        """Start the controller application."""
        logger.info(f"Starting Resource Controller Service (instance: {self.instance_id})")

        # Initialize clients
        etcd_client = EtcdStateStore(
            host=self.settings.ETCD_HOST,
            port=self.settings.ETCD_PORT,
        )
        api_client = ControlPlaneApiClient(
            base_url=self.settings.CONTROL_PLANE_API_URL,
        )

        # Initialize cloud provider
        cloud_provider = AwsEc2Provider(
            region=self.settings.AWS_REGION,
            access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
        )

        # Initialize controller service
        self.controller_service = ControllerService(
            etcd_client=etcd_client,
            api_client=api_client,
            cloud_provider=cloud_provider,
            instance_id=self.instance_id,
            settings=self.settings,
        )

        # Start the controller
        await self.controller_service.start_async()

        logger.info("Resource Controller Service started successfully")

        # Wait for shutdown signal
        await self.shutdown_event.wait()

    async def stop_async(self):
        """Stop the controller application."""
        logger.info("Stopping Resource Controller Service...")

        if self.controller_service:
            await self.controller_service.stop_async()

        self.shutdown_event.set()
        logger.info("Resource Controller Service stopped")


def main():
    """Main entry point."""
    app = ControllerApplication()

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
