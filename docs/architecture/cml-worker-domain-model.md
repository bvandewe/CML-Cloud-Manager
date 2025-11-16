# CML Worker Domain Model

## Overview

The **CML Worker** is a domain aggregate that represents an AWS EC2 instance running Cisco Modeling Lab (CML). It encapsulates the complete lifecycle, state management, and operational characteristics of a CML instance.

## Domain Structure

### Entity: `CMLWorker`

**Location**: `src/domain/entities/cml_worker.py`

The `CMLWorker` aggregate follows the Neuroglia `AggregateState` pattern with event sourcing.

#### Key Attributes

**Identity & Infrastructure**

- `id`: Unique worker identifier (UUID)
- `name`: Human-readable name
- `aws_region`: AWS region (e.g., "us-east-1")
- `aws_instance_id`: EC2 instance ID
- `instance_type`: EC2 instance type (e.g., "t3.xlarge")
- `ami_id`: AWS AMI ID to create instance from (e.g., "ami-0123456789abcdef0")
- `ami_name`: Human-readable AMI name (e.g., "CML-2.7.0-Ubuntu-22.04")

**State Management**

- `status`: EC2 instance status (CMLWorkerStatus enum)
- `service_status`: CML HTTPS service availability (CMLServiceStatus enum)

**CML Integration**

- `cml_version`: Installed CML version
- `license_status`: License registration status (LicenseStatus enum)
- `license_token`: License registration key
- `https_endpoint`: HTTPS URL for CML access

**Networking**

- `public_ip`: Public IP address
- `private_ip`: Private IP address

**Telemetry & Monitoring**

- `last_activity_at`: Last detected activity timestamp
- `active_labs_count`: Number of active labs
- `cpu_utilization`: CPU usage percentage (0-100)
- `memory_utilization`: Memory usage percentage (0-100)

**Audit Trail**

- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `terminated_at`: Termination timestamp
- `created_by`: User ID who created the worker
- `terminated_by`: User ID who terminated the worker

### Enums

**Location**: `src/domain/enums.py`

#### CMLWorkerStatus

Represents EC2 instance states:

- `PENDING`: Instance being launched
- `RUNNING`: Instance is running
- `STOPPING`: Instance being stopped
- `STOPPED`: Instance is stopped
- `SHUTTING_DOWN`: Instance being terminated
- `TERMINATED`: Instance is terminated
- `UNKNOWN`: Status cannot be determined

#### CMLServiceStatus

Represents CML HTTPS service availability:

- `UNAVAILABLE`: Service not accessible
- `STARTING`: Service starting up
- `AVAILABLE`: Service accessible via HTTPS
- `ERROR`: Service encountered an error

#### LicenseStatus

Represents CML license state:

- `UNREGISTERED`: No license registered
- `REGISTERED`: Valid license active
- `EVALUATION`: Evaluation license active
- `EXPIRED`: License has expired
- `INVALID`: License is invalid

### Domain Events

**Location**: `src/domain/events/cml_worker.py`

All events are decorated with `@cloudevent` for CloudEvents compliance.

#### CMLWorkerCreatedDomainEvent

Raised when a new worker is created.

**Fields**: `aggregate_id`, `name`, `aws_region`, `aws_instance_id`, `instance_type`, `ami_id`, `ami_name`, `status`, `cml_version`, `created_at`, `created_by`

#### CMLWorkerStatusUpdatedDomainEvent

Raised when EC2 instance status changes.

**Fields**: `aggregate_id`, `old_status`, `new_status`, `updated_at`

#### CMLServiceStatusUpdatedDomainEvent

Raised when CML HTTPS service status changes.

**Fields**: `aggregate_id`, `old_service_status`, `new_service_status`, `https_endpoint`, `updated_at`

#### CMLWorkerInstanceAssignedDomainEvent

Raised when AWS EC2 instance ID is assigned.

**Fields**: `aggregate_id`, `aws_instance_id`, `public_ip`, `private_ip`, `assigned_at`

#### CMLWorkerLicenseUpdatedDomainEvent

Raised when license status is updated.

**Fields**: `aggregate_id`, `license_status`, `license_token`, `updated_at`

#### CMLWorkerTelemetryUpdatedDomainEvent

Raised when telemetry data is collected.

**Fields**: `aggregate_id`, `last_activity_at`, `active_labs_count`, `cpu_utilization`, `memory_utilization`, `updated_at`

#### CMLWorkerEndpointUpdatedDomainEvent

Raised when HTTPS endpoint is updated.

**Fields**: `aggregate_id`, `https_endpoint`, `public_ip`, `updated_at`

#### CMLWorkerTerminatedDomainEvent

Raised when worker is terminated.

**Fields**: `aggregate_id`, `name`, `terminated_at`, `terminated_by`

### Repository Interface

**Location**: `src/domain/repositories/cml_worker_repository.py`

#### Query Methods

```python
async def get_all_async() -> list[CMLWorker]
async def get_by_id_async(worker_id: str) -> CMLWorker | None
async def get_by_aws_instance_id_async(aws_instance_id: str) -> CMLWorker | None
async def get_by_status_async(status: CMLWorkerStatus) -> list[CMLWorker]
async def get_active_workers_async() -> list[CMLWorker]
async def get_idle_workers_async(idle_threshold_minutes: int) -> list[CMLWorker]
```

