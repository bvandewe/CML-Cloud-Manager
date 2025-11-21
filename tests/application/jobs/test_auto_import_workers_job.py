from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from neuroglia.mediation import Mediator

from application.commands.bulk_import_cml_workers_command import BulkImportCMLWorkersCommand, BulkImportResult
from application.commands.request_worker_data_refresh_command import RequestWorkerDataRefreshCommand
from application.jobs.auto_import_workers_job import AutoImportWorkersJob
from integration.enums import AwsRegion
from integration.models.cml_worker_instance_dto import CMLWorkerInstanceDto


@pytest.mark.asyncio
async def test_auto_import_triggers_refresh() -> None:
    # Arrange
    mediator = AsyncMock(spec=Mediator)
    job = AutoImportWorkersJob(mediator=mediator)

    # Mock settings
    with patch("application.jobs.auto_import_workers_job.app_settings") as mock_settings:
        mock_settings.auto_import_workers_enabled = True
        mock_settings.auto_import_workers_region = "us-east-1"
        mock_settings.auto_import_workers_ami_name = "cml-ami"

        # Mock BulkImport result
        worker_dto = MagicMock(spec=CMLWorkerInstanceDto)
        worker_dto.aws_instance_id = "i-12345"
        worker_dto.aws_region = AwsRegion.US_EAST_1

        bulk_result = MagicMock()
        bulk_result.status = 200
        bulk_result.data = BulkImportResult(
            imported=[worker_dto], skipped=[], total_found=1, total_imported=1, total_skipped=0
        )

        mediator.execute_async.side_effect = [
            bulk_result,  # First call: BulkImport
            MagicMock(),  # Second call: Refresh
        ]

        # Act
        await job.run_every()

        # Assert
        # Verify BulkImport was called
        assert mediator.execute_async.call_count >= 1
        args, _ = mediator.execute_async.call_args_list[0]
        assert isinstance(args[0], BulkImportCMLWorkersCommand)

        # Verify Refresh was called
        assert mediator.execute_async.call_count == 2
        args, _ = mediator.execute_async.call_args_list[1]
        cmd = args[0]
        assert isinstance(cmd, RequestWorkerDataRefreshCommand)
        assert cmd.worker_id == "i-12345"
        assert cmd.region == "us-east-1"
        args, _ = mediator.execute_async.call_args_list[1]
        cmd = args[0]
        assert isinstance(cmd, RequestWorkerDataRefreshCommand)
        assert cmd.worker_id == "i-12345"
        assert cmd.region == "us-east-1"
