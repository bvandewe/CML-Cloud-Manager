"""Update CML Worker tags command with handler."""

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
from integration.enums import AwsRegion
from integration.exceptions import (
    EC2AuthenticationException,
    EC2InstanceNotFoundException,
    EC2InvalidParameterException,
    EC2TagOperationException,
    IntegrationException,
)
from integration.services.aws_ec2_api_client import AwsEc2Client

from .command_handler_base import CommandHandlerBase

log = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class UpdateCMLWorkerTagsCommand(Command[OperationResult[dict[str, str]]]):
    """Command to add or update tags on a CML Worker EC2 instance.

    This command:
    1. Retrieves the worker from repository
    2. Adds/updates tags on the EC2 instance via AWS API
    3. Returns the updated tags

    Tags are key-value pairs that help organize and identify AWS resources.
    """

    worker_id: str
    tags: dict[str, str]
    updated_by: str | None = None


class UpdateCMLWorkerTagsCommandHandler(
    CommandHandlerBase,
    CommandHandler[UpdateCMLWorkerTagsCommand, OperationResult[dict[str, str]]],
):
    """Handle updating tags on a CML Worker EC2 instance."""

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
        self, request: UpdateCMLWorkerTagsCommand
    ) -> OperationResult[dict[str, str]]:
        """Handle update CML Worker tags command.

        Args:
            request: Update tags command with worker ID and tags

        Returns:
            OperationResult with updated tags dict, or error

        Raises:
            EC2InstanceNotFoundException: If instance doesn't exist
            EC2TagOperationException: If tag operation fails
            EC2AuthenticationException: If AWS credentials invalid
        """
        command = request

        # Add tracing context
        add_span_attributes(
            {
                "cml_worker.id": command.worker_id,
                "cml_worker.tags_count": len(command.tags),
                "cml_worker.has_updated_by": command.updated_by is not None,
            }
        )

        if not command.tags:
            error_msg = "No tags provided to update"
            log.error(error_msg)
            return self.bad_request(error_msg)

        try:
            with tracer.start_as_current_span("retrieve_cml_worker") as span:
                # Retrieve worker from repository
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

            with tracer.start_as_current_span("update_ec2_tags") as span:
                # Update tags on EC2 instance
                # This involves:
                # 1. Get current tags from AWS
                # 2. Add/update tags that are in the new tag dict
                # 3. Remove tags that are not in the new tag dict

                aws_region = AwsRegion(worker.state.aws_region)

                # Get current tags from AWS
                current_tags = self.aws_ec2_client.get_tags(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                # Determine which tags to add/update and which to remove
                tags_to_add = {}
                tags_to_remove = []

                # Find tags to add or update (in new dict but different value or not in current)
                for key, value in command.tags.items():
                    if key not in current_tags or current_tags[key] != value:
                        tags_to_add[key] = value

                # Find tags to remove (in current but not in new dict)
                for key in current_tags:
                    if key not in command.tags:
                        tags_to_remove.append(key)

                # Add/update tags if any
                if tags_to_add:
                    success = self.aws_ec2_client.add_tags(
                        aws_region=aws_region,
                        instance_id=worker.state.aws_instance_id,
                        tags=tags_to_add,
                    )

                    if not success:
                        error_msg = f"Failed to add tags to EC2 instance {worker.state.aws_instance_id}"
                        log.error(error_msg)
                        return self.bad_request(error_msg)

                    log.info(
                        f"Added/updated {len(tags_to_add)} tags on instance {worker.state.aws_instance_id}: {list(tags_to_add.keys())}"
                    )

                # Remove tags if any
                if tags_to_remove:
                    success = self.aws_ec2_client.remove_tags(
                        aws_region=aws_region,
                        instance_id=worker.state.aws_instance_id,
                        tag_keys=tags_to_remove,
                    )

                    if not success:
                        error_msg = f"Failed to remove tags from EC2 instance {worker.state.aws_instance_id}"
                        log.error(error_msg)
                        return self.bad_request(error_msg)

                    log.info(
                        f"Removed {len(tags_to_remove)} tags from instance {worker.state.aws_instance_id}: {tags_to_remove}"
                    )

                span.set_attribute("ec2.tags_added", len(tags_to_add))
                span.set_attribute("ec2.tags_removed", len(tags_to_remove))

            with tracer.start_as_current_span("retrieve_updated_tags") as span:
                # Retrieve all tags to return updated state
                all_tags = self.aws_ec2_client.get_tags(
                    aws_region=aws_region,
                    instance_id=worker.state.aws_instance_id,
                )

                span.set_attribute("ec2.total_tags", len(all_tags))

            log.info(
                f"CML Worker tags updated successfully: id={worker.id()}, "
                f"aws_instance_id={worker.state.aws_instance_id}, "
                f"updated_tags={list(command.tags.keys())}"
            )

            return self.ok(all_tags)

        except EC2InstanceNotFoundException as e:
            log.error(f"EC2 instance not found for CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Instance not found: {str(e)}")

        except EC2TagOperationException as e:
            log.error(f"Failed to update tags for CML Worker {command.worker_id}: {e}")
            return self.bad_request(f"Tag operation failed: {str(e)}")

        except EC2AuthenticationException as e:
            log.error(f"AWS authentication failed while updating tags: {e}")
            return self.bad_request(f"Authentication failed: {str(e)}")

        except EC2InvalidParameterException as e:
            log.error(f"Invalid parameters for updating tags: {e}")
            return self.bad_request(f"Invalid parameters: {str(e)}")

        except IntegrationException as e:
            log.error(f"Integration error while updating tags: {e}")
            return self.bad_request(f"Integration error: {str(e)}")

        except Exception as e:
            log.error(f"Unexpected error updating tags: {e}", exc_info=True)
            return self.bad_request(f"Unexpected error: {str(e)}")