#### Command Methods

```python
async def add_async(entity: CMLWorker) -> CMLWorker
async def update_async(entity: CMLWorker) -> CMLWorker
async def delete_async(worker_id: str, worker: Optional[CMLWorker] = None) -> bool
```

## Aggregate Behavior

### Lifecycle Operations

#### `update_status(new_status: CMLWorkerStatus) -> bool`

Updates EC2 instance status. Returns `False` if status unchanged.

#### `update_service_status(new_service_status: CMLServiceStatus, https_endpoint: Optional[str]) -> bool`

Updates CML service availability and endpoint. Returns `False` if unchanged.

#### `assign_instance(aws_instance_id: str, public_ip: Optional[str], private_ip: Optional[str]) -> None`

Assigns AWS EC2 instance details to the worker.

#### `terminate(terminated_by: Optional[str]) -> None`

Marks worker as terminated.

### License Management

#### `update_license(license_status: LicenseStatus, license_token: Optional[str]) -> bool`

Updates CML license status. Returns `False` if unchanged.

### Telemetry & Monitoring

#### `update_telemetry(last_activity_at: datetime, active_labs_count: int, cpu_utilization: Optional[float], memory_utilization: Optional[float]) -> None`

Updates worker telemetry data.

#### `is_idle(idle_threshold_minutes: int) -> bool`

Checks if worker has been idle beyond threshold. Returns `True` if idle.

**Idle Criteria**:

- Has `last_activity_at` timestamp
- `active_labs_count == 0`
- Time since last activity exceeds threshold

### Connectivity

#### `update_endpoint(https_endpoint: Optional[str], public_ip: Optional[str]) -> bool`

Updates HTTPS endpoint and optionally public IP. Returns `False` if unchanged.

#### `can_connect() -> bool`

Checks if worker is ready for connections.

**Connection Ready Criteria**:

- Status is `RUNNING`
- Service status is `AVAILABLE`
- HTTPS endpoint is set

## Usage Patterns

### Creating a Worker

```python
worker = CMLWorker(
    name="Dev Lab Worker 1",
    aws_region="us-east-1",
    instance_type="c5.2xlarge",
    ami_id="ami-0123456789abcdef0",
    ami_name="CML-2.7.0-Ubuntu-22.04",
    cml_version="2.7.0",
    created_by="user_123"
)
```

### Updating Worker State

```python
# Update EC2 status
worker.update_status(CMLWorkerStatus.RUNNING)

# Assign instance details after provisioning
worker.assign_instance(
    aws_instance_id="i-1234567890abcdef0",
    public_ip="54.123.45.67",
    private_ip="10.0.1.100"
)

# Update service availability
worker.update_service_status(
    CMLServiceStatus.AVAILABLE,
    https_endpoint="https://54.123.45.67"
)
```

### Monitoring & Automation

```python
# Update telemetry
worker.update_telemetry(
    last_activity_at=datetime.now(timezone.utc),
    active_labs_count=2,
    cpu_utilization=45.5,
    memory_utilization=62.3
)

# Check if idle
if worker.is_idle(idle_threshold_minutes=30):
    # Trigger auto-shutdown
    worker.update_status(CMLWorkerStatus.STOPPING)
```

### User Connection Flow

```python
# Check if ready for connections
if worker.can_connect():
    endpoint = worker.state.https_endpoint
    # Direct user to endpoint
else:
    # Show status and wait
    pass
```

## Integration Points

### Application Layer

- **Commands**: Create, update, start, stop, terminate workers
- **Queries**: Get worker status, list available workers, find idle workers
- **Event Handlers**: React to status changes, trigger notifications

### Infrastructure Layer

- **AWS Integration**: EC2 instance management via boto3
- **CML API Client**: License management, telemetry collection
- **Monitoring**: CloudWatch metrics, health checks

### Repository Implementations

- **In-Memory**: For testing and development
- **MongoDB**: For production persistence
- **Event Store**: For event sourcing (if required)

## Design Decisions

### Why AggregateState Pattern?

- **Event Sourcing**: Complete audit trail of all state changes
- **Domain Events**: Clean integration with event-driven architecture
- **CQRS**: Natural separation of commands and queries

### Why Separate Status Enums?

- **EC2 Status**: Represents infrastructure state (AWS concern)
- **Service Status**: Represents application availability (CML concern)
- **Clear Semantics**: Different lifecycle management per concern

### Telemetry as Aggregate State

- **Decision Point**: Telemetry stored in aggregate, not separate entity
- **Rationale**: Telemetry drives idle detection and lifecycle decisions
- **Trade-off**: More frequent updates, but simpler model

## Future Enhancements

### Potential Extensions

1. **Lab Assignments**
   - Add `LabAssignment` value object
   - Track which users have access to which labs
   - Enforce RBAC at domain level

2. **Cost Tracking**
   - Add `cost_per_hour` attribute
   - Calculate running costs
   - Cost-based shutdown policies

3. **Maintenance Windows**
   - Add `maintenance_schedule` value object
   - Prevent auto-shutdown during maintenance
   - Schedule patches and updates

4. **Multi-Region Support**
   - Add region-specific configuration
   - Cross-region failover
   - Region affinity for users

5. **Snapshot Management**
   - Track EBS snapshots
   - Backup policies
   - Restore capabilities
