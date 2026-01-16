"""Resource Controller Service - Core reconciliation logic with leader election."""

import asyncio
import logging
from datetime import datetime, timezone

from application.settings import Settings

logger = logging.getLogger(__name__)


class ControllerService:
    """
    Resource Controller Service with leader election.

    Handles:
    - Reconciliation loop for workers and instances
    - Auto-scaling decisions (scale-up/scale-down)
    - Cloud provider operations via SPI
    - Worker lifecycle management (including DRAINING)
    """

    def __init__(
        self,
        etcd_client,
        api_client,
        cloud_provider,
        instance_id: str,
        settings: Settings,
    ):
        self.etcd = etcd_client
        self.api = api_client
        self.cloud_provider = cloud_provider
        self.instance_id = instance_id
        self.settings = settings
        self.is_leader = False
        self._running = False
        self._lease = None
        self._tasks: list[asyncio.Task] = []

    async def start_async(self):
        """Start the controller service."""
        self._running = True

        # Attempt to become leader
        self.is_leader = await self._campaign_for_leadership()

        if self.is_leader:
            logger.info(f"Instance {self.instance_id} elected as leader")
            self._tasks.append(asyncio.create_task(self._maintain_leadership()))
            self._tasks.append(asyncio.create_task(self._run_reconciliation_loop()))
        else:
            logger.info(f"Instance {self.instance_id} is standby, watching for leader")
            self._tasks.append(asyncio.create_task(self._watch_leader()))

    async def stop_async(self):
        """Stop the controller service."""
        self._running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self.is_leader and self._lease:
            try:
                await self.etcd.revoke_lease(self._lease)
            except Exception as e:
                logger.warning(f"Error revoking lease: {e}")

        logger.info("Controller service stopped")

    async def _campaign_for_leadership(self) -> bool:
        """Try to become leader via etcd lease."""
        try:
            self._lease = await self.etcd.grant_lease(ttl=self.settings.LEADER_LEASE_TTL)
            success = await self.etcd.put_if_not_exists(
                key=self.settings.LEADER_KEY,
                value=self.instance_id,
                lease=self._lease,
            )
            if success:
                return True
            else:
                await self.etcd.revoke_lease(self._lease)
                self._lease = None
                return False
        except Exception as e:
            logger.error(f"Error campaigning for leadership: {e}")
            return False

    async def _maintain_leadership(self):
        """Keep the leader lease alive."""
        while self._running and self.is_leader:
            try:
                if self._lease:
                    await self.etcd.refresh_lease(self._lease)
                await asyncio.sleep(self.settings.LEADER_LEASE_TTL / 3)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error maintaining leadership: {e}")
                self.is_leader = False
                break

    async def _watch_leader(self):
        """Watch leader key, campaign when leader fails."""
        while self._running:
            try:
                async for event in self.etcd.watch(self.settings.LEADER_KEY):
                    if event.type == "DELETE":
                        logger.info("Leader lost, attempting to take over")
                        self.is_leader = await self._campaign_for_leadership()
                        if self.is_leader:
                            logger.info(f"Instance {self.instance_id} became leader")
                            self._tasks.append(asyncio.create_task(self._maintain_leadership()))
                            self._tasks.append(asyncio.create_task(self._run_reconciliation_loop()))
                            return
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching leader: {e}")
                await asyncio.sleep(5)

    async def _run_reconciliation_loop(self):
        """Main reconciliation loop."""
        logger.info("Starting reconciliation loop")

        while self._running and self.is_leader:
            try:
                await self._reconcile()
                await asyncio.sleep(self.settings.RECONCILE_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}")
                await asyncio.sleep(5)

        logger.info("Reconciliation loop stopped")

    async def _reconcile(self):
        """Perform one reconciliation cycle."""
        logger.debug("Starting reconciliation cycle")
        start_time = datetime.now(timezone.utc)

        # Reconcile in order
        await self._reconcile_instances()
        await self._reconcile_workers()
        await self._check_scale_up_needed()
        await self._check_scale_down_candidates()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.debug(f"Reconciliation cycle completed in {elapsed:.2f}s")

    async def _reconcile_instances(self):
        """Reconcile instance states."""
        # TODO: Implement instance reconciliation
        # - Check SCHEDULED instances approaching timeslot
        # - Verify RUNNING instances are actually running on workers
        # - Handle stuck instances
        pass

    async def _reconcile_workers(self):
        """Reconcile worker states."""
        # TODO: Implement worker reconciliation
        # - Sync worker state from CML API
        # - Update capacity tracking
        # - Handle crashed/unreachable workers
        pass

    async def _check_scale_up_needed(self):
        """Check if new workers need to be provisioned."""
        # TODO: Implement scale-up logic
        # - Get approaching instances without assigned workers
        # - Select appropriate WorkerTemplate
        # - Provision via cloud provider
        pass

    async def _check_scale_down_candidates(self):
        """Check for idle workers that can be scaled down."""
        # TODO: Implement scale-down logic
        # - Find idle workers (no running/scheduled instances)
        # - Check for upcoming work in grace period
        # - Transition to DRAINING
        # - Stop DRAINING workers when empty
        pass

    async def _provision_worker(self, template_name: str, reason: str):
        """Provision a new worker via cloud provider."""
        logger.info(f"Provisioning new worker (template={template_name}, reason={reason})")

        try:
            # Create EC2 instance
            instance_id = await self.cloud_provider.create_instance(
                template_name=template_name,
            )

            # Notify Control Plane API
            await self.api.register_worker(
                instance_id=instance_id,
                template_name=template_name,
            )

            logger.info(f"Worker provisioned: {instance_id}")
            return instance_id

        except Exception as e:
            logger.error(f"Failed to provision worker: {e}")
            raise

    async def _terminate_worker(self, worker_id: str, ec2_instance_id: str, reason: str):
        """Terminate a worker via cloud provider."""
        logger.info(f"Terminating worker {worker_id} (reason={reason})")

        try:
            # Terminate EC2 instance
            await self.cloud_provider.terminate_instance(ec2_instance_id)

            # Notify Control Plane API
            await self.api.update_worker_status(
                worker_id=worker_id,
                status="TERMINATED",
            )

            logger.info(f"Worker terminated: {worker_id}")

        except Exception as e:
            logger.error(f"Failed to terminate worker: {e}")
            raise
