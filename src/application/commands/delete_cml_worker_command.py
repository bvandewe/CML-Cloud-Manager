"""Delete CML Worker command with handler."""

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
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceNotFoundException,
    EC2InstanceOperationException,
    IntegrationException,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class DeleteCMLWorkerCommand(Command[OperationResult[bool]]):
    """Command to delete a CML Worker from the local database.

    This command:
    1. Retrieves the worker from repository
    2. Optionally terminates the EC2 instance if terminate_instance=True
    3. Marks worker aggregate as terminated (if not already)
    4. Deletes the worker record from the database

    Args:
        worker_id: ID of the worker to delete
        terminate_instance: If True, terminate the EC2 instance before deletion
        deleted_by: Optional user ID who initiated the deletion
    """

    worker_id: str
    terminate_instance: bool = False
    deleted_by: str | None = None


class DeleteCMLWorkerCommandHandler(
    CommandHandlerBase,
    CommandHandler[DeleteCMLWorkerCommand, OperationResult[bool]],
):
    """Handle deleting a CML Worker from the local database with optional EC2 termination."""

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

    async def handle_async(self, request: DeleteCMLWorkerCommand) -> OperationResult[bool]:
        """Handle delete CML Worker command.

        Args:
            request: Delete command with worker ID and options

        Returns:
            OperationResult with True if deleted successfully, or error

        Raises:
            EC2InstanceNotFoundException: If instance doesn't exist (logged as warning)
            EC2InstanceOperationException: If terminate operation fails
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "cml_worker.terminate_instance": command.terminate_instance,
                "cml_worker.has_deleted_by": command.deleted_by is not None,
            }
        )

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # Retrieve worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(command.worker_id)

                if not worker:
                    error_msg = f"CML Worker not found: {command.worker_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("ec2.instance_id", worker.state.aws_instance_id or "none")
                span.set_attribute("cml_worker.current_status", worker.state.status.value)

            # Terminate EC2 instance if requested and instance exists
            if command.terminate_instance and worker.state.aws_instance_id:
                with tracer.start_as_current_span("terminate_ec2_instance") as span:
                    try:
                        aws_region = AwsRegion(worker.state.aws_region)

                        success = self.aws_ec2_client.terminate_instance(
                            aws_region=aws_region,
                            instance_id=worker.state.aws_instance_id,
                        )

                        if not success:
                            log.warning(
                                f"Failed to terminate EC2 instance {worker.state.aws_instance_id}, "
                                "but will continue with deletion"
                            )

                        span.set_attribute("ec2.terminate_success", success)

                    except EC2InstanceNotFoundException as e:
                        # Instance already gone - log warning and continue
                        log.warning(
                            f"EC2 instance {worker.state.aws_instance_id} not found during deletion: {e}. "
                            "Continuing with database deletion."
                        )
                        span.set_attribute("ec2.already_terminated", True)

                    except (
                        EC2InstanceOperationException,
                        EC2AuthenticationException,
                        IntegrationException,
                    ) as e:
                        # EC2 termination failed - don't proceed with deletion
                        error_msg = (
                            f"Failed to terminate EC2 instance {worker.state.aws_instance_id}: {e}. "
                            "Worker not deleted from database."
                        )
                        log.error(error_msg)
                        return self.bad_request(error_msg)
            elif command.terminate_instance and not worker.state.aws_instance_id:
                log.info(f"CML Worker {command.worker_id} has no AWS instance to terminate")

            # Mark worker as terminated in domain before deletion
            with tracer.start_as_current_span("mark_worker_terminated") as span:
                if worker.state.status != CMLWorkerStatus.TERMINATED:
                    worker.terminate(terminated_by=command.deleted_by)
                    span.set_attribute("cml_worker.marked_terminated", True)
                else:
                    span.set_attribute("cml_worker.already_terminated", True)

            # Delete worker from repository
            with tracer.start_as_current_span("delete_from_repository") as span:
                # Pass the worker to allow domain events to be published before deletion
                deleted = await self.cml_worker_repository.delete_async(command.worker_id, worker)

                if not deleted:
                    error_msg = f"Failed to delete CML Worker {command.worker_id} from database"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                span.set_attribute("cml_worker.deleted", True)

            log.info(
                f"CML Worker deleted successfully: id={worker.id()}, "
                f"aws_instance_id={worker.state.aws_instance_id or 'none'}, "
                f"terminate_instance={command.terminate_instance}, "
                f"deleted_by={command.deleted_by or 'system'}"
            )

            return self.ok(True)

        except (
            EC2InstanceOperationException,
            EC2AuthenticationException,
            IntegrationException,
        ) as e:
            log.error(f"Failed to delete CML Worker {command.worker_id}: {e}")
            return self.bad_request(str(e))

        except Exception as e:
            log.exception(f"Unexpected error deleting CML Worker {command.worker_id}")
            return self.bad_request(f"Unexpected error: {str(e)}")
