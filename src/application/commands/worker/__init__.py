"""Worker-related commands package."""

from .bulk_import_cml_workers_command import (
    BulkImportCMLWorkersCommand,
    BulkImportCMLWorkersCommandHandler,
    BulkImportResult,
)
from .bulk_sync_worker_cml_data_command import BulkSyncWorkerCMLDataCommand, BulkSyncWorkerCMLDataCommandHandler
from .bulk_sync_worker_ec2_status_command import (
    BulkSyncResult,
    BulkSyncWorkerEC2StatusCommand,
    BulkSyncWorkerEC2StatusCommandHandler,
)
from .collect_worker_cloudwatch_metrics_command import (
    CollectWorkerCloudWatchMetricsCommand,
    CollectWorkerCloudWatchMetricsCommandHandler,
)
from .create_cml_worker_command import CreateCMLWorkerCommand, CreateCMLWorkerCommandHandler
from .delete_cml_worker_command import DeleteCMLWorkerCommand, DeleteCMLWorkerCommandHandler
from .deregister_cml_worker_license_command import (
    DeregisterCMLWorkerLicenseCommand,
    DeregisterCMLWorkerLicenseCommandHandler,
)
from .detect_worker_idle_command import DetectWorkerIdleCommand, DetectWorkerIdleCommandHandler
from .disable_idle_detection_command import DisableIdleDetectionCommand, DisableIdleDetectionCommandHandler
from .enable_idle_detection_command import EnableIdleDetectionCommand, EnableIdleDetectionCommandHandler
from .enable_worker_detailed_monitoring_command import (
    EnableWorkerDetailedMonitoringCommand,
    EnableWorkerDetailedMonitoringCommandHandler,
)
from .import_cml_worker_command import ImportCMLWorkerCommand, ImportCMLWorkerCommandHandler
from .pause_worker_command import PauseWorkerCommand, PauseWorkerCommandHandler
from .refresh_worker_labs_command import RefreshWorkerLabsCommand, RefreshWorkerLabsCommandHandler
from .refresh_worker_metrics_command import RefreshWorkerMetricsCommand, RefreshWorkerMetricsCommandHandler
from .register_cml_worker_license_command import RegisterCMLWorkerLicenseCommand, RegisterCMLWorkerLicenseCommandHandler
from .request_worker_data_refresh_command import RequestWorkerDataRefreshCommand, RequestWorkerDataRefreshCommandHandler
from .start_cml_worker_command import StartCMLWorkerCommand, StartCMLWorkerCommandHandler
from .stop_cml_worker_command import StopCMLWorkerCommand, StopCMLWorkerCommandHandler
from .sync_worker_cml_data_command import SyncWorkerCMLDataCommand, SyncWorkerCMLDataCommandHandler
from .sync_worker_ec2_status_command import SyncWorkerEC2StatusCommand, SyncWorkerEC2StatusCommandHandler
from .terminate_cml_worker_command import TerminateCMLWorkerCommand, TerminateCMLWorkerCommandHandler
from .update_cml_worker_status_command import UpdateCMLWorkerStatusCommand, UpdateCMLWorkerStatusCommandHandler
from .update_cml_worker_tags_command import UpdateCMLWorkerTagsCommand, UpdateCMLWorkerTagsCommandHandler
from .update_worker_activity_command import UpdateWorkerActivityCommand, UpdateWorkerActivityCommandHandler

__all__ = [
    "BulkImportCMLWorkersCommand",
    "BulkImportCMLWorkersCommandHandler",
    "BulkImportResult",
    "BulkSyncWorkerCMLDataCommand",
    "BulkSyncWorkerCMLDataCommandHandler",
    "BulkSyncWorkerEC2StatusCommand",
    "BulkSyncWorkerEC2StatusCommandHandler",
    "BulkSyncResult",
    "CollectWorkerCloudWatchMetricsCommand",
    "CollectWorkerCloudWatchMetricsCommandHandler",
    "CreateCMLWorkerCommand",
    "CreateCMLWorkerCommandHandler",
    "DeleteCMLWorkerCommand",
    "DeleteCMLWorkerCommandHandler",
    "DeregisterCMLWorkerLicenseCommand",
    "DeregisterCMLWorkerLicenseCommandHandler",
    "DetectWorkerIdleCommand",
    "DetectWorkerIdleCommandHandler",
    "DisableIdleDetectionCommand",
    "DisableIdleDetectionCommandHandler",
    "EnableIdleDetectionCommand",
    "EnableIdleDetectionCommandHandler",
    "EnableWorkerDetailedMonitoringCommand",
    "EnableWorkerDetailedMonitoringCommandHandler",
    "ImportCMLWorkerCommand",
    "ImportCMLWorkerCommandHandler",
    "PauseWorkerCommand",
    "PauseWorkerCommandHandler",
    "RefreshWorkerLabsCommand",
    "RefreshWorkerLabsCommandHandler",
    "RefreshWorkerMetricsCommand",
    "RefreshWorkerMetricsCommandHandler",
    "RegisterCMLWorkerLicenseCommand",
    "RegisterCMLWorkerLicenseCommandHandler",
    "RequestWorkerDataRefreshCommand",
    "RequestWorkerDataRefreshCommandHandler",
    "StartCMLWorkerCommand",
    "StartCMLWorkerCommandHandler",
    "StopCMLWorkerCommand",
    "StopCMLWorkerCommandHandler",
    "SyncWorkerCMLDataCommand",
    "SyncWorkerCMLDataCommandHandler",
    "SyncWorkerEC2StatusCommand",
    "SyncWorkerEC2StatusCommandHandler",
    "TerminateCMLWorkerCommand",
    "TerminateCMLWorkerCommandHandler",
    "UpdateCMLWorkerStatusCommand",
    "UpdateCMLWorkerStatusCommandHandler",
    "UpdateCMLWorkerTagsCommand",
    "UpdateCMLWorkerTagsCommandHandler",
    "UpdateWorkerActivityCommand",
    "UpdateWorkerActivityCommandHandler",
]
