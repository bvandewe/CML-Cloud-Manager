# AWS EC2 Client Enhancement: Status Checks & Tag Management

**Date**: November 16, 2025
**Status**: ✅ Complete

## Summary

Added instance status checks and tag management capabilities to the AWS EC2 API client, along with corresponding fields in the CMLWorkerInstanceDto.

---

## 1. Enhanced CMLWorkerInstanceDto ✅

**File**: `src/integration/models/cml_worker_instance_dto.py`

### New Fields Added

| Field | Type | Description |
|-------|------|-------------|
| `instance_state` | `str \| None` | Current EC2 state (pending, running, stopping, stopped, etc.) |
| `tags` | `dict[str, str]` | Dictionary of instance tags |
| `instance_status` | `str \| None` | Instance status check result (ok, impaired, etc.) |
| `system_status` | `str \| None` | System status check result (ok, impaired, etc.) |

### Benefits

- DTO now captures complete instance state
- Tags are included for better tracking and filtering
- Status checks help monitor instance health
- Aligns with EC2 API response structure

---

## 2. New AWS EC2 Client Methods ✅

**File**: `src/integration/services/aws_ec2_api_client.py`

### A. `get_instance_status_checks()` - NEW ✨

```python
def get_instance_status_checks(
    self,
    aws_region: AwsRegion,
    instance_id: str,
) -> dict[str, str]
```

**Purpose**: Retrieve instance and system status checks

**Returns**:

```python
{
    "instance_status": "ok",      # or "impaired", "insufficient-data", etc.
    "system_status": "ok",        # or "impaired", "insufficient-data", etc.
    "instance_state": "running"   # or "pending", "stopping", "stopped", etc.
}
```

**Use Cases**:

- Monitor CML Worker health before assigning labs
- Detect instances with hardware issues
- Verify instance is ready for CML service startup
- Auto-recovery triggers for impaired instances

---

### B. `get_tags()` - NEW ✨

```python
def get_tags(
    self,
    aws_region: AwsRegion,
    instance_id: str,
) -> dict[str, str]
```

**Purpose**: Retrieve all tags for an instance

**Returns**: Dictionary of tag key-value pairs

**Use Cases**:

- Audit instance ownership and metadata
- Filter workers by custom tags
- Track cost allocation tags
- Verify compliance with tagging policies

---

### C. `add_tags()` - NEW ✨

```python
def add_tags(
    self,
    aws_region: AwsRegion,
    instance_id: str,
    tags: dict[str, str],
) -> bool
```

**Purpose**: Add or update tags on an instance

**Use Cases**:

- Tag workers with lab assignments
- Add cost center information
- Mark workers for maintenance
- Track worker lifecycle states

**Example**:

```python
client.add_tags(
    aws_region=AwsRegion.US_EAST_1,
    instance_id="i-1234567890abcdef0",
    tags={
        "AssignedLab": "CCNA-Lab-5",
        "Student": "john.doe@example.com",
        "LabStartTime": "2025-11-16T10:30:00Z",
        "AutoShutdown": "true"
    }
)
```

---

### D. `remove_tags()` - NEW ✨

```python
def remove_tags(
    self,
    aws_region: AwsRegion,
    instance_id: str,
    tag_keys: list[str],
) -> bool
```

**Purpose**: Remove specific tags from an instance

**Use Cases**:

- Clean up temporary tags after lab completion
- Remove outdated metadata
- Unassign lab from worker
- Clear maintenance flags

**Example**:

```python
client.remove_tags(
    aws_region=AwsRegion.US_EAST_1,
    instance_id="i-1234567890abcdef0",
    tag_keys=["AssignedLab", "Student", "LabStartTime"]
)
```

---

## 3. Updated `create_instance()` Method ✅

Enhanced to populate new DTO fields:

```python
return CMLWorkerInstanceDto(
    # ... existing fields ...
    instance_state=instance.state["Name"],  # NEW
    tags=tags,                               # NEW (extracted from instance)
    # instance_status and system_status are None initially
    # (populated later via get_instance_status_checks)
)
```

---

## 4. Complete Method Inventory

### Lifecycle Operations

- ✅ `create_instance()` - Create new EC2 instance
- ✅ `start_instance()` - Start stopped instance
- ✅ `stop_instance()` - Stop running instance
- ✅ `terminate_instance()` - Terminate instance

### Information Retrieval

- ✅ `get_instance_details()` - Get instance metadata
- ✅ `get_instance_status_checks()` - Get health status **[NEW]**
- ✅ `list_instances()` - List instances with filters
- ✅ `get_instance_resources_utilization()` - Get CloudWatch metrics

### Tag Management

