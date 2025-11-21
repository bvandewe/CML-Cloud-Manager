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
from .tasks_events import TaskCreatedDomainEventHandler
from .user_auth_events_handler import UserLoggedInDomainEventHandler

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
    # Lab record events
    "LabRecordCreatedDomainEventHandler",
    "LabRecordUpdatedDomainEventHandler",
    "LabStateChangedDomainEventHandler",
    # Task events
    "TaskCreatedDomainEventHandler",
]
