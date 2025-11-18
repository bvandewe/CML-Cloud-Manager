"""Abstract repository for CML Workers."""

from abc import ABC, abstractmethod
from typing import Optional

from domain.entities.cml_worker import CMLWorker
from domain.enums import CMLWorkerStatus


class CMLWorkerRepository(ABC):
    """Abstract repository for CML Worker entities."""

    @abstractmethod
    async def get_all_async(self) -> list[CMLWorker]:
        """Retrieve all CML workers."""
        pass

    @abstractmethod
    async def get_by_id_async(self, worker_id: str) -> CMLWorker | None:
        """Retrieve a CML worker by ID."""
        pass

    @abstractmethod
    async def get_by_aws_instance_id_async(
        self, aws_instance_id: str
    ) -> CMLWorker | None:
        """Retrieve a CML worker by AWS EC2 instance ID."""
        pass

    @abstractmethod
    async def get_by_status_async(self, status: CMLWorkerStatus) -> list[CMLWorker]:
        """Retrieve CML workers by status."""
        pass

    @abstractmethod
    async def get_active_workers_async(self) -> list[CMLWorker]:
        """Retrieve all active (non-terminated) CML workers."""
        pass

    @abstractmethod
    async def get_idle_workers_async(
        self, idle_threshold_minutes: int
    ) -> list[CMLWorker]:
        """Retrieve workers that have been idle beyond the threshold.

        Args:
            idle_threshold_minutes: Idle threshold in minutes

        Returns:
            List of idle workers
        """
        pass

    @abstractmethod
    async def add_async(self, entity: CMLWorker) -> CMLWorker:
        """Add a new CML worker."""
        pass

    @abstractmethod
    async def update_async(self, entity: CMLWorker) -> CMLWorker:
        """Update an existing CML worker."""
        pass

    @abstractmethod
    async def update_many_async(self, entities: list[CMLWorker]) -> int:
        """Update multiple CML workers in a batch operation.

        Args:
            entities: List of CMLWorker entities to update

        Returns:
            Number of workers updated
        """
        pass

    @abstractmethod
    async def delete_async(
        self, worker_id: str, worker: Optional[CMLWorker] = None
    ) -> bool:
        """Delete a CML worker by ID.

        Args:
            worker_id: The ID of the worker to delete
            worker: Optional worker entity with pending domain events to publish

        Returns:
            True if deletion was successful, False otherwise
        """
        pass
