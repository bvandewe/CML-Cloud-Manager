"""Cloud Provider Service Provider Interface (SPI).

Abstraction layer for cloud infrastructure operations.
Allows pluggable cloud provider implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InstanceInfo:
    """Information about a cloud instance."""

    instance_id: str
    status: str
    public_ip: str | None = None
    private_ip: str | None = None
    launch_time: str | None = None
    instance_type: str | None = None
    tags: dict[str, str] | None = None


class CloudProviderInterface(ABC):
    """
    Abstract interface for cloud provider operations.

    Implementations:
    - AwsEc2Provider: AWS EC2 for CML workers
    - (Future) GcpComputeProvider: GCP Compute Engine
    - (Future) AzureVmProvider: Azure Virtual Machines
    """

    @abstractmethod
    async def create_instance(
        self,
        template_name: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """
        Create a new compute instance.

        Args:
            template_name: Name of the worker template to use
            tags: Additional tags to apply to the instance

        Returns:
            The instance ID of the created instance
        """
        pass

    @abstractmethod
    async def terminate_instance(self, instance_id: str) -> None:
        """
        Terminate a compute instance.

        Args:
            instance_id: The ID of the instance to terminate
        """
        pass

    @abstractmethod
    async def stop_instance(self, instance_id: str) -> None:
        """
        Stop a compute instance (but don't terminate).

        Args:
            instance_id: The ID of the instance to stop
        """
        pass

    @abstractmethod
    async def start_instance(self, instance_id: str) -> None:
        """
        Start a stopped compute instance.

        Args:
            instance_id: The ID of the instance to start
        """
        pass

    @abstractmethod
    async def get_instance_status(self, instance_id: str) -> str:
        """
        Get the status of a compute instance.

        Args:
            instance_id: The ID of the instance

        Returns:
            Status string (e.g., "running", "stopped", "terminated")
        """
        pass

    @abstractmethod
    async def get_instance_info(self, instance_id: str) -> InstanceInfo | None:
        """
        Get detailed information about a compute instance.

        Args:
            instance_id: The ID of the instance

        Returns:
            InstanceInfo object or None if not found
        """
        pass

    @abstractmethod
    async def list_instances(
        self,
        tags: dict[str, str] | None = None,
    ) -> list[InstanceInfo]:
        """
        List compute instances, optionally filtered by tags.

        Args:
            tags: Filter instances by these tags

        Returns:
            List of InstanceInfo objects
        """
        pass
