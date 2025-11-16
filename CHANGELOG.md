# Changelog

All notable changes to this project will be documented in this file.

The format follows the recommendations of Keep a Changelog (https://keepachangelog.com) and the project aims to follow Semantic Versioning (https://semver.org).

## [Unreleased]

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
