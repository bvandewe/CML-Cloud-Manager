"""Scheduler Service - Core scheduling logic with leader election."""

import asyncio
import logging
from datetime import datetime, timezone

from application.settings import Settings

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Scheduler Service with leader election.

    Only the elected leader runs the scheduling loop. Standbys watch
    for leader failure and campaign to take over.
    """

    def __init__(
        self,
        etcd_client,
        api_client,
        instance_id: str,
        settings: Settings,
    ):
        self.etcd = etcd_client
        self.api = api_client
        self.instance_id = instance_id
        self.settings = settings
        self.is_leader = False
        self._running = False
        self._lease = None
        self._tasks: list[asyncio.Task] = []

    async def start_async(self):
        """Start the scheduler service."""
        self._running = True

        # Attempt to become leader
        self.is_leader = await self._campaign_for_leadership()

        if self.is_leader:
            logger.info(f"Instance {self.instance_id} elected as leader")
            # Start leadership maintenance and scheduling loop
            self._tasks.append(asyncio.create_task(self._maintain_leadership()))
            self._tasks.append(asyncio.create_task(self._run_scheduling_loop()))
        else:
            logger.info(f"Instance {self.instance_id} is standby, watching for leader")
            # Watch for leader changes
            self._tasks.append(asyncio.create_task(self._watch_leader()))

    async def stop_async(self):
        """Stop the scheduler service."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Release leadership if held
        if self.is_leader and self._lease:
            try:
                await self.etcd.revoke_lease(self._lease)
            except Exception as e:
                logger.warning(f"Error revoking lease: {e}")

        logger.info("Scheduler service stopped")

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
                            self._tasks.append(asyncio.create_task(self._run_scheduling_loop()))
                            return  # Exit watch loop, now running as leader
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching leader: {e}")
                await asyncio.sleep(5)

    async def _run_scheduling_loop(self):
        """Main scheduling reconciliation loop."""
        logger.info("Starting scheduling loop")

        while self._running and self.is_leader:
            try:
                await self._reconcile()
                await asyncio.sleep(self.settings.RECONCILE_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduling loop: {e}")
                await asyncio.sleep(5)

        logger.info("Scheduling loop stopped")

    async def _reconcile(self):
        """Perform one reconciliation cycle."""
        logger.debug("Starting reconciliation cycle")
        start_time = datetime.now(timezone.utc)

        # TODO: Implement scheduling logic
        # 1. Get PENDING instances from etcd
        # 2. For each PENDING instance:
        #    a. Run placement algorithm
        #    b. If worker found: call API to schedule
        #    c. If no worker: signal controller for scale-up
        # 3. Check approaching timeslots
        # 4. Trigger instantiation for scheduled instances

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.debug(f"Reconciliation cycle completed in {elapsed:.2f}s")
