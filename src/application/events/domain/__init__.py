from .cml_worker_data_refresh_events import (
    WorkerDataRefreshCompletedEventHandler,
    WorkerDataRefreshRequestedEventHandler,
    WorkerDataRefreshSkippedEventHandler,
)
from .cml_worker_events import (
    CMLMetricsUpdatedDomainEventHandler,
    CMLWorkerCreatedDomainEventHandler,
    CMLWorkerImportedDomainEventHandler,
    CMLWorkerStatusUpdatedDomainEventHandler,
    CMLWorkerTelemetryUpdatedDomainEventHandler,
    CMLWorkerTerminatedDomainEventHandler,
)
from .cml_worker_license_events import (
    CMLWorkerLicenseDeregisteredEventHandler,
    CMLWorkerLicenseRegistrationCompletedEventHandler,
    CMLWorkerLicenseRegistrationFailedEventHandler,
    CMLWorkerLicenseRegistrationStartedEventHandler,
)
from .lab_record_events import (
    LabRecordCreatedDomainEventHandler,
    LabRecordUpdatedDomainEventHandler,
    LabStateChangedDomainEventHandler,
)
from .provision_cml_worker_event_handler import ProvisionCMLWorkerEventHandler
from .tasks_events import TaskCreatedDomainEventHandler
from .user_auth_events_handler import UserLoggedInDomainEventHandler
from .worker_activity_events_handler import (
    IdleDetectionToggledDomainEventHandler,
    WorkerActivityUpdatedDomainEventHandler,
    WorkerPausedDomainEventHandler,
    WorkerResumedDomainEventHandler,
)

__all__ = [
    # User auth events
    "UserLoggedInDomainEventHandler",
    # CML Worker events
    "CMLWorkerCreatedDomainEventHandler",
    "CMLWorkerImportedDomainEventHandler",
    "CMLWorkerStatusUpdatedDomainEventHandler",
    "CMLWorkerTerminatedDomainEventHandler",
    "CMLWorkerTelemetryUpdatedDomainEventHandler",
    "CMLMetricsUpdatedDomainEventHandler",
    # CML Worker license events
    "CMLWorkerLicenseRegistrationStartedEventHandler",
    "CMLWorkerLicenseRegistrationCompletedEventHandler",
    "CMLWorkerLicenseRegistrationFailedEventHandler",
    "CMLWorkerLicenseDeregisteredEventHandler",
    # Worker data refresh events
    "WorkerDataRefreshRequestedEventHandler",
    "WorkerDataRefreshSkippedEventHandler",
    "WorkerDataRefreshCompletedEventHandler",
    # Worker activity events
    "IdleDetectionToggledDomainEventHandler",
    "WorkerActivityUpdatedDomainEventHandler",
    "WorkerPausedDomainEventHandler",
    "WorkerResumedDomainEventHandler",
    # Lab record events
    "LabRecordCreatedDomainEventHandler",
    "LabRecordUpdatedDomainEventHandler",
    "LabStateChangedDomainEventHandler",
    # Task events
    "TaskCreatedDomainEventHandler",
    # Provisioning events
    "ProvisionCMLWorkerEventHandler",
]
