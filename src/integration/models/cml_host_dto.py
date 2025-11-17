import datetime
import logging

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


cmlhost_instance_id_dto_field = Field(
    description="The AWS identifier of the CML Host VM instance.",
    examples=["i-abcdef12345abcdef"],
    min_length=19,
    max_length=19,
    pattern=r"^i-[a-zA-Z0-9]{17}$",
)


class CmlHostInstanceIdDto(BaseModel):
    id: str = cmlhost_instance_id_dto_field


class CmlHostDto(BaseModel):
    id: str = cmlhost_instance_id_dto_field

    uri: str
    """The URI where to reach the EC2 Instance."""

    created_at: datetime.datetime = datetime.datetime.now()

    last_modified: datetime.datetime | None = None
