"""Enable CloudWatch Detailed Monitoring Command

One-time command to enable detailed monitoring on existing workers.
Run this for instances created before detailed monitoring was added.
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

from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.exceptions import IntegrationException
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class EnableWorkerDetailedMonitoringCommand(Command[OperationResult[bool]]):
    """Command to enable detailed CloudWatch monitoring on a worker's EC2 instance.

    This enables 1-minute metric granularity instead of the default 5-minute.
    Cost: ~$2.10/month per instance.
    """

    worker_id: str


class EnableWorkerDetailedMonitoringCommandHandler(
    CommandHandlerBase,
    CommandHandler[EnableWorkerDetailedMonitoringCommand, OperationResult[bool]],
):
    """Handle enabling detailed monitoring on worker instances."""

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
        self, request: EnableWorkerDetailedMonitoringCommand
    ) -> OperationResult[bool]:
        """Enable detailed monitoring on worker's EC2 instance.

        Args:
            request: Command with worker ID

        Returns:
            OperationResult with True if enabled successfully
        """
        command = request

        add_span_attributes({"cml_worker.id": command.worker_id})

        try:
            # Load worker
            worker = await self.cml_worker_repository.get_by_id_async(command.worker_id)
            if not worker:
                error_msg = f"Worker not found: {command.worker_id}"
                log.error(error_msg)
                return self.bad_request(error_msg)

            if not worker.state.aws_instance_id:
                error_msg = f"Worker {command.worker_id} has no AWS instance ID"
                log.error(error_msg)
                return self.bad_request(error_msg)

            # Enable monitoring via boto3 client
            import boto3

            ec2_client = boto3.client(
                "ec2",
                aws_access_key_id=self.aws_ec2_client.aws_account_credentials.aws_access_key_id,
                aws_secret_access_key=self.aws_ec2_client.aws_account_credentials.aws_secret_access_key,
                region_name=worker.state.aws_region,
            )

            ec2_client.monitor_instances(InstanceIds=[worker.state.aws_instance_id])

            log.info(
                f"✅ Enabled detailed CloudWatch monitoring for worker {command.worker_id}, "
                f"instance {worker.state.aws_instance_id}"
            )

            # Update worker aggregate with monitoring status
            worker.update_cloudwatch_monitoring(enabled=True)
            await self.cml_worker_repository.add_or_update_async(worker)
            log.info(
                f"Updated worker {command.worker_id} monitoring status in database"
            )

            return self.ok(True)

        except IntegrationException as ex:
            log.error(
                f"Failed to enable monitoring for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"AWS integration error: {ex}")

        except Exception as ex:
            log.error(
                f"Unexpected error enabling monitoring for worker {command.worker_id}: {ex}",
                exc_info=True,
            )
            return self.internal_server_error(f"Unexpected error: {ex}")
