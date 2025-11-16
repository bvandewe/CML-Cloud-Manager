import datetime
from enum import Enum
from typing import Union


class Ec2InstanceStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    BUSY = "BUSY"
    LOCKED = "LOCKED"
    COMPLETED = "COMPLETED"


class Ec2InstanceType(str, Enum):
    MICRO = "t3.micro"
    SMALL = "t3.small"
    MEDIUM = "t3.medium"
    LARGE = "t3.large"
    METAL = "m5zn.metal"


class Ec2InstanceResourcesUtilizationRelativeStartTime(Enum):
    THIRTY_SEC_AGO = "30s"
    ONE_MIN_AGO = "1m"
    FIVE_MIN_AGO = "5m"
    TEN_MIN_AGO = "10m"

    @classmethod
    def to_timedelta(
        cls, value: Union[str, "Ec2InstanceResourcesUtilizationRelativeStartTime"]
    ) -> datetime.timedelta:
        """Converts the enum value to a timedelta object."""
        if isinstance(value, cls):
            value = value.value
        time_dict = {"s": 1, "m": 60}
        unit = value[-1]  # type: ignore[index]
        delta = int(value[:-1]) * time_dict[unit]  # type: ignore[index]
        return datetime.timedelta(seconds=delta)
