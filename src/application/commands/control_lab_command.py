"""Lab Control Commands - Start, Stop, Wipe operations."""

import logging
from dataclasses import dataclass
from enum import Enum

from neuroglia.core import OperationResult
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_bus import CloudEventBus
from neuroglia.eventing.cloud_events.infrastructure.cloud_event_publisher import \
    CloudEventPublishingOptions
from neuroglia.mapping import Mapper
from neuroglia.mediation import Command, CommandHandler, Mediator
from opentelemetry import trace

from application.commands.command_handler_base import CommandHandlerBase
from application.settings import Settings
from domain.repositories.cml_worker_repository import CMLWorkerRepository
from integration.services.cml_api_client import CMLApiClient

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class LabAction(str, Enum):
    """Supported lab actions."""

    START = "start"
    STOP = "stop"
    WIPE = "wipe"


@dataclass
class ControlLabCommand(Command[OperationResult[dict]]):
    """Command to control a lab (start/stop/wipe).

    Attributes:
        worker_id: Worker ID hosting the lab
        lab_id: Lab identifier
        action: Action to perform (start/stop/wipe)
    """

    worker_id: str
    lab_id: str
    action: LabAction


class ControlLabCommandHandler(
    CommandHandlerBase,
    CommandHandler[ControlLabCommand, OperationResult[dict]],
):
    """Handler for lab control operations."""

    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        cloud_event_bus: CloudEventBus,
        cloud_event_publishing_options: CloudEventPublishingOptions,
        cml_worker_repository: CMLWorkerRepository,
        settings: Settings,
    ):
        super().__init__(
            mediator,
            mapper,
            cloud_event_bus,
            cloud_event_publishing_options,
        )
        self.cml_worker_repository = cml_worker_repository
        self.settings = settings

    async def handle_async(
        self, request: ControlLabCommand
    ) -> OperationResult[dict]:
        """Handle lab control command.

        Args:
            request: Control command with worker_id, lab_id, and action

        Returns:
            OperationResult with success/failure status
        """
        command = request

        with tracer.start_as_current_span("control_lab_command") as span:
            span.set_attribute("worker.id", command.worker_id)
            span.set_attribute("lab.id", command.lab_id)
            span.set_attribute("lab.action", command.action.value)

            try:
                # Get worker from repository
                worker = await self.cml_worker_repository.get_by_id_async(
                    command.worker_id
                )
                if not worker:
                    error_msg = f"Worker {command.worker_id} not found"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                # Validate worker has CML endpoint
                if not worker.state.https_endpoint:
                    error_msg = f"Worker {command.worker_id} has no HTTPS endpoint configured"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                # Create CML API client
                cml_client = CMLApiClient(
                    base_url=worker.state.https_endpoint,
                    username=self.settings.cml_worker_api_username,
                    password=self.settings.cml_worker_api_password,
                    verify_ssl=False,
                )

                # Perform the requested action
                success = False
                if command.action == LabAction.START:
                    log.info(f"Starting lab {command.lab_id} on worker {command.worker_id}")
                    success = await cml_client.start_lab(command.lab_id)
                elif command.action == LabAction.STOP:
                    log.info(f"Stopping lab {command.lab_id} on worker {command.worker_id}")
                    success = await cml_client.stop_lab(command.lab_id)
                elif command.action == LabAction.WIPE:
                    log.info(f"Wiping lab {command.lab_id} on worker {command.worker_id}")
                    success = await cml_client.wipe_lab(command.lab_id)
                else:
                    error_msg = f"Unknown action: {command.action}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

                if success:
                    log.info(
                        f"Successfully performed {command.action.value} on lab {command.lab_id}"
                    )
                    return self.ok(
                        {
                            "lab_id": command.lab_id,
                            "action": command.action.value,
                            "status": "success",
                        }
                    )
                else:
                    error_msg = f"Failed to {command.action.value} lab {command.lab_id}"
                    log.error(error_msg)
                    return self.bad_request(error_msg)

            except Exception as e:
                error_msg = (
                    f"Error performing {command.action.value} on lab {command.lab_id}: {str(e)}"
                )
                log.error(error_msg, exc_info=True)
                return self.bad_request(error_msg)
