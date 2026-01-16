"""AWS EC2 Cloud Provider Implementation.

Implements the CloudProviderInterface for AWS EC2 instances.
Used for provisioning and managing CML worker instances.
"""

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from integration.providers.cloud_provider import CloudProviderInterface, InstanceInfo

logger = logging.getLogger(__name__)


class AwsEc2Provider(CloudProviderInterface):
    """
    AWS EC2 implementation of the Cloud Provider SPI.

    Handles:
    - EC2 instance creation (m5zn.metal for CML workers)
    - Instance lifecycle (start, stop, terminate)
    - Instance status queries
    - Tag-based instance discovery
    """

    def __init__(
        self,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        self.region = region

        # Initialize boto3 client
        session_kwargs: dict[str, Any] = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key

        self._session = boto3.Session(**session_kwargs)
        self._ec2 = self._session.client("ec2")
        self._ec2_resource = self._session.resource("ec2")

        # Default configuration (should come from WorkerTemplate)
        self._default_instance_type = "m5zn.metal"
        self._default_ami_name = "cml-worker-*"

    async def create_instance(
        self,
        template_name: str,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Create a new EC2 instance for CML worker."""
        logger.info(f"Creating EC2 instance for template: {template_name}")

        # TODO: Get configuration from WorkerTemplate via API
        # For now, use defaults
        instance_config = await self._get_instance_config(template_name)

        # Build tags
        instance_tags = {
            "Name": f"cml-worker-{template_name}",
            "ccm:template": template_name,
            "ccm:managed": "true",
        }
        if tags:
            instance_tags.update(tags)

        tag_specifications = [
            {
                "ResourceType": "instance",
                "Tags": [{"Key": k, "Value": v} for k, v in instance_tags.items()],
            }
        ]

        try:
            response = self._ec2.run_instances(
                ImageId=instance_config["ami_id"],
                InstanceType=instance_config["instance_type"],
                MinCount=1,
                MaxCount=1,
                KeyName=instance_config.get("key_name"),
                SecurityGroupIds=instance_config.get("security_group_ids", []),
                SubnetId=instance_config.get("subnet_id"),
                TagSpecifications=tag_specifications,
                # Additional options
                EbsOptimized=True,
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": instance_config.get("volume_size_gb", 500),
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )

            instance_id = response["Instances"][0]["InstanceId"]
            logger.info(f"Created EC2 instance: {instance_id}")
            return instance_id

        except ClientError as e:
            logger.error(f"Failed to create EC2 instance: {e}")
            raise

    async def terminate_instance(self, instance_id: str) -> None:
        """Terminate an EC2 instance."""
        logger.info(f"Terminating EC2 instance: {instance_id}")

        try:
            self._ec2.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Terminated EC2 instance: {instance_id}")
        except ClientError as e:
            logger.error(f"Failed to terminate EC2 instance: {e}")
            raise

    async def stop_instance(self, instance_id: str) -> None:
        """Stop an EC2 instance."""
        logger.info(f"Stopping EC2 instance: {instance_id}")

        try:
            self._ec2.stop_instances(InstanceIds=[instance_id])
            logger.info(f"Stopped EC2 instance: {instance_id}")
        except ClientError as e:
            logger.error(f"Failed to stop EC2 instance: {e}")
            raise

    async def start_instance(self, instance_id: str) -> None:
        """Start a stopped EC2 instance."""
        logger.info(f"Starting EC2 instance: {instance_id}")

        try:
            self._ec2.start_instances(InstanceIds=[instance_id])
            logger.info(f"Started EC2 instance: {instance_id}")
        except ClientError as e:
            logger.error(f"Failed to start EC2 instance: {e}")
            raise

    async def get_instance_status(self, instance_id: str) -> str:
        """Get the status of an EC2 instance."""
        try:
            response = self._ec2.describe_instances(InstanceIds=[instance_id])
            if response["Reservations"]:
                state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
                return state
            return "not-found"
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return "not-found"
            logger.error(f"Failed to get EC2 instance status: {e}")
            raise

    async def get_instance_info(self, instance_id: str) -> InstanceInfo | None:
        """Get detailed information about an EC2 instance."""
        try:
            response = self._ec2.describe_instances(InstanceIds=[instance_id])
            if not response["Reservations"]:
                return None

            instance = response["Reservations"][0]["Instances"][0]
            tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}

            return InstanceInfo(
                instance_id=instance["InstanceId"],
                status=instance["State"]["Name"],
                public_ip=instance.get("PublicIpAddress"),
                private_ip=instance.get("PrivateIpAddress"),
                launch_time=instance.get("LaunchTime", "").isoformat() if instance.get("LaunchTime") else None,
                instance_type=instance.get("InstanceType"),
                tags=tags,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return None
            logger.error(f"Failed to get EC2 instance info: {e}")
            raise

    async def list_instances(
        self,
        tags: dict[str, str] | None = None,
    ) -> list[InstanceInfo]:
        """List EC2 instances, optionally filtered by tags."""
        filters = [
            {"Name": "tag:ccm:managed", "Values": ["true"]},
        ]

        if tags:
            for key, value in tags.items():
                filters.append({"Name": f"tag:{key}", "Values": [value]})

        try:
            response = self._ec2.describe_instances(Filters=filters)

            instances = []
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
                    instances.append(
                        InstanceInfo(
                            instance_id=instance["InstanceId"],
                            status=instance["State"]["Name"],
                            public_ip=instance.get("PublicIpAddress"),
                            private_ip=instance.get("PrivateIpAddress"),
                            launch_time=instance.get("LaunchTime", "").isoformat()
                            if instance.get("LaunchTime")
                            else None,
                            instance_type=instance.get("InstanceType"),
                            tags=instance_tags,
                        )
                    )

            return instances

        except ClientError as e:
            logger.error(f"Failed to list EC2 instances: {e}")
            raise

    async def _get_instance_config(self, template_name: str) -> dict[str, Any]:
        """Get instance configuration from template.

        TODO: Fetch from Control Plane API / WorkerTemplate
        """
        # Mock configuration - should come from WorkerTemplate
        return {
            "ami_id": "ami-12345678",  # Should be resolved from AMI name
            "instance_type": self._default_instance_type,
            "key_name": None,
            "security_group_ids": [],
            "subnet_id": None,
            "volume_size_gb": 500,
        }
