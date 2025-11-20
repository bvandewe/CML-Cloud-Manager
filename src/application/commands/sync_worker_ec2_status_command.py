"""Sync Worker EC2 Status command with handler.

This command synchronizes the worker's status with AWS EC2 instance state.
It queries EC2 for current instance status and updates the worker aggregate.
"""

import logging
from dataclasses import dataclass

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import (
    CloudEventPublishingOptions,
)
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace

from domain.enums import CMLWorkerStatus
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.enums import AwsRegion
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class SyncWorkerEC2StatusCommand(Command[OperationResult[dict]]):
    """Command to synchronize worker status with AWS EC2 instance state.

    This command:
    1. Queries AWS EC2 for current instance state and details
    2. Updates worker status based on EC2 state
    3. Updates EC2 health metrics (status checks)
    4. Updates instance details (IPs, instance type, AMI)
    5. Updates CloudWatch monitoring status

    Returns dict with sync summary.
    """

    worker_id: str


class SyncWorkerEC2StatusCommandHandler(
    CommandHandlerBase,
    CommandHandler[SyncWorkerEC2StatusCommand, OperationResult[dict]],
):
    """Handle worker EC2 status synchronization."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        aws_ec2_client: AwsEc2Client,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.aws_ec2_client = aws_ec2_client

    async def handle_async(
        self, request: SyncWorkerEC2StatusCommand
    ) -> OperationResult[dict]:
        """Handle sync worker EC2 status command.

        Args:
            request: Sync command with worker ID

        Returns:
            OperationResult with sync summary dict or error
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "operation": "sync_ec2_status",
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # 1. Load worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(
                    command.worker_id
                )

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                if not worker.state.aws_instance_id:
                    error_msg = (
                        f"CML Worker {command.worker_id} has no AWS instance assigned"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id)
                span.set_attribute(
                    "cml_worker.current_status", worker.state.status.value
                )

            # 2. Query AWS EC2 for current instance status
            with tracer.start_as_current_span("query_ec2_instance_status") as span:
                aws_region = AwsRegion(worker.state.aws_region)

                status_checks = self.aws_ec2_client.get_instance_status_checks(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if not status_checks:
                    error_msg = (
                        f"EC2 instance {worker.state.aws_instance_id} not found in AWS"
                    )
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                ec2_state = status_checks["instance_state"]
                span.set_attribute("ec2.current_state", ec2_state)

                # Update EC2 health metrics
                worker.update_ec2_metrics(
                    instance_state_detail=status_checks["instance_status_check"],
                    system_status_check=status_checks["ec2_system_status_check"],
                )

                # Get EC2 instance details (IPs, type, AMI)
                instance_details = self.aws_ec2_client.get_instance_details(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                if instance_details:
                    # Fetch AMI details from AWS
                    ami_details = None
                    if instance_details.image_id:
                        ami_details = self.aws_ec2_client.get_ami_details(
                            aws_region=aws_region, ami_id=instance_details.image_id
                        )
                        if ami_details:
                            log.info(
                                f"Retrieved AMI details for worker {command.worker_id}: "
                                f"name={ami_details.ami_name}, "
                                f"description={ami_details.ami_description[:50] if ami_details.ami_description else 'N/A'}..."
                            )

                    # Update instance details
                    worker.update_ec2_instance_details(
                        public_ip=instance_details.public_ip,
                        private_ip=instance_details.private_ip,
                        instance_type=instance_details.type,
                        ami_id=instance_details.image_id,
                        ami_name=ami_details.ami_name if ami_details else None,
                        ami_description=(
                            ami_details.ami_description if ami_details else None
                        ),
                        ami_creation_date=(
                            ami_details.ami_creation_date if ami_details else None
                        ),
                    )

                    # Auto-populate HTTPS endpoint if public IP available and not already set
                    if instance_details.public_ip and not worker.state.https_endpoint:
                        worker.update_endpoint(
                            https_endpoint=f"https://{instance_details.public_ip}",
                            public_ip=instance_details.public_ip,
                        )
                        log.info(
                            f"Auto-populated HTTPS endpoint for worker {command.worker_id}: "
                            f"https://{instance_details.public_ip}"
                        )

                # Check CloudWatch detailed monitoring status
                monitoring_state = status_checks.get("monitoring_state", "disabled")
                monitoring_enabled = monitoring_state == "enabled"

                # Update worker monitoring status if changed
                if (
                    worker.state.cloudwatch_detailed_monitoring_enabled
                    != monitoring_enabled
                ):
                    worker.update_cloudwatch_monitoring(monitoring_enabled)
                    log.info(
                        f"Worker {command.worker_id} CloudWatch monitoring status updated: {monitoring_state}"
                    )

                # Fetch and update AWS tags
                try:
                    aws_tags = self.aws_ec2_client.get_tags(
                        aws_region=aws_region,
                        instance_id=worker.state.aws_instance_id,
                    )
                    if aws_tags:
                        worker.update_aws_tags(aws_tags)
                        log.debug(
                            f"Updated {len(aws_tags)} AWS tags for worker {command.worker_id}"
                        )
                except Exception as e:
                    log.warning(
                        f"Failed to fetch AWS tags for worker {command.worker_id}: {e}"
                    )

                # Map EC2 state to worker status
                ec2_state_to_worker_status = {
                    "pending": CMLWorkerStatus.PENDING,
                    "running": CMLWorkerStatus.RUNNING,
                    "stopping": CMLWorkerStatus.STOPPING,
                    "stopped": CMLWorkerStatus.STOPPED,
                    "shutting-down": CMLWorkerStatus.TERMINATED,
                    "terminated": CMLWorkerStatus.TERMINATED,
                }
                new_status = ec2_state_to_worker_status.get(
                    ec2_state, CMLWorkerStatus.PENDING
                )

                # Update worker status if changed
                status_changed = worker.update_status(new_status)
                if status_changed:
                    log.info(
                        f"Worker {command.worker_id} status updated: {worker.state.status.value}"
                    )

                span.set_attribute("ec2.new_status", new_status.value)
                span.set_attribute("worker.status_changed", status_changed)

            # 3. Save updated worker
            with tracer.start_as_current_span("save_worker"):
                await self.cml_worker_repository.update_async(worker)

            # 4. Build result summary
            result = {
                "worker_id": command.worker_id,
                "ec2_state": ec2_state,
                "worker_status": worker.state.status.value,
                "status_changed": status_changed,
                "public_ip": worker.state.public_ip,
                "private_ip": worker.state.private_ip,
                "https_endpoint": worker.state.https_endpoint,
                "cloudwatch_monitoring_enabled": worker.state.cloudwatch_detailed_monitoring_enabled,
            }

            log.info(
                f"Synced EC2 status for worker {command.worker_id}: {ec2_state} -> {worker.state.status.value}"
            )

            return self.ok(result)

        except Exception as ex:
            log.error(
                f"Failed to sync EC2 status for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(
                f"Failed to sync worker EC2 status: {str(ex)}"
            )
