# Changelog

All notable changes to this project will be documented in this file.

The format follows the recommendations of Keep a Changelog (https://keepachangelog.com) and the project aims to follow Semantic Versioning (https://semver.org).

## [Unreleased]

### Added

- **Auto-Import Workers Background Job**: New recurrent job for automatically discovering and importing CML Workers
  - Runs at configurable intervals (default: 1 hour) via `AUTO_IMPORT_WORKERS_INTERVAL`
  - Searches AWS EC2 instances by AMI name pattern in specified region
  - Uses existing `BulkImportCMLWorkersCommand` for consistent import logic
  - Configurable via environment variables:
    - `AUTO_IMPORT_WORKERS_ENABLED` (default: false)
    - `AUTO_IMPORT_WORKERS_REGION` (default: us-east-1)
    - `AUTO_IMPORT_WORKERS_AMI_NAME` (AMI name pattern to search)
    - `AUTO_IMPORT_WORKERS_INTERVAL` (seconds, default: 3600)
  - Registered at boot alongside existing worker monitoring jobs
  - Non-intrusive: skips already-imported instances

- **Lab Operations Auto-Refresh**: Lab control commands (start/stop/wipe) now automatically schedule on-demand worker data refresh
  - Ensures worker metrics and lab states are updated after lab operations
  - Non-blocking: refresh scheduling failures don't affect lab operation success
  - Uses existing `OnDemandWorkerDataRefreshJob` infrastructure
  - Improves data consistency and real-time UI updates

### Changed

- **System View Scheduler Tab**: Improved job display clarity
  - Renamed "Function" column to "Command" for better understanding
  - Display actual job class name (e.g., "WorkerMetricsCollectionJob") instead of generic wrapper function
  - Makes it easier to identify which background job is scheduled
  - Applied same improvement to Worker Details modal Jobs tab

- **Import Organization**: Removed all inline imports from application layer (jobs, commands, queries, event handlers)
  - Moved 30+ inline imports to module level following Python PEP 8 best practices
  - Improved code readability with explicit dependency declarations at file start
  - Affected files: 21 commands, 2 jobs, 6 queries (29 files total)
  - Common patterns: `AwsRegion`, `CMLWorkerStatus`, `boto3`, service imports
  - Updated `.github/copilot-instructions.md` with comprehensive import guidelines
  - Benefits: Better maintainability, easier circular dependency detection, clearer for static analysis

- **Service Registration Patterns**: Unified DI registration patterns across all `application.services`
  - Standardized to `@staticmethod` decorator (removed `@classmethod`)
  - Consistent `implementation_factory=lambda` pattern for services with dependencies
  - All `configure()` methods now return `None` (builder modified in-place)
  - Added docstrings with Args sections for clarity
  - Unified log messages with ✅ emoji for consistency

### Removed

- **WorkerMetricsService**: Removed unnecessary service abstraction layer
  - Service was only used by `CollectWorkerCloudWatchMetricsCommand`
  - Command handler now contains CloudWatch metrics collection logic directly
  - Follows CQRS principles: handlers contain business logic, not delegating to services
  - Simplifies architecture by removing intermediate abstraction
  - Deleted: `application/services/worker_metrics_service.py`, `tests/application/test_worker_metrics_service.py`

### Fixed

- **Worker Metrics Display**: Fixed metrics display inconsistencies between views and SSE updates
  - **User cards view**: Added missing disk utilization progress bar (was only showing CPU/Memory)
  - **SSE real-time updates**: Both admin table and user cards now update when `worker.snapshot` SSE events arrive
  - **Metrics synchronization**: All three metrics (CPU, Memory, Disk) now stay in sync across landing page and modal
  - Worker cards now show individual progress bars for each metric that's available (no longer requires all three)
  - Simplified SSE handler: `worker.metrics.updated` event now only handles timing info, metrics updated via `worker.snapshot`

- **Worker Refresh Duplicates**: Fixed duplicate workers appearing after clicking refresh button
  - Added `workersData.length = 0` to clear array before populating with API response
  - Prevents accumulation of duplicate workers in both admin table and user card views
  - Ensures UI accurately reflects backend state on refresh

  - Affects: `SSEEventRelayHostedService`, `WorkerMetricsService`, `BackgroundTaskScheduler`
  - See: `notes/SERVICE_REGISTRATION_PATTERNS_UNIFIED.md`

### Fixed

- **Metrics Display Consistency**: Fixed inconsistent CPU/memory metrics between table and modal views
  - Unified data source: both views now use CML native telemetry (not CloudWatch)
  - SSE handler updates local cache directly instead of triggering full page reload
  - Added disk utilization to modal's Resource Utilization card (3-column layout)
  - Real-time metrics sync: table rows and modal update simultaneously on SSE events

- **WorkerMetricsService DI Registration**: Fixed factory function registration to properly inject service instances
  - Changed from `singleton=create_service` to positional `create_service` argument
  - Resolves AttributeError where handlers received factory function instead of service instance
  - Aligns with Neuroglia DI convention for lazy-initialized singletons

- **Countdown Timer Display**: Fixed stale timing data causing `--:--` display in worker details modal
  - Added validation to check if `next_refresh_at` is in the past before displaying
  - Automatically calculates fresh timing (`current_time + poll_interval`) when backend data is stale
  - Ensures countdown always shows valid future timestamp

### Added

#### Worker Metrics Architecture Refactoring

- **WorkerMetricsService**: Centralized service for collecting worker metrics from AWS
  - Extracts shared logic from command handler and background job (eliminated 90% code duplication)
  - Single source of truth for EC2 status checks and CloudWatch metrics collection
  - Returns `MetricsResult` with collected data and update status
  - Clear separation: service handles logic, command/job handle orchestration

- **Focused Command Split**: Refactored monolithic `RefreshWorkerMetricsCommand` into focused commands
  - `SyncWorkerEC2StatusCommand`: Synchronizes worker status with EC2 instance state (218 lines)
  - `CollectWorkerCloudWatchMetricsCommand`: Collects CPU/memory metrics from CloudWatch (80 lines)
  - `SyncWorkerCMLDataCommand`: Synchronizes CML service data and lab information (234 lines)
  - `BulkSyncWorkerEC2StatusCommand`: Concurrent EC2 status sync for multiple workers
  - `BulkSyncWorkerCMLDataCommand`: Concurrent CML data sync for multiple workers
  - Each command <250 lines, testable independently, follows Single Responsibility Principle

- **Concurrent Background Job Processing**: Worker metrics collection now processes workers in parallel
  - Uses `asyncio.gather()` with `Semaphore(10)` for rate-limited concurrent AWS API calls
  - 10x faster metrics refresh (200s → 20s for 100 workers)
  - Batch database updates via new `update_many_async()` repository method
  - Reduces database operations from 100 to 1 per collection cycle

- **Batch Repository Operations**: Added `update_many_async()` to worker repository
  - MongoDB `bulk_write` for efficient batch updates
  - Abstract method in `CMLWorkerRepository` interface
  - Implementation in `MongoCMLWorkerRepository` with domain event publishing
  - 100x reduction in database round-trips for background jobs

- **Background Jobs Simplification**: Removed BackgroundJobsInitializer abstraction layer
  - Jobs now self-configure intervals via decorator parameters: `@backgroundjob(task_type="recurrent", interval=300)`
  - BackgroundTaskScheduler auto-discovers jobs from configured modules
  - Index creation moved to `LabsRefreshJob.configure()` method
  - Eliminated 133 lines of unnecessary initialization code
  - Jobs declare configuration explicitly at class definition

- **System Monitoring UI Cleanup**: Removed obsolete "Collectors" tab
  - Consolidated monitoring information into Scheduler and Monitoring tabs
  - Updated card layout from 4 to 3 columns for better visual balance
  - Removed redundant collector-specific endpoints and logic
  - Clearer separation: Scheduler shows jobs, Monitoring shows worker-level status

### Changed

- **Settings Configuration**: Improved logging and APScheduler job store defaults
  - Added file handler support (optional, for local development)
  - Configurable third-party logger levels (uvicorn, fastapi, pymongo, httpx, asyncio)
  - Switched default job store from MongoDB to Redis (separate DB from session store)
  - Cleaned up security group validation logic (moved to field_validator pattern)

- **Module Scanning**: Background job scheduler now scans `application.jobs` module
  - Changed from `application.services` to `application.jobs` for clearer separation
  - Job wrappers dynamically retrieve configured modules from settings
  - Fallback mechanism for backward compatibility

- **Job Registration**: Enhanced `@backgroundjob` decorator with explicit parameters
  - Accepts `interval` (seconds) and `scheduled_at` (datetime) parameters
  - More explicit and self-documenting than class attributes
  - Better IDE support with type hints
  - Example: `@backgroundjob(task_type="recurrent", interval=app_settings.worker_metrics_poll_interval)`

### Fixed

- **Background Job Module Scanning**: Fixed job registration bug where wrappers scanned wrong module
  - Wrappers now retrieve modules from `BackgroundTaskSchedulerOptions` via service provider
  - Added fallback to default modules if service provider unavailable
  - Proper error handling with debug logging for module loading failures

- **System Controller**: Updated to use `BackgroundTaskScheduler` singleton instead of removed initializer
  - Removed references to `_background_jobs_initializer` global variable
  - Uses service provider pattern: `self.service_provider.get_required_service(BackgroundTaskScheduler)`

- **Dead Code Removal**: Cleaned up obsolete `WorkerMonitoringScheduler` references
  - Removed from event handlers, command handlers, and controller dependencies
  - Simplified dependency injection with fewer obsolete parameters

### Removed

- **BackgroundJobsInitializer**: Deleted 133-line HostedService abstraction
  - Unnecessary layer - BackgroundTaskScheduler already handles job discovery and scheduling
  - Jobs self-configure via decorator parameters and `configure()` methods
  - See `notes/BACKGROUND_JOBS_INITIALIZER_REMOVAL.md` for migration guide

#### Delete Worker Command with Optional EC2 Termination

- **Delete Worker Command**: New `DeleteCMLWorkerCommand` to remove workers from the database with optional EC2 termination
  - Deletes worker record from local database
  - Optional `terminate_instance` flag to also terminate the EC2 instance before deletion
  - Properly marks worker as terminated before deletion (publishes domain events)
  - Graceful handling if EC2 instance not found (logs warning, continues with deletion)
  - Prevents deletion if EC2 termination requested but fails (protects against orphaned instances)
  - Supports audit trail with `deleted_by` user tracking
  - Full OpenTelemetry tracing coverage (retrieve, terminate, mark terminated, delete)
- **API Endpoint**: New `DeleteCMLWorkerRequest` model and updated DELETE endpoint
  - `DELETE /api/workers/region/{region}/workers/{worker_id}` with request body
  - Request body includes `terminate_instance` boolean flag (default: false)
  - **Admin-only access**: Requires `admin` role (stricter than previous `lablets-admin`)
  - Returns success/error with detailed messages
- **UI Delete Modal**: New confirmation modal with terminate option
  - Prominent warning about irreversible action
  - Checkbox to optionally terminate EC2 instance
  - Clear explanations of single vs. dual deletion (database only vs. database + EC2)
  - Admin-only visibility (button hidden for non-admin users)
  - Delete button accessible from Worker Details modal footer
  - Delete button available in admin table view action buttons
- **Admin Table Interaction**: Table rows now clickable to open worker details modal
  - Clicking anywhere on a row opens the worker details modal (consistent with card view)
  - Action buttons use event.stopPropagation() to prevent triggering row click
  - Maintains all existing button functionality (Start, Stop, License, Delete)
  - Replaces previous simple terminate confirmation with comprehensive modal
  - **Delete button in Worker Details modal footer**: Delete Worker button added to the footer of the Worker Details modal
    - Positioned on the left side, separated from Refresh and Close buttons
    - Opens the Delete Worker modal when clicked

#### Dark Theme Support

- **Native Bootstrap Theme Switcher**: Toggle between light and dark themes
  - Theme toggle button in navbar with moon/sun icon
  - Dark theme: pure white text on black background
  - Light theme: standard black text on white background (Bootstrap default)
  - Theme preference persisted in localStorage
  - Applies Bootstrap's `data-bs-theme` attribute for native dark mode
  - Custom CSS overrides for cards, tables, modals, and form controls

#### Metrics Refresh Countdown Timer

- **Worker Details Modal Timer**: Real-time countdown showing when next metrics refresh will occur
  - Displays in modal header on the right side (format: `M:SS`)
  - Updates every second to show remaining time until next scheduled metrics collection
  - **Backend provides scheduling info**: SSE events now include `poll_interval` and `next_refresh_at` fields
  - **Per-worker localStorage tracking**: UI stores timing info per worker in localStorage
  - Timer persists across modal close/reopen - remembers last known refresh time
  - Automatically updates when metrics are collected via SSE event
  - Uses actual APScheduler job next_run_time from backend (not client-side estimation)
  - Supports per-worker configurable poll intervals (future admin feature ready)
  - Timer stops when modal is closed to prevent unnecessary background activity
  - Provides visual feedback about background monitoring system activity
  - Icon changes based on current theme (moon for light mode, sun for dark mode)
    - Pre-fills modal with current worker's information
    - Admin-only visibility (hidden for non-admin users)
- **Admin-Only Controls**: Delete functionality restricted to administrators
  - Delete button uses `admin-only` CSS class and hidden by default
  - Role checking in JavaScript (`isAdmin()`) before showing modal
  - Backend enforces `admin` role via `require_roles("admin")` dependency
  - Permission denied toast messages for unauthorized attempts
- **Comprehensive Test Coverage**: Full unit test suite for delete command
  - Tests delete without termination, delete with termination
  - Tests handling of missing workers, missing instances
  - Tests error conditions (termination failures, database failures)
  - Tests worker state transitions (marking as terminated)

#### Bulk Import EC2 Instances

- **Bulk Import Command**: New `BulkImportCMLWorkersCommand` to import all matching EC2 instances at once
  - Discovers all instances matching AMI ID or AMI name pattern in specified region
  - Automatically filters out instances already registered as workers
  - Returns detailed result with imported/skipped counts and reasons
  - Supports same AMI search criteria as single import (ami_id, ami_name)
- **Enhanced Import Request Model**: Added `import_all` flag to `ImportCMLWorkerRequest`
  - Set `import_all=true` to trigger bulk import behavior
  - Controller automatically routes to appropriate command handler
  - Validation ensures bulk import only works with AMI criteria (not instance_id)
- **UI Bulk Import Support**: Import Worker modal now includes bulk import option
  - Checkbox "Import all matching instances (bulk import)" enabled by default for AMI-based imports
  - Dynamic help text explains single vs. bulk import behavior
  - Worker name field automatically disabled during bulk import (not applicable)
  - Success toast shows detailed results: "X worker(s) imported, Y skipped"
  - Seamless switching between single and bulk import modes
- **Comprehensive Result Tracking**: `BulkImportResult` dataclass provides:
  - List of successfully imported workers with full details
  - List of skipped instances with instance IDs and skip reasons
  - Total counts: found, imported, and skipped
- **Efficient Duplicate Detection**: Single query to fetch all existing workers, filters in-memory
- **Detailed Logging**: Progress indicators for each import operation (✅ success, ⏭️ skipped)
- **OpenTelemetry Tracing**: Full span coverage for bulk operations (discover, filter, import)
- **Test Coverage**: Comprehensive unit tests for bulk import scenarios

### Fixed

#### SSE Event Relay Dependency Injection Refactoring

- **Removed Global State**: Eliminated `get_sse_relay()` global function and `_sse_relay_instance` global variable
- **Proper DI Pattern**: `SSEEventRelay` now registered as singleton and injected via constructor dependencies
  - Domain event handlers (`CMLWorker*DomainEventHandler`) receive `SSEEventRelay` via constructor
  - Command handlers (`RefreshWorkerLabsCommandHandler`, `RefreshWorkerMetricsCommandHandler`) receive via DI
  - Controllers (`EventsController`) resolve from `service_provider.get_required_service(SSEEventRelay)`
- **Consistent Architecture**: Follows same DI pattern as other services (CloudEventBus, repositories, etc.)
- **Better Testability**: SSE relay can be mocked/replaced in tests without global state manipulation

#### Worker Monitoring Job Cleanup on Termination

- **Background Job Cleanup**: Fixed issue where metrics collection jobs continued running for terminated workers
  - `CMLWorkerTerminatedDomainEventHandler` now receives `WorkerMonitoringScheduler` via dependency injection
  - Handler stops monitoring job when worker terminates by calling `stop_monitoring_worker_async()`
  - Scheduler registered as singleton in service provider and injected into lifespan startup
  - Jobs are properly unscheduled when termination event fires, preventing continuous error logs
  - Graceful degradation if scheduler unavailable (monitoring disabled scenario)
  - Follows proper DI pattern instead of using global variables

### Added

#### AMI Information Display & Tracking

- **Enhanced AMI Metadata**: Workers now store and display comprehensive Amazon Machine Image (AMI) information
  - Backend automatically retrieves AMI details from AWS including name, description, and creation date
  - New fields in `CMLWorkerState`: `ami_description`, `ami_creation_date`
  - `get_ami_details()` method in `AwsEc2Client` queries AWS `describe_images` API
  - Domain events updated: `CMLWorkerCreatedDomainEvent`, `CMLWorkerImportedDomainEvent`, `EC2InstanceDetailsUpdatedDomainEvent`
- **UI AMI Information Section**: New dedicated section in worker details modal (AWS tab)
  - Displays AMI ID, Name, Description, and Creation Date
  - Positioned above Network section for better visibility
  - Formatted with proper date/time display and code formatting for AMI IDs
- **Automatic Population**: AMI details fetched during worker creation, import, and metrics refresh operations

#### AI Agent Documentation Integration

- **Comprehensive AI Agent Guide**: Created `.github/copilot-instructions.md` with detailed instructions for AI coding agents (GitHub Copilot, Cursor, Cline, etc.)
  - Architecture overview: Multi-SubApp pattern, layer architecture, self-contained CQRS
  - Critical domain concepts: CMLWorker aggregate, lab management, worker monitoring system
  - Authentication architecture: Dual auth (cookie + bearer), BFF pattern, RBAC enforcement
  - Development workflows: Essential Makefile commands, local vs Docker development
  - Neuroglia framework specifics: DI patterns, controller routing, CQRS/Mediator, event sourcing
  - AWS integration: EC2/CloudWatch client, required environment variables
  - Common pitfalls: Gotchas specific to this codebase
  - Architecture evolution: Migration path to hybrid ROA model
  - Code style & contribution guidelines: Commit conventions, pre-commit hooks, documentation requirements
- **MkDocs Integration**: Added `docs/development/ai-agent-guide.md` that automatically includes `.github/copilot-instructions.md` via PyMdown Snippets
  - Single source of truth maintained in `.github/copilot-instructions.md`
  - Automatic sync to documentation site on every build
  - Added to Development section in MkDocs navigation
  - Cross-referenced in `docs/index.md` and `README.md`
  - Useful for both AI agents and human developers (onboarding/reference)

#### Real-Time SSE Updates & Labs Visibility

- **Server-Sent Events (SSE) Stream**: New endpoint `/api/events/stream` delivering real-time worker lifecycle, metrics, labs, and status updates to the UI.
  - Initial connection + heartbeat every 30s for connection health.
  - Graceful shutdown event `system.sse.shutdown` on application stop.
- **Domain Event Broadcasting**: Added handlers (`cml_worker_events.py`) mapping domain events to SSE types:
  - `worker.created`, `worker.status.updated`, `worker.terminated`, `worker.metrics.updated` (telemetry), `worker.labs.updated` (command/job driven)
- **Labs Refresh Job Visibility**: Global recurrent job `labs-refresh-global` now appears in scheduler listings; executes every 30 minutes and once at startup.
- **Frontend SSE Client**: Robust auto-reconnecting client (`sse-client.js`) with exponential backoff, status callbacks (`connected`, `reconnecting`, `disconnected`, `error`).
  - Central badge indicator added to Workers view (`Realtime: <status>`).
  - Automatic UI refresh of worker tables/cards, open details modal, and Labs tab when relevant events arrive.
  - **Graceful connection lifecycle**: Closes SSE connections cleanly on page unload/refresh, preventing stale connections.
  - **Page visibility handling**: Maintains connection when tab is hidden, auto-reconnects when tab becomes visible.
  - **Mobile-friendly**: Handles freeze/resume events for mobile browser backgrounding.
- **Hosted Relay Service**: `SSEEventRelayHostedService` registered in application lifecycle providing structured start/stop and future extensibility for cleanup/backpressure features.
- **Extensible Event Model**: Simple relay abstraction allows adding new event types by broadcasting via `get_sse_relay().broadcast_event(...)` in commands or handlers.

#### Documentation Enhancements (in progress)

- Preparing updates across README and MkDocs site to cover real-time updates, role-specific onboarding, and background processing.

#### Lab Records and CQRS Pattern

- **Lab Record Aggregate**: Event-sourced tracking of CML labs
  - Lab metadata: title, description, state, owner, node/link counts
  - Operation history: max 50 entries tracking state changes
  - Domain events: `LabRecordCreatedDomainEvent`, `LabRecordUpdatedDomainEvent`, `LabStateChangedDomainEvent`
  - MongoDB repository with worker_id+lab_id indexing
  - Consistent event dispatch pattern using `multipledispatch.dispatch`

- **CQRS Implementation for Labs**:
  - **GetWorkerLabsQuery**: Read-only query for fetching labs from database
    - Fast cached reads from `lab_records` collection
    - Returns labs with last_synced timestamp
    - Proper QueryHandler base class usage (instance methods)
  - **RefreshWorkerLabsCommand**: Write operation for on-demand CML sync
    - Fetches labs from CML API for specific worker
    - Creates/updates lab records with change detection
    - Lenient status validation (warns if not RUNNING)
    - Returns summary: labs_synced, labs_created, labs_updated

- **Labs Background Refresh**:
  - **LabsRefreshJob**: Global 30-minute refresh cycle
  - Processes all RUNNING workers with https_endpoint
  - Runs at startup and periodically
  - Updates lab_records collection for all workers

- **UI Labs Integration**:
  - Labs tab in worker details modal
  - Refresh button triggers both metrics and labs refresh
  - Visual feedback with warning toasts on failures
  - Real-time lab state display with operation history

### Added

#### Worker Metrics Source Separation

- **Multi-Source Metrics Architecture**: Clear separation of metrics by data source
  - **EC2 Metrics**: Instance health checks from AWS EC2 API (`ec2_instance_state_detail`, `ec2_system_status_check`, `ec2_last_checked_at`)
  - **CloudWatch Metrics**: Resource utilization from AWS CloudWatch (`cloudwatch_cpu_utilization`, `cloudwatch_memory_utilization`, `cloudwatch_last_collected_at`, `cloudwatch_detailed_monitoring_enabled`)
  - **CML Metrics**: Application metrics from CML API (`cml_system_info`, `cml_ready`, `cml_uptime_seconds`, `cml_labs_count`, `cml_last_synced_at`)
  - Domain events for each source: `EC2MetricsUpdatedDomainEvent`, `CloudWatchMetricsUpdatedDomainEvent`, `CMLMetricsUpdatedDomainEvent`
  - Aggregate methods: `update_ec2_metrics()`, `update_cloudwatch_metrics()`, `update_cml_metrics()`
  - Backward compatibility maintained with deprecated `update_telemetry()` method

#### CML API Integration

- **CMLApiClient**: Async REST API client for querying CML instances
  - **JWT Authentication**: POST `/api/v0/authenticate` with username/password
  - **Token Management**: Automatic token caching and refresh on expiration
  - **System Stats**: `/api/v0/system_stats` endpoint integration
  - **Metrics Parsing**: Compute nodes, dominfo, CPU/memory/disk statistics
  - **Workload Metrics**: Allocated CPUs, running nodes, total nodes from dominfo
  - **Error Handling**: Graceful handling for unreachable instances
  - **SSL Support**: SSL verification configurable (disabled for self-signed certs)
  - **Async/Await**: Fully async implementation using httpx

#### Command Pattern Implementation

- **RefreshWorkerMetricsCommand**: CQRS-compliant metrics refresh
  - Orchestrates EC2, CloudWatch, and CML data collection
  - Updates worker aggregate state (triggers domain events)
  - Updates OpenTelemetry gauges after each refresh
  - Handles failures gracefully per data source
  - Respects worker status (only queries CML when RUNNING+AVAILABLE)

- **EnableWorkerDetailedMonitoringCommand**: Admin command for 1-minute metrics
  - Enables detailed CloudWatch monitoring via AWS API
  - Updates worker aggregate with monitoring status
  - POST `/region/{region}/workers/{id}/monitoring` endpoint (admin-only)
  - Cost: ~$2.10/month per instance

#### Configuration

- **CML API Settings**:
  - `cml_worker_api_username`: CML API username for system stats (default: "admin")
  - `cml_worker_api_password`: CML API password (change in production)

#### Documentation

- `notes/WORKER_METRICS_SOURCE_SEPARATION.md`: Architecture guide for metric sources
- `notes/REFRESH_WORKER_METRICS_IMPLEMENTATION_PLAN.md`: Implementation roadmap and phases
- `notes/METRICS_STORAGE_ARCHITECTURE.md`: Analysis of metrics storage options (time-series collections, external DBs)
- `notes/CML_API_TESTING.md`: Testing guide for CML API client with endpoint reference and troubleshooting

#### Testing & Development Tools

- `scripts/test_cml_api.py`: Comprehensive test script for CML API client
  - Test specific HTTPS endpoints with authentication
  - Test by worker ID (database lookup)
  - Test all RUNNING workers in parallel
  - MongoDB integration for worker discovery
  - Detailed logging and error reporting

#### Decision Log

- **Custom CML API Client vs Official Library**: Chose custom implementation
  - Official `virl2-client` library is sync (our architecture is async)
  - We only need `system_stats` endpoint (library has 50+ methods)
  - Custom implementation: lightweight, async, fits architecture perfectly
  - Future: Can integrate official library for advanced features if needed

### Changed

- **Monitoring Status Tracking**: AWS EC2 API now returns `monitoring_state` field
  - `get_instance_status_checks()` includes CloudWatch monitoring status
  - RefreshWorkerMetricsCommand syncs monitoring status from AWS
  - New instances created with detailed monitoring enabled by default

#### Background Task Scheduling System

- **APScheduler Integration**: Distributed task scheduling with Redis/MongoDB persistence
  - `BackgroundTaskScheduler`: Core scheduler with automatic job discovery via `@backgroundjob` decorator
  - `BackgroundTasksBus`: Message bus for task scheduling and coordination
  - `RecurrentBackgroundJob` and `ScheduledBackgroundJob`: Base classes for periodic and one-time jobs
  - Dependency injection pattern: Jobs serialize minimal data, dependencies re-injected on deserialization
  - Automatic job recovery after application restarts
  - Support for both Redis and MongoDB job stores

#### Worker Monitoring System

- **Automated Worker Monitoring**: Background monitoring of CML Worker health and metrics
  - `WorkerMetricsCollectionJob`: Recurrent job for collecting AWS EC2 and CloudWatch metrics
  - `WorkerMonitoringScheduler`: Orchestrates monitoring job lifecycle for all active workers
  - `WorkerNotificationHandler`: Reactive observer for processing metrics events and threshold alerts
  - Auto-discovery of active workers on application startup
  - Graceful job termination when workers are deleted
  - CPU and memory utilization threshold monitoring (default: 90%)
  - OpenTelemetry integration for observability

#### Worker Management Features

- **AMI Name Support**: Workers can be created and imported using human-readable AMI names
  - `cml_worker_ami_name_default` setting for default AMI
  - `cml_worker_ami_names` dictionary mapping names to AMI IDs
  - AMI name stored in worker state for auditing
  - AMI name included in worker domain events

- **Worker Refresh Endpoint**: Manual worker state synchronization and monitoring restart
  - POST `/region/{aws_region}/workers/{worker_id}/refresh` endpoint
  - Triggers immediate metrics collection from AWS EC2/CloudWatch
  - Updates worker state in database with current AWS data (emits domain events on changes)
  - Automatically starts monitoring if worker is running/pending and not monitored
  - Returns refreshed worker details to UI
  - Refresh button in Worker Details modal with loading state and notifications
  - Comprehensive error handling and user feedback

#### Configuration

- **Worker Monitoring Settings**:
  - `worker_monitoring_enabled`: Enable/disable automated monitoring (default: true)
  - `worker_metrics_poll_interval`: Metrics collection interval in seconds (default: 300)
  - `worker_notification_webhooks`: List of webhook URLs for alerts (placeholder)

- **Background Job Store Settings**:
  - `background_job_store`: Redis or MongoDB configuration for job persistence
  - Separate Redis database for job storage (DB 1) vs sessions (DB 0)

#### Documentation

- **Architecture Documentation**:
  - `docs/architecture/background-scheduling.md`: Comprehensive guide to background task system
  - `docs/architecture/worker-monitoring.md`: Worker monitoring system architecture and usage
  - Updated README.md with new features and expanded project structure
  - Updated mkdocs.yml navigation to include new documentation pages

#### Design Notes

- `notes/APSCHEDULER_IMPROVEMENTS_COMPLETE.md`: Phase 2 implementation details and recommendations
- `notes/APSCHEDULER_REFACTORING_SUMMARY.md`: Phase 1 summary and architectural decisions
- `notes/WORKER_MONITORING_ARCHITECTURE.md`: Reactive monitoring architecture design
- `notes/ROA_MIGRATION_PLAN.md`: Future Resource-Oriented Architecture (ROA) migration plan
- `notes/WORKER_REFRESH_IMPLEMENTATION.md`: Worker refresh feature implementation details and known issues

#### UI/Frontend Utilities

- **Role-based Access Control**: New `src/ui/src/scripts/utils/roles.js` module
  - `getUserRoles()`, `hasRole()`, `hasAnyRole()`, `hasAllRoles()` utility functions
  - `isAdmin()`, `isManager()`, `isAdminOrManager()` convenience functions
  - Centralized role checking logic for frontend components

### Changed

#### Backend

- Refactored authentication middleware configuration by moving detailed setup code from `main.py` to `DualAuthService.configure_middleware()` helper method for better separation of concerns and maintainability.
- Updated import statements formatting for improved code readability (multi-line imports consolidated).
- Enhanced `main.py` with worker monitoring configuration during application startup
- Added lifecycle hooks for background task scheduler and worker monitoring
- Improved `WorkerMetricsCollectionJob` pickle serialization with `__getstate__` and `__setstate__` methods
- Enhanced job configuration with proper dependency injection pattern

#### UI/Frontend

- Enhanced Worker Details modal with improved refresh functionality
- Added loading states and visual feedback for async operations
- Improved role-based access control checks in workers UI
- Enhanced system monitoring display with better data formatting
- Updated navbar to properly display user information and roles

#### Dependencies

- Updated `neuroglia-python` from 0.6.6 to 0.6.7 (later updated to 0.6.8)
- Added `apscheduler = "^3.11.1"` for background task scheduling

### Fixed

- **APScheduler Pickle Serialization**: Fixed "Can't pickle local object" errors preventing background job persistence
  - Modified job wrappers to accept only serializable parameters (task_type_name, task_id, task_data)
  - Job wrappers reconstruct task objects from minimal data using service provider
  - Eliminated unpicklable references (JsonSerializer lambdas) from job arguments
  - Enables Redis/MongoDB job stores to persist scheduled and recurrent jobs successfully

- **Enhanced Worker Refresh**: Refresh endpoint now triggers immediate metrics collection
  - Creates and executes WorkerMetricsCollectionJob instance on-demand
  - Collects EC2 status and CloudWatch metrics instantly
  - Worker aggregate emits domain events for any state changes (status, IP, telemetry)
  - Domain event handlers can react asynchronously to worker updates
  - Ensures monitoring scheduler tracks worker after refresh

- Fixed dependency injection for authentication middleware to properly resolve service provider
- Fixed configuration issues in CI workflow for Git LFS checkout to ensure GitHub Pages deployment includes LFS assets
- Fixed Bandit security scanner configuration to skip test directories and B101 (assert_used) check, eliminating 155 false positive warnings
- Fixed job serialization to store only minimal data (worker_id), avoiding non-serializable dependencies
- Fixed job stop implementation in `WorkerMonitoringScheduler` to properly call APScheduler's remove_job
- Fixed job state validation to check for terminated workers and raise exceptions to stop jobs gracefully

---

## [0.1.0] - 2025-11-11

### Added

#### Testing Infrastructure

- Comprehensive test suite with 60 tests achieving 98% coverage across domain, infrastructure, and application layers.
- pytest.ini configuration with custom markers (unit, integration, asyncio, auth, repository, command, query, slow, smoke).
- Test fixtures package with factories for Task, Token, and Session data generation.
- Test mixins providing reusable patterns: AsyncTestMixin, AssertionMixin, MockHelperMixin, SessionTestMixin.
- Domain layer tests (18 tests) validating Task entity behavior and domain events.
- Infrastructure tests (11 tests) for InMemorySessionStore and RedisSessionStore.
- Application layer tests (31 tests) for command handlers (create, update, delete) and query handlers (get tasks, get by id).
- Testing documentation at `docs/development/testing.md` with examples and best practices.

#### Documentation

- Security section (renamed from Authentication) with comprehensive authorization guide covering OAuth2/OIDC, BFF pattern, and RBAC.
- Observability documentation split into 8 focused documents:
  - Overview: High-level introduction and navigation hub (234 lines).
  - Architecture: Technical components, data flow, and diagrams (300 lines).
  - Getting Started: Quick start guide with 4 complete workflows (379 lines).
  - Configuration: Environment variables, OTEL Collector, and backend setup (489 lines).
  - Best Practices: Naming conventions, cardinality control, sampling strategies (558 lines).
  - Troubleshooting: Common issues and solutions with diagnosis steps (616 lines).
  - Metrics Instrumentation: Complete guide to all metric types with real code examples (918 lines).
  - Tracing Instrumentation: Distributed tracing patterns and context propagation (997 lines).
- GitHub Pages setup documentation for MkDocs deployment.
- Makefile reference guide.

#### Frontend Components

- Modular UI component structure in `src/ui/src/scripts/components/`:
  - `dashboard.js`: Task loading, CRUD operations, and workflow orchestration.
  - `modals.js`: Alert, confirm, and toast notification utilities.
  - `permissions.js`: Role-based access control helpers.
  - `task-card.js`: Card rendering with markdown support and collapsible behavior.
- Component-specific SCSS stylesheets in `src/ui/src/styles/components/`.
- Reusable Jinja2 template components in `src/ui/src/templates/components/`.
- Task editing UI with role-based field permissions:
  - Regular users: Edit title, description, status, priority.
  - Managers: Additional assignee assignment capability.
  - Admins: Full access including department field.
- Edit modal with markdown-enabled textarea and success toast notifications.
- Task card collapsible interface with toggle behavior and markdown rendering.
- Task card action icons (edit, info, delete) with Bootstrap tooltips.

#### Configuration

- `.vscode/copilot-context.md` instructions to guide AI agents on backend, frontend, documentation, and git practices.

### Changed

#### Backend

- Task entity methods updated to use aggregate root pattern instead of direct state manipulation.
- UpdateTaskCommand now properly emits domain events through aggregate methods.
- Task entity removed attribute delegation for cleaner separation of concerns.
- Department field support added to update command and API controllers.

#### Frontend

- UI codebase reorganized into modular component structure.
- Task cards now display assignee and department information.
- Improved card layout with proper collapsed/expanded states.
- Enhanced modal dialogs with scrollable content and better form visibility.

#### Documentation

- Authentication section renamed to Security for broader scope.
- Authorization Code Flow diagram corrected to show Backend-for-Frontend (BFF) pattern.
- Observability documentation backend tools updated from Jaeger to Tempo and Console Exporter to Prometheus.
- MkDocs navigation restructured with 8 organized observability entries.

#### Configuration

- Disabled automatic YAML formatting in the workspace to respect yamllint comment-spacing requirements.
- Increased the yamllint line-length limit to 250 characters to accommodate long Docker Compose entries.

### Fixed

- Task card toggle behavior now correctly uses `.task-header` class for header selection.
- Edit modal properly pre-fills all task fields including assignee and department.
- Role-based field visibility in edit modal working correctly (assignee for managers+, department for admins only).
- Domain events now properly emitted for all task updates.

### Security

- Uvicorn now binds to `127.0.0.1` by default; override via `APP_HOST` when exposing the service deliberately.
- RBAC enforcement in update command handler: users can only edit their own tasks, admins can edit any task.
- Permission checks in UI: edit/delete buttons only shown to authorized users.


---

## [0.1.0] - 2025-11-07

### Added

- Multi sub-app FastAPI architecture (API at `/api`, UI root) using Neuroglia patterns.
- OAuth2/OIDC integration with Keycloak (Authorization Code flow) and refresh endpoint `/api/auth/refresh`.
- RS256 JWT verification via JWKS with issuer and audience validation.
- Dual security schemes (OAuth2 Authorization Code + HTTP Bearer) in OpenAPI spec.
- Auto-refresh logic for access tokens with leeway configuration.
- Explicit expired token handling returning `401` with `WWW-Authenticate` header.
- Redis session store option (configurable backend) plus in-memory fallback.
- CQRS layer: commands (`create_task`, `update_task`), queries (`get_tasks`) and RBAC enforcement handlers.
- Observability metrics scaffold (`observability/metrics.py`).
- Project rename script `scripts/rename_project.py` supporting variant styles & dry-run.
- Rebranding documentation (README section) and rename integrity test.
- CONTRIBUTING guide with DCO sign-off instructions.
- Pull request template enforcing checklist & DCO sign-off.
- Apache 2.0 License adoption and README license section.

### Changed

- OpenAPI configuration upgraded to correctly apply security schemes to protected endpoints.
- README expanded with detailed project structure and template usage guidance.

### Fixed

- Missing Authorization header in Swagger UI by correcting scheme definitions.
- Legacy HS256 secret decoding replaced with proper RS256 JWKS verification.
- Markdown formatting issues in README and CONTRIBUTING (lists & fenced block spacing).

### Security

- Migration from HS256 static secret to RS256 with remote JWKS caching.
- Added issuer/audience claim validation toggles.
- Improved expired token feedback via standards-compliant `WWW-Authenticate` header.

### Removed

- Deprecated reliance on `JWT_SECRET_KEY` for RS256 tokens (retained only as legacy fallback context).

---

[0.1.0]: https://github.com/your-org/your-repo/releases/tag/v0.1.0
