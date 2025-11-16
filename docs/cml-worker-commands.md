# CML Worker Application Commands

**Date**: November 16, 2025
**Status**: ✅ Complete

## Overview

Created 6 application commands for CML Worker lifecycle management, integrating the domain layer (CMLWorker aggregate) with the AWS EC2 API client. All commands follow CQRS pattern with proper error handling, tracing, and domain event publishing.

---

## Commands Created

### 1. **CreateCMLWorkerCommand**

**File**: `src/application/commands/create_cml_worker_command.py`

**Purpose**: Create a new CML Worker and provision AWS EC2 instance

**Flow**:

1. Determines AMI from settings based on region
2. Creates CMLWorker domain aggregate (PENDING status)
3. Provisions EC2 instance via `aws_ec2_client.create_instance()`
4. Assigns instance to worker aggregate with `worker.assign_instance()`
5. Updates worker status based on instance state
6. Saves to repository (publishes domain events)

**Parameters**:

- `name`: Worker name
- `aws_region`: AWS region
- `instance_type`: EC2 instance type
- `ami_id`: Optional AMI ID (uses settings if not provided)
- `ami_name`: Optional AMI name
- `cml_version`: Optional CML version
- `created_by`: User who created the worker

**Returns**: `CMLWorkerInstanceDto` with instance details

**Exception Handling**:

- `EC2InvalidParameterException`: Invalid AMI or parameters
- `EC2QuotaExceededException`: AWS instance limit reached
- `EC2AuthenticationException`: Invalid credentials
- `EC2InstanceCreationException`: Instance creation failed

---

### 2. **StartCMLWorkerCommand**

**File**: `src/application/commands/start_cml_worker_command.py`

**Purpose**: Start a stopped CML Worker EC2 instance

**Flow**:

1. Retrieves worker from repository
2. Validates worker has AWS instance assigned
3. Checks current status (skip if already running, error if terminated)
4. Starts EC2 instance via `aws_ec2_client.start_instance()`
5. Updates worker status to STARTING
6. Saves to repository (publishes domain events)

**Parameters**:

- `worker_id`: CML Worker ID
- `started_by`: Optional user who started the worker

**Returns**: `bool` (True if started successfully)

**Exception Handling**:

- `EC2InstanceNotFoundException`: Instance not found
- `EC2InstanceOperationException`: Start operation failed
- `EC2AuthenticationException`: Invalid credentials

---

### 3. **StopCMLWorkerCommand**

**File**: `src/application/commands/stop_cml_worker_command.py`

**Purpose**: Stop a running CML Worker EC2 instance

**Flow**:

1. Retrieves worker from repository
2. Validates worker has AWS instance assigned
3. Checks current status (skip if already stopped, error if terminated)
4. Stops EC2 instance via `aws_ec2_client.stop_instance()`
5. Updates worker status to STOPPING
6. Saves to repository (publishes domain events)

**Parameters**:

- `worker_id`: CML Worker ID
- `stopped_by`: Optional user who stopped the worker

**Returns**: `bool` (True if stopped successfully)

**Exception Handling**:

- `EC2InstanceNotFoundException`: Instance not found
- `EC2InstanceOperationException`: Stop operation failed
- `EC2AuthenticationException`: Invalid credentials

---

### 4. **TerminateCMLWorkerCommand**

**File**: `src/application/commands/terminate_cml_worker_command.py`

**Purpose**: Terminate CML Worker and permanently delete EC2 instance

**Flow**:

1. Retrieves worker from repository
2. If worker has AWS instance, terminates it via `aws_ec2_client.terminate_instance()`
3. Handles instance-not-found gracefully (logs warning, continues)
4. Marks worker as terminated via `worker.terminate()`
5. Saves to repository (publishes domain events)

**Parameters**:

- `worker_id`: CML Worker ID
- `terminated_by`: Optional user who terminated the worker

**Returns**: `bool` (True if terminated successfully)

**Exception Handling**:

- `EC2InstanceNotFoundException`: Logged as warning, continues (instance already gone)
- `EC2InstanceOperationException`: Terminate operation failed
- `EC2AuthenticationException`: Invalid credentials

**Warning**: This is a destructive operation that cannot be undone!

---

### 5. **UpdateCMLWorkerTagsCommand**

**File**: `src/application/commands/update_cml_worker_tags_command.py`

**Purpose**: Add or update tags on CML Worker EC2 instance

**Flow**:

1. Retrieves worker from repository
2. Validates worker has AWS instance assigned
3. Adds/updates tags via `aws_ec2_client.add_tags()`
4. Retrieves all tags to return updated state
5. Returns complete tag dictionary

**Parameters**:

- `worker_id`: CML Worker ID
- `tags`: Dictionary of tag key-value pairs
- `updated_by`: Optional user who updated tags

**Returns**: `dict[str, str]` with all instance tags

**Exception Handling**:

- `EC2InstanceNotFoundException`: Instance not found
- `EC2TagOperationException`: Tag operation failed (e.g., 50-tag limit)
- `EC2AuthenticationException`: Invalid credentials

**Use Case**: Organize resources, track costs, add metadata

---

### 6. **UpdateCMLWorkerStatusCommand**

**File**: `src/application/commands/update_cml_worker_status_command.py`

