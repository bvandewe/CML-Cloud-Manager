"""Lab Record Aggregate for tracking CML lab state and history."""

from datetime import datetime, timezone
from typing import Optional

from multipledispatch import dispatch
from neuroglia.data.abstractions import AggregateRoot, AggregateState

from domain.events.lab_record_events import (LabRecordCreatedDomainEvent,
                                             LabRecordUpdatedDomainEvent,
                                             LabStateChangedDomainEvent)


class LabOperation:
    """Represents a single operation/change in lab history."""

    def __init__(
        self,
        timestamp: datetime,
        previous_state: Optional[str],
        new_state: str,
        changed_fields: Optional[dict] = None,
    ):
        self.timestamp = timestamp
        self.previous_state = previous_state
        self.new_state = new_state
        self.changed_fields = changed_fields or {}

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "changed_fields": self.changed_fields,
        }

    @staticmethod
    def from_dict(data: dict) -> "LabOperation":
        """Create from dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc)
        return LabOperation(
            timestamp=timestamp,
            previous_state=data.get("previous_state"),
            new_state=data["new_state"],
            changed_fields=data.get("changed_fields", {}),
        )


class LabRecordState(AggregateState[str]):
    """Encapsulates the persisted state for a Lab Record."""

    def __init__(self):
        super().__init__()
        self.id: str = ""
        self.worker_id: str = ""
        self.lab_id: str = ""

        # Current lab state
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self.notes: Optional[str] = None
        self.state: Optional[str] = None  # STARTED, STOPPED, DEFINED_ON_CORE, etc.
        self.owner_username: Optional[str] = None
        self.owner_fullname: Optional[str] = None
        self.node_count: int = 0
        self.link_count: int = 0
        self.groups: list[str] = []

        # Timestamps
        self.cml_created_at: Optional[datetime] = None  # When lab was created in CML
        self.modified_at: Optional[datetime] = None  # When lab was last modified in CML
        self.last_synced_at: Optional[datetime] = None  # When we last fetched from CML
        self.first_seen_at: Optional[datetime] = None  # When we first discovered this lab

        # Operation history (stored as dicts for MongoDB serialization)
        self.operation_history: list[dict] = []  # Max 50 entries
        self.max_history_size: int = 50

    @dispatch(LabRecordCreatedDomainEvent)
    def on(self, event: LabRecordCreatedDomainEvent) -> None:  # type: ignore[override]
        """Apply lab record creation event."""
        self.id = event.aggregate_id
        self.worker_id = event.worker_id
        self.lab_id = event.lab_id
        self.title = event.title
        self.description = event.description
        self.notes = event.notes
        self.state = event.state
        self.owner_username = event.owner_username
        self.owner_fullname = event.owner_fullname
        self.node_count = event.node_count
        self.link_count = event.link_count
        self.groups = event.groups or []
        self.cml_created_at = event.cml_created_at
        self.modified_at = event.cml_modified_at
        self.first_seen_at = event.first_seen_at
        self.last_synced_at = event.first_seen_at

    @dispatch(LabRecordUpdatedDomainEvent)
    def on(self, event: LabRecordUpdatedDomainEvent) -> None:  # type: ignore[override]
        """Apply lab record update event."""
        self.title = event.title
        self.description = event.description
        self.notes = event.notes
        self.state = event.state
        self.owner_username = event.owner_username
        self.owner_fullname = event.owner_fullname
        self.node_count = event.node_count
        self.link_count = event.link_count
        self.groups = event.groups or []
        self.modified_at = event.cml_modified_at
        self.last_synced_at = event.synced_at

    @dispatch(LabStateChangedDomainEvent)
    def on(self, event: LabStateChangedDomainEvent) -> None:  # type: ignore[override]
        """Apply lab state change event and add to history."""
        # Add to operation history
        operation = LabOperation(
            timestamp=event.changed_at,
            previous_state=event.previous_state,
            new_state=event.new_state,
            changed_fields=event.changed_fields,
        )

        # Add to history and maintain max size
        self.operation_history.append(operation.to_dict())
        if len(self.operation_history) > self.max_history_size:
            self.operation_history = self.operation_history[-self.max_history_size:]

        self.state = event.new_state


class LabRecord(AggregateRoot[LabRecordState, str]):
    """Lab Record aggregate for tracking CML lab state and operation history."""

    def __init__(self):
        super().__init__()

    def id(self) -> str:
        """Return the aggregate identifier with a precise type."""
        from typing import cast
        aggregate_id = super().id()
        if aggregate_id is None:
            raise ValueError("LabRecord aggregate identifier has not been initialized")
        return cast(str, aggregate_id)

    @staticmethod
    def create(
        lab_id: str,
        worker_id: str,
        title: Optional[str],
        description: Optional[str],
        notes: Optional[str],
        state: str,
        owner_username: Optional[str],
        owner_fullname: Optional[str],
        node_count: int,
        link_count: int,
        groups: Optional[list[str]],
        cml_created_at: Optional[datetime],
        cml_modified_at: Optional[datetime],
    ) -> "LabRecord":
        """Create a new lab record."""
        import uuid

        record = LabRecord()
        record_id = str(uuid.uuid4())
        first_seen = datetime.now(timezone.utc)

        event = LabRecordCreatedDomainEvent(
            aggregate_id=record_id,
            worker_id=worker_id,
            lab_id=lab_id,
            title=title,
            description=description,
            notes=notes,
            state=state,
            owner_username=owner_username,
            owner_fullname=owner_fullname,
            node_count=node_count,
            link_count=link_count,
            groups=groups,
            cml_created_at=cml_created_at,
            cml_modified_at=cml_modified_at,
            first_seen_at=first_seen,
        )

        record.state.on(record.register_event(event))  # type: ignore
        return record

    def update_from_cml(
        self,
        title: Optional[str],
        description: Optional[str],
        notes: Optional[str],
        state: str,
        owner_username: Optional[str],
        owner_fullname: Optional[str],
        node_count: int,
        link_count: int,
        groups: Optional[list[str]],
        cml_modified_at: Optional[datetime],
    ) -> None:
        """Update lab record with fresh data from CML."""
        synced_at = datetime.now(timezone.utc)

        # Check if state changed to record in history
        if self.state.state and self.state.state != state:
            changed_fields = {}
            if self.state.title != title:
                changed_fields["title"] = {"old": self.state.title, "new": title}
            if self.state.node_count != node_count:
                changed_fields["node_count"] = {"old": self.state.node_count, "new": node_count}
            if self.state.link_count != link_count:
                changed_fields["link_count"] = {"old": self.state.link_count, "new": link_count}

            state_change_event = LabStateChangedDomainEvent(
                aggregate_id=self.id(),
                lab_id=self.state.lab_id,
                previous_state=self.state.state,
                new_state=state,
                changed_fields=changed_fields,
                changed_at=synced_at,
            )
            self.state.on(self.register_event(state_change_event))  # type: ignore

        # Update all fields
        update_event = LabRecordUpdatedDomainEvent(
            aggregate_id=self.id(),
            lab_id=self.state.lab_id,
            title=title,
            description=description,
            notes=notes,
            state=state,
            owner_username=owner_username,
            owner_fullname=owner_fullname,
            node_count=node_count,
            link_count=link_count,
            groups=groups,
            cml_modified_at=cml_modified_at,
            synced_at=synced_at,
        )

        self.state.on(self.register_event(update_event))  # type: ignore
