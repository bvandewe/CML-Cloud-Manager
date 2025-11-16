# Exception Hierarchy Enhancement for AWS EC2 Client

**Date**: November 16, 2025
**Status**: ✅ Complete

## Overview

Replaced generic `IntegrationException` with specific exception types for better error handling, debugging, and user experience.

---

## Exception Hierarchy

```
IntegrationException (base)
└── EC2Exception (AWS EC2 base)
    ├── EC2AuthenticationException
    ├── EC2InstanceNotFoundException
    ├── EC2InstanceCreationException
    ├── EC2InstanceOperationException
    ├── EC2TagOperationException
    ├── EC2StatusCheckException
    ├── EC2QuotaExceededException
    └── EC2InvalidParameterException
```

---

## Exception Types

### 1. `EC2AuthenticationException`

**When**: AWS credentials invalid or insufficient permissions
**AWS Error Codes**: `UnauthorizedOperation`, `InvalidClientTokenId`, `SignatureDoesNotMatch`, `AccessDenied`
**Example**:

```python
try:
    client.create_instance(...)
except EC2AuthenticationException as e:
    # Show user: "Please check your AWS credentials"
    # Log: Contact AWS admin for permission review
```

### 2. `EC2InstanceNotFoundException`

**When**: Instance ID doesn't exist
**AWS Error Codes**: `InvalidInstanceID.NotFound`
**Example**:

```python
try:
    client.start_instance(region, "i-invalid123")
except EC2InstanceNotFoundException:
    # Instance was already terminated or never existed
    # Update UI: Show "Instance not found" message
```

### 3. `EC2InstanceCreationException`

**When**: Instance creation fails
**Causes**: Invalid AMI, network config issues, internal AWS errors
**Example**:

```python
try:
    dto = client.create_instance(...)
except EC2InstanceCreationException as e:
    # Retry with different AZ or instance type
    # Log for capacity planning
```

### 4. `EC2InstanceOperationException`

**When**: Start/stop/terminate operations fail
**Causes**: Instance in wrong state, concurrent modification
**Example**:

```python
try:
    client.stop_instance(region, instance_id)
except EC2InstanceOperationException:
    # Can't stop instance that's already stopping
    # Show user current state and wait
```

### 5. `EC2TagOperationException`

**When**: Tag add/remove/get operations fail
**Causes**: Tag limit exceeded, invalid tag format
**Example**:

```python
try:
    client.add_tags(region, instance_id, large_tag_dict)
except EC2TagOperationException as e:
    # AWS has 50-tag limit per resource
    # Remove old tags before adding new ones
```

### 6. `EC2StatusCheckException`

**When**: Cannot retrieve instance health status
**Causes**: Instance too new, API throttling
**Example**:

```python
try:
    status = client.get_instance_status_checks(region, instance_id)
except EC2StatusCheckException:
    # Status checks not available yet (instance just launched)
    # Retry after 2-3 minutes
```

### 7. `EC2QuotaExceededException`

**When**: AWS resource limits hit
**AWS Error Codes**: `InstanceLimitExceeded`, `InsufficientInstanceCapacity`, `RequestLimitExceeded`
**Example**:

```python
try:
    client.create_instance(...)
except EC2QuotaExceededException as e:
    # Request quota increase from AWS
    # Show user: "Maximum instance limit reached"
```

### 8. `EC2InvalidParameterException`

**When**: Invalid parameters provided
**AWS Error Codes**: `InvalidParameterValue`, `InvalidAMIID.NotFound`, `InvalidGroup.NotFound`
**Example**:

```python
try:
    client.create_instance(
        ami_id="ami-invalid",  # Wrong!
        ...
    )
except EC2InvalidParameterException as e:
    # Validate inputs before calling AWS
    # Show user which parameter is wrong
```

---

## Benefits

### 1. **Precise Error Handling**

```python
# Before (Generic)
try:
    client.start_instance(region, instance_id)
except IntegrationException as e:
    # What happened? Auth? Not found? Already running?
    # Can't tell without parsing error message strings
    log.error(f"Something went wrong: {e}")

# After (Specific)
try:
    client.start_instance(region, instance_id)
except EC2InstanceNotFoundException:
    # Instance was terminated, remove from database
    db.delete_worker(instance_id)
except EC2AuthenticationException:
    # Credentials expired, trigger re-auth flow
    auth_service.refresh_credentials()
except EC2InstanceOperationException as e:
    # Instance in wrong state, wait and retry
    if "already started" in str(e).lower():
        return True  # Success!
    raise
```

### 2. **Better User Experience**

```python
# Application layer can provide specific messages
try:
    await create_worker_command(...)
except EC2QuotaExceededException:
    return {
        "error": "Instance Limit Reached",
        "message": "You've reached your AWS EC2 instance limit. Please contact support to request an increase.",
        "action": "request_quota_increase"
    }
except EC2AuthenticationException:
    return {
        "error": "Authentication Failed",
        "message": "AWS credentials are invalid. Please check your configuration.",
        "action": "verify_credentials"
    }
```

### 3. **Intelligent Retry Logic**