**Purpose**: Sync CML Worker status from AWS EC2 (status reconciliation)

**Flow**:

1. Retrieves worker from repository
2. Queries EC2 instance status via `aws_ec2_client.get_instance_status_checks()`
3. Maps EC2 state to CMLWorkerStatus:
   - `running` → RUNNING
   - `stopped` → STOPPED
   - `stopping` → STOPPING
   - `pending` → STARTING
   - `shutting-down` → STOPPING
   - `terminated` → calls `worker.terminate()`
4. Updates worker status if changed
5. Saves to repository if status changed (publishes domain events)

**Parameters**:

- `worker_id`: CML Worker ID

**Returns**: `dict[str, str]` with status check information (instance_state, instance_status_check, ec2_system_status_check)

**Exception Handling**:

- `EC2InstanceNotFoundException`: Marks worker as terminated (instance gone from AWS)
- `EC2StatusCheckException`: Status check retrieval failed
- `EC2AuthenticationException`: Invalid credentials

**Use Case**: Background job to keep worker state in sync with AWS

---

## Integration Points

### Domain Layer

All commands interact with:

- **CMLWorker aggregate**: Domain entity with business logic
- **CMLWorkerRepository**: Abstract repository for persistence
- **Domain events**: Automatically published when worker state changes

### Integration Layer

All commands use:

- **AwsEc2Client**: AWS EC2 API wrapper
- **Specific exceptions**: EC2InvalidParameterException, EC2InstanceNotFoundException, etc.
- **CMLWorkerInstanceDto**: Data transfer object for AWS responses

### Application Settings

Commands use these settings:

- `cml_worker_ami_ids`: Dict of AMI IDs per region
- `cml_worker_ami_names`: Dict of AMI names per region
- `cml_worker_security_group_ids`: Security group IDs
- `cml_worker_subnet_id`: VPC subnet ID
- `cml_worker_key_name`: SSH key pair name

---

## CQRS Pattern

All commands follow the Neuroglia CQRS pattern:

```python
@dataclass
class MyCommand(Command[OperationResult[TReturn]]):
    """Command definition"""
    param1: str
    param2: int

class MyCommandHandler(
    CommandHandlerBase,
    CommandHandler[MyCommand, OperationResult[TReturn]],
):
    """Command handler"""

    async def handle_async(self, request: MyCommand) -> OperationResult[TReturn]:
        # Implementation
        pass
```

---

## Observability

All commands include:

1. **OpenTelemetry Tracing**:
   - Automatic span from CQRS middleware
   - Custom spans for each operation phase
   - Attributes for debugging (worker_id, instance_id, status, etc.)

2. **Structured Logging**:
   - Info logs for success
   - Error logs with exception details
   - Warning logs for non-critical issues

3. **Error Context**:
   - Specific exception types for different error scenarios
   - Error messages include relevant IDs and context
   - Stack traces for unexpected errors

---

## Usage Examples

### Create Worker

```python
command = CreateCMLWorkerCommand(
    name="cml-worker-prod-01",
    aws_region="us-east-1",
    instance_type="c5.2xlarge",
    cml_version="2.6.1",
    created_by="user-123",
)
result = await mediator.send_async(command)
```

### Start Worker

```python
command = StartCMLWorkerCommand(
    worker_id="550e8400-e29b-41d4-a716-446655440000",
    started_by="user-123",
)
result = await mediator.send_async(command)
```

### Sync Status (Background Job)

```python
# Run periodically to keep workers in sync with AWS
for worker in await repository.get_all_async():
    command = UpdateCMLWorkerStatusCommand(worker_id=worker.id())
    await mediator.send_async(command)
```

---

## File Structure

```
src/application/commands/
├── __init__.py                          # Exports all commands
├── command_handler_base.py              # Base class
├── create_cml_worker_command.py         # ✅ New
├── start_cml_worker_command.py          # ✅ New
├── stop_cml_worker_command.py           # ✅ New
├── terminate_cml_worker_command.py      # ✅ New
├── update_cml_worker_tags_command.py    # ✅ New
├── update_cml_worker_status_command.py  # ✅ New
├── create_task_command.py               # Existing
├── update_task_command.py               # Existing
└── delete_task_command.py               # Existing
```

---

## Next Steps

### Recommended

1. **Create Queries**:
   - `GetCMLWorkerQuery` - Retrieve worker by ID
   - `ListCMLWorkersQuery` - List all workers with filtering
   - `GetCMLWorkerMetricsQuery` - Get worker telemetry

2. **API Controllers**:
   - Add endpoints to `src/api/controllers/workers_controller.py`
   - Map commands to HTTP POST/PUT endpoints
   - Handle authentication and authorization

3. **Background Jobs**:
   - Status sync job (every 5 minutes)
   - Idle worker detection (check telemetry)
   - Auto-stop/terminate for cost optimization

4. **Tests**:
   - Unit tests for each command handler
   - Mock AWS client responses
   - Test exception handling paths

---

## Summary

✅ **6 commands created** for complete CML Worker lifecycle management
✅ **Domain-driven design** with proper aggregate boundaries
✅ **Clean architecture** with separation of concerns
✅ **Specific exception handling** for better error management
✅ **Full observability** with tracing and logging
✅ **CQRS pattern** following Neuroglia framework

The application layer is now complete for CML Worker management! 🎯
