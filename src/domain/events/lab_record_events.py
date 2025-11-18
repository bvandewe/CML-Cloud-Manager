"""Domain events for Lab Records."""

from dataclasses import dataclass
from datetime import datetime

from neuroglia.data.abstractions import DomainEvent


@dataclass
class LabRecordCreatedDomainEvent(DomainEvent):
    """Event raised when a lab record is first created."""

    worker_id: str
    lab_id: str
    title: str | None
    description: str | None
    notes: str | None
    state: str
    owner_username: str | None
    owner_fullname: str | None
    node_count: int
    link_count: int
    groups: list[str] | None
    cml_created_at: datetime | None
    cml_modified_at: datetime | None
    first_seen_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        worker_id: str,
        lab_id: str,
        title: str | None,
        description: str | None,
        notes: str | None,
        state: str,
        owner_username: str | None,
        owner_fullname: str | None,
        node_count: int,
        link_count: int,
        groups: list[str] | None,
        cml_created_at: datetime | None,
        cml_modified_at: datetime | None,
        first_seen_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.worker_id = worker_id
        self.lab_id = lab_id
        self.title = title
        self.description = description
        self.notes = notes
        self.state = state
        self.owner_username = owner_username
        self.owner_fullname = owner_fullname
        self.node_count = node_count
        self.link_count = link_count
        self.groups = groups
        self.cml_created_at = cml_created_at
        self.cml_modified_at = cml_modified_at
        self.first_seen_at = first_seen_at


@dataclass
class LabRecordUpdatedDomainEvent(DomainEvent):
    """Event raised when a lab record is updated with fresh CML data."""

    lab_id: str
    title: str | None
    description: str | None
    notes: str | None
    state: str
    owner_username: str | None
    owner_fullname: str | None
    node_count: int
    link_count: int
    groups: list[str] | None
    cml_modified_at: datetime | None
    synced_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        lab_id: str,
        title: str | None,
        description: str | None,
        notes: str | None,
        state: str,
        owner_username: str | None,
        owner_fullname: str | None,
        node_count: int,
        link_count: int,
        groups: list[str] | None,
        cml_modified_at: datetime | None,
        synced_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.lab_id = lab_id
        self.title = title
        self.description = description
        self.notes = notes
        self.state = state
        self.owner_username = owner_username
        self.owner_fullname = owner_fullname
        self.node_count = node_count
        self.link_count = link_count
        self.groups = groups
        self.cml_modified_at = cml_modified_at
        self.synced_at = synced_at


@dataclass
class LabStateChangedDomainEvent(DomainEvent):
    """Event raised when a lab's state changes (e.g., STARTED -> STOPPED)."""

    lab_id: str
    previous_state: str
    new_state: str
    changed_fields: dict
    changed_at: datetime

    def __init__(
        self,
        aggregate_id: str,
        lab_id: str,
        previous_state: str,
        new_state: str,
        changed_fields: dict,
        changed_at: datetime,
    ) -> None:
        super().__init__(aggregate_id)
        self.aggregate_id = aggregate_id
        self.lab_id = lab_id
        self.previous_state = previous_state
        self.new_state = new_state
        self.changed_fields = changed_fields
        self.changed_at = changed_at