```python
def create_worker_with_retry(config, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.create_instance(...)
        except EC2QuotaExceededException:
            # Don't retry - quota limit won't change
            raise
        except EC2InvalidParameterException:
            # Don't retry - parameters won't magically become valid
            raise
        except EC2InstanceCreationException as e:
            # Might be temporary AWS capacity issue
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
        except EC2AuthenticationException:
            # Try to refresh credentials once
            if attempt == 0:
                auth_service.refresh_credentials()
                continue
            raise
```

### 4. **Better Monitoring & Alerting**

```python
# Metrics collection
@track_exceptions
def create_worker(...):
    try:
        return client.create_instance(...)
    except EC2QuotaExceededException:
        metrics.increment("ec2.quota_exceeded")
        alerts.notify_ops("EC2 quota limit reached - request increase")
        raise
    except EC2AuthenticationException:
        metrics.increment("ec2.auth_failures")
        alerts.notify_security("AWS credential issue detected")
        raise
    except EC2InstanceCreationException:
        metrics.increment("ec2.creation_failures")
        # Track for capacity planning
        raise
```

### 5. **Cleaner Testing**

```python
# Unit tests can be very specific
def test_create_worker_quota_exceeded():
    with pytest.raises(EC2QuotaExceededException):
        service.create_worker(...)

def test_create_worker_invalid_ami():
    with pytest.raises(EC2InvalidParameterException) as exc_info:
        service.create_worker(ami_id="ami-invalid")
    assert "AMI" in str(exc_info.value)

def test_start_nonexistent_instance():
    with pytest.raises(EC2InstanceNotFoundException):
        service.start_worker("i-doesnotexist")
```

---

## Error Parsing Logic

The `_parse_aws_error()` helper method inspects AWS ClientError and returns appropriate exception:

```python
def _parse_aws_error(self, error: ClientError, operation: str) -> Exception:
    error_code = error.response.get("Error", {}).get("Code", "")

    # Maps AWS error codes to specific exceptions
    if error_code in ("UnauthorizedOperation", ...):
        return EC2AuthenticationException(...)
    if error_code in ("InvalidInstanceID.NotFound", ...):
        return EC2InstanceNotFoundException(...)
    # ... etc

    # Fall back to generic for unknown errors
    return IntegrationException(f"AWS error [{error_code}]: {message}")
```

---

## Updated Method Signatures

All methods now document specific exceptions:

```python
def create_instance(...) -> CMLWorkerInstanceDto | None:
    """
    Raises:
        EC2InvalidParameterException: Invalid AMI, security group, etc.
        EC2InstanceCreationException: Instance creation failed.
        EC2QuotaExceededException: Instance limit reached.
        EC2AuthenticationException: Invalid credentials.
    """

def start_instance(...) -> bool:
    """
    Raises:
        EC2InstanceNotFoundException: Instance not found.
        EC2InstanceOperationException: Start operation failed.
        EC2AuthenticationException: Invalid credentials.
    """
```

---

## Migration Guide

### For Existing Code

**Before**:

```python
try:
    client.create_instance(...)
except IntegrationException as e:
    log.error(f"Failed: {e}")
    raise
```

**After** (minimal change - still works):

```python
try:
    client.create_instance(...)
except IntegrationException as e:  # Catches all EC2* exceptions too
    log.error(f"Failed: {e}")
    raise
```

**After** (better - specific handling):

```python
try:
    client.create_instance(...)
except EC2QuotaExceededException:
    notify_admin("Need quota increase")
    raise
except EC2InvalidParameterException as e:
    log.error(f"Config error: {e}")
    raise
except IntegrationException as e:
    log.error(f"Other AWS error: {e}")
    raise
```

---

## Best Practices

### 1. **Catch Specific First, Generic Last**

```python
try:
    operation()
except EC2InstanceNotFoundException:
    # Handle specific case
    pass
except EC2InstanceOperationException:
    # Handle another specific case
    pass
except IntegrationException:
    # Catch-all for unexpected issues
    pass
```

### 2. **Don't Catch and Ignore**

```python
# BAD
try:
    client.create_instance(...)
except IntegrationException:
    pass  # Silently fails - terrible!

# GOOD
try:
    client.create_instance(...)
except EC2QuotaExceededException as e:
    log.warning(f"Quota exceeded: {e}")
    notify_admin()
    raise  # Re-raise after handling
```

### 3. **Add Context When Re-raising**

```python
try:
    client.start_instance(region, instance_id)
except EC2InstanceNotFoundException as e:
    raise EC2InstanceNotFoundException(
        f"Cannot start worker {worker_name} (instance {instance_id}): {e}"
    ) from e
```

---

## Summary

✅ **8 specific exception types** instead of generic `IntegrationException`
✅ **Automatic AWS error parsing** with `_parse_aws_error()` helper
✅ **All methods updated** with specific exception documentation
✅ **Backward compatible** - `IntegrationException` is still base class
✅ **Better error handling** throughout the codebase
✅ **Improved testability** with specific exception types

The AWS EC2 client now provides enterprise-grade error handling! 🎯
