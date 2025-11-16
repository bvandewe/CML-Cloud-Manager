"""Data Transfer Object for CML Worker EC2 Instance creation and management.

This module provides the DTO used by the AWS EC2 API client to represent
EC2 instances that will run CML (Cisco Modeling Labs).
"""

from dataclasses import dataclass, field

from integration.enums import AwsRegion


@dataclass
class CMLWorkerInstanceDto:
    """DTO representing an EC2 instance provisioned for CML Worker.

    This DTO is returned when creating EC2 instances through the AWS API client
    and contains the essential information needed to track and manage the instance.

    Attributes:
        id: Unique identifier for this DTO record
        aws_instance_id: AWS EC2 instance ID (e.g., 'i-1234567890abcdef0')
        aws_region: AWS region where the instance is provisioned
        instance_name: Human-readable name for the instance
        ami_id: Amazon Machine Image ID used to launch the instance
        ami_name: Human-readable name of the AMI (e.g., 'CML-2.7.0-Ubuntu-22.04')
        instance_type: EC2 instance type (e.g., 'c5.2xlarge')
        security_group_ids: List of security group IDs attached to the instance
        subnet_id: VPC subnet ID where the instance is launched
        instance_state: Current EC2 instance state (pending, running, stopping, stopped, etc.)
        public_ip: Public IP address assigned to the instance (if any)
        private_ip: Private IP address within the VPC
        key_pair_name: SSH key pair name for instance access
        tags: Dictionary of tags attached to the instance
        instance_status_check: AWS instance status check result (ok, impaired, insufficient-data, etc.)
        ec2_system_status_check: AWS system/hardware status check result (ok, impaired, insufficient-data, etc.)
    """

    id: str
    aws_instance_id: str
    aws_region: AwsRegion
    instance_name: str
    ami_id: str
    ami_name: str | None
    instance_type: str
    security_group_ids: list[str]
    subnet_id: str
    instance_state: str | None = None
    public_ip: str | None = None
    private_ip: str | None = None
    key_pair_name: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    instance_status_check: str | None = None
    ec2_system_status_check: str | None = None
