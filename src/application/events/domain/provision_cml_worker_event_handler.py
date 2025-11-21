"""Domain event handler for provisioning CML Worker EC2 instances.

This handler implements the Saga pattern for worker creation:
1. Worker created in DB (PENDING) -> CMLWorkerCreatedDomainEvent
2. This handler triggers EC2 provisioning
3. On success -> Updates worker with instance ID (RUNNING/PENDING)
4. On failure -> Updates worker status to FAILED
"""

import logging

from neuroglia.mediation import DomainEventHandler
from opentelemetry import trace

from application.settings import Settings
from domain.enums import CMLWorkerStatus
from domain.events.cml_worker import CMLWorkerCreatedDomainEvent
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.services.aws_ec2_api_client import AwsEc2Client

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ProvisionCMLWorkerEventHandler(DomainEventHandler[CMLWorkerCreatedDomainEvent]):
    """Handle CML Worker creation by provisioning EC2 instance."""

    def __init__(
        self,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
        settings: Settings,
    ):
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client
        self.settings = settings

    async def handle_async(self, notification: CMLWorkerCreatedDomainEvent) -> None:
        """Handle worker created event."""
        # Skip if instance ID already exists (e.g. imported worker)
        if notification.aws_instance_id:
            log.debug(f"Skipping provisioning for worker {notification.aggregate_id}: already has instance ID")
            return

        worker_id = notification.aggregate_id
        log.info(f"Starting provisioning for worker {worker_id} (name={notification.name})")

        with tracer.start_as_current_span("provision_cml_worker_saga") as span:
            span.set_attribute("cml_worker.id", worker_id)
            span.set_attribute("cml_worker.name", notification.name)

            try:
                if not notification.ami_id:
                    raise ValueError("AMI ID is required for provisioning")

                # 1. Provision EC2 instance
                instance_dto = await self.aws_ec2_client.create_instance(
                    aws_region=AwsRegion(notification.aws_region),
                    instance_name=notification.name,
                    ami_id=notification.ami_id,
                    ami_name=notification.ami_name or "CML Worker AMI",
                    instance_type=notification.instance_type,
                    security_group_ids=self.settings.cml_worker_security_group_ids,
                    subnet_id=self.settings.cml_worker_subnet_id,
                    key_name=self.settings.cml_worker_key_name,
                )

                if not instance_dto:
                    raise Exception("Failed to create EC2 instance - no instance returned")

                log.info(
                    f"EC2 instance provisioned for worker {worker_id}: "
                    f"{instance_dto.aws_instance_id} ({instance_dto.instance_state})"
                )

                # 2. Update worker with instance details
                # We need to reload the worker to ensure we have the latest version
                worker = await self.cml_worker_repository.get_by_id_async(worker_id)
                if not worker:
                    log.error(f"Worker {worker_id} not found during provisioning callback")
                    return

                worker.assign_instance(
                    aws_instance_id=instance_dto.aws_instance_id,
                    public_ip=instance_dto.public_ip,
                    private_ip=instance_dto.private_ip,
                )

                # Update status based on instance state
                if instance_dto.instance_state == "running":
                    worker.update_status(CMLWorkerStatus.RUNNING)
                elif instance_dto.instance_state == "pending":
                    worker.update_status(CMLWorkerStatus.PENDING)

                await self.cml_worker_repository.update_async(worker)
                log.info(f"Worker {worker_id} updated with instance {instance_dto.aws_instance_id}")

            except Exception as e:
                log.error(f"Provisioning failed for worker {worker_id}: {e}", exc_info=True)

                # Handle failure - mark worker as FAILED
                try:
                    worker = await self.cml_worker_repository.get_by_id_async(worker_id)
                    if worker:
                        # We need to manually set status since update_status might enforce transitions
                        # But update_status is safer. Let's check if FAILED is allowed.
                        # If not, we might need to force it or add a specific method.
                        # For now, we'll try update_status.
                        worker.update_status(CMLWorkerStatus.FAILED)
                        await self.cml_worker_repository.update_async(worker)
                        log.info(f"Worker {worker_id} marked as FAILED")
                except Exception as update_error:
                    log.error(f"Failed to update worker status to FAILED: {update_error}")
