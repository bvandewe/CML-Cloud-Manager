"""Repository interface for Lab Records."""

from abc import ABC, abstractmethod

from domain.entities.lab_record import LabRecord


class LabRecordRepository(ABC):
    """Repository for managing Lab Record persistence."""

    @abstractmethod
    async def get_by_id_async(self, record_id: str) -> LabRecord | None:
        """Get a lab record by its ID."""

    @abstractmethod
    async def get_by_lab_id_async(
        self, worker_id: str, lab_id: str
    ) -> LabRecord | None:
        """Get a lab record by worker ID and CML lab ID."""

    @abstractmethod
    async def get_all_by_worker_async(self, worker_id: str) -> list[LabRecord]:
        """Get all lab records for a specific worker."""

    @abstractmethod
    async def get_all_async(self) -> list[LabRecord]:
        """Get all lab records."""

    @abstractmethod
    async def add_async(self, lab_record: LabRecord) -> None:
        """Add a new lab record."""

    @abstractmethod
    async def update_async(self, lab_record: LabRecord) -> None:
        """Update an existing lab record."""

    @abstractmethod
    async def remove_async(self, lab_record: LabRecord) -> None:
        """Remove a lab record."""

    @abstractmethod
    async def remove_by_id_async(self, record_id: str) -> None:
        """Remove a lab record by ID."""

    @abstractmethod
    async def remove_by_lab_id_async(self, worker_id: str, lab_id: str) -> bool:
        """Remove a lab record by worker ID and CML lab ID.

        Args:
            worker_id: Worker ID hosting the lab
            lab_id: CML lab ID to remove

        Returns:
            True if record was deleted, False if not found
        """

    @abstractmethod
    async def remove_by_worker_async(self, worker_id: str) -> None:
        """Remove all lab records for a worker."""