- ✅ `get_tags()` - Retrieve instance tags **[NEW]**
- ✅ `add_tags()` - Add/update tags **[NEW]**
- ✅ `remove_tags()` - Remove tags **[NEW]**

---

## 5. Integration Patterns

### Pattern 1: Create Worker with Full Status

```python
# 1. Create instance
dto = aws_client.create_instance(
    aws_region=AwsRegion.US_EAST_1,
    instance_name="cml-worker-prod-001",
    ami_id="ami-0123456789abcdef0",
    ami_name="CML-2.7.0-Ubuntu-22.04",
    instance_type="c5.2xlarge",
    security_group_ids=["sg-123"],
    subnet_id="subnet-456",
    key_name="cml-worker-key"
)

# 2. Wait for instance to be ready (poll status)
import time
max_retries = 30
for i in range(max_retries):
    status = aws_client.get_instance_status_checks(
        aws_region=AwsRegion.US_EAST_1,
        instance_id=dto.aws_instance_id
    )
    if status["instance_state"] == "running" and status["instance_status"] == "ok":
        break
    time.sleep(10)

# 3. Tag with metadata
aws_client.add_tags(
    aws_region=AwsRegion.US_EAST_1,
    instance_id=dto.aws_instance_id,
    tags={
        "Environment": "Production",
        "ManagedBy": "CML-Cloud-Manager",
        "CMLVersion": "2.7.0"
    }
)
```

### Pattern 2: Health Check Before Lab Assignment

```python
# Before assigning expensive lab, verify worker is healthy
status = aws_client.get_instance_status_checks(
    aws_region=worker.aws_region,
    instance_id=worker.aws_instance_id
)

if status["instance_status"] != "ok" or status["system_status"] != "ok":
    # Don't assign lab, instance has issues
    raise WorkerUnhealthyException(
        f"Worker {worker.id} failed health checks: {status}"
    )

# Proceed with lab assignment...
```

### Pattern 3: Tag-Based Worker Discovery

```python
# Get all tags for a worker
tags = aws_client.get_tags(
    aws_region=AwsRegion.US_EAST_1,
    instance_id=instance_id
)

# Check if worker is already assigned
if "AssignedLab" in tags:
    assigned_lab = tags["AssignedLab"]
    # Handle already-assigned worker
else:
    # Worker is available, assign new lab
    pass
```

### Pattern 4: Cleanup on Lab Termination

```python
# When student completes lab, clean up worker tags
aws_client.remove_tags(
    aws_region=worker.aws_region,
    instance_id=worker.aws_instance_id,
    tag_keys=["AssignedLab", "Student", "LabStartTime", "AutoShutdown"]
)

# Stop or terminate worker
if should_reuse_worker:
    aws_client.stop_instance(worker.aws_region, worker.aws_instance_id)
else:
    aws_client.terminate_instance(worker.aws_region, worker.aws_instance_id)
```

---

## 6. Error Handling

All new methods follow the same pattern:

```python
try:
    # AWS operation
except (ValueError, ParamValidationError, ClientError) as e:
    log.error(f"Error message: {e}")
    raise IntegrationException(f"User-friendly error: {e}")
```

Benefits:

- Consistent error handling across all methods
- AWS-specific errors wrapped in application exception
- Detailed logging for troubleshooting
- Clean separation of concerns

---

## 7. Next Steps

### Application Layer Integration

1. **Command Handlers** - Use new methods in CQRS commands:
   - `CreateCMLWorkerCommand` → populate status after creation
   - `AssignLabToWorkerCommand` → verify health before assignment
   - `TerminateWorkerCommand` → clean up tags before termination

2. **Query Handlers** - Include status in queries:
   - `GetWorkerDetailsQuery` → fetch current status and tags
   - `ListHealthyWorkersQuery` → filter by status checks
   - `ListAvailableWorkersQuery` → filter by tags (no "AssignedLab")

3. **Event Handlers** - Track state changes:
   - Update domain entity when status changes
   - Publish events on tag changes
   - Monitor for impaired instances

### Testing

1. Unit tests for new methods with mocked boto3
2. Integration tests with real AWS (or LocalStack)
3. End-to-end tests for complete workflows

### Documentation

1. Update API documentation with new capabilities
2. Add operational runbooks for health monitoring
3. Document tagging strategy and conventions

---

## Benefits Summary

✅ **Better Observability**: Health status monitoring
✅ **Flexible Metadata**: Tag-based tracking and filtering
✅ **Operational Excellence**: Proactive health checks before operations
✅ **Cost Management**: Tag-based cost allocation
✅ **Compliance**: Enforce tagging policies
✅ **Automation**: Enable auto-recovery based on status

The AWS EC2 client now provides comprehensive instance management capabilities!
