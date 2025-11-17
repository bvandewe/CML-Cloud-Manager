# CML API Debugging Guide

## Issue

The CML API is not being called during worker refresh, and all CML attributes remain at default values.

## Root Cause Analysis

The CML API is only called when ALL these conditions are met:

1. **Worker status** = `RUNNING`
2. **HTTPS endpoint** is set (not None/empty)
3. **Service status** = `AVAILABLE`

## How Service Status is Determined

**Automatic Health Check**: The refresh command now automatically performs a health check using the `/api/v0/system_health` endpoint:

1. **If endpoint is set and worker is RUNNING**: Attempts to call `/api/v0/system_health`
2. **If health check succeeds** (`system_health.valid == True`): Sets service status to `AVAILABLE` ✅
3. **If health check fails** (connection error, timeout): Sets service status to `UNAVAILABLE` ❌
4. **If health check returns invalid**: Sets service status to `ERROR` ⚠️

This happens **automatically** during each refresh cycle, so the service status should update itself based on actual CML service availability.

## Diagnostic Logs Added

The following log messages have been added to help diagnose the issue:

### 1. Public IP and Endpoint Population

```
Worker {id} has public IP: {ip}, current endpoint: {endpoint}
Auto-populated HTTPS endpoint for worker {id}: https://{ip}
Worker {id} has no public IP from AWS, cannot auto-populate endpoint
```

### 2. CML Service Health Check (NEW!)

```
Performing CML service health check for worker {id} at {endpoint}
✅ CML service health check passed for worker {id} - service marked as AVAILABLE (licensed={bool}, enterprise={bool})
⚠️  CML service health check failed for worker {id} - service returned invalid health status
❌ CML service not accessible for worker {id}: {error} - service marked as UNAVAILABLE
```

### 3. CML API Call Decision

```
CML API check for worker {id}: status={status}, has_endpoint={bool}, endpoint={url}, service_status={status}
```

### 4. When CML API IS Called

```
Attempting to query CML API for worker {id} at {endpoint}
```

### 5. When CML API IS NOT Called

```
Skipping CML API query for worker {id} - not meeting requirements (status={status}, has_endpoint={bool}, service_status={status})
```

## Troubleshooting Steps

### Step 1: Check Worker Status

Look for the log: `CML API check for worker {id}`

Expected values:

- `status=CMLWorkerStatus.RUNNING` ✅
- `has_endpoint=True` ✅
- `endpoint=https://{public_ip}` ✅
- `service_status=CMLServiceStatus.AVAILABLE` ✅

### Step 2: Common Issues

#### Issue A: Missing HTTPS Endpoint

**Symptom**: `has_endpoint=False` or `endpoint=None`

**Cause**: Worker doesn't have a public IP, or endpoint wasn't auto-populated

**Solution**:

1. Check if worker has public IP: Look for "Worker {id} has public IP"
2. If no public IP: Worker might be in private subnet or hasn't finished launching
3. Manually set endpoint in worker creation/configuration

#### Issue B: Service Status Not AVAILABLE

**Symptom**: `service_status=UNAVAILABLE`, `STARTING`, or `ERROR`

**Cause**: CML service health check failed or hasn't completed yet

**Solution**:

1. **Check health check logs**: Look for "CML service health check" messages
2. **If health check is failing**:
   - Verify CML service is actually running on the worker
   - Check if CML web interface is accessible at `https://{public_ip}`
   - Verify credentials in settings: `cml_worker_api_username` and `cml_worker_api_password`
   - Check for network/firewall issues blocking HTTPS access
3. **If first refresh after worker start**: Service status starts as `UNAVAILABLE`, wait for first refresh cycle to complete (health check runs automatically)
4. **Service will auto-update**: Each refresh cycle performs a health check and updates the status accordingly

#### Issue C: Worker Not RUNNING

**Symptom**: `status=PENDING` or `status=STOPPED`

**Cause**: EC2 instance isn't in running state yet

**Solution**: Wait for EC2 instance to fully start

### Step 3: Verify CML API Credentials

Even if all conditions are met, the CML API calls need valid credentials.

Check the settings:

```python
cml_worker_api_username  # From settings
cml_worker_api_password  # From settings
```

These are configured in your application settings/environment variables.

## Testing the Fix

1. **Restart the application** to pick up the new logging
2. **Click the Refresh button** on a running worker
3. **Check the logs** for the diagnostic messages above
4. **Share the log output** if you need further help

### Expected Log Sequence (Success)

```
Worker abc123 has public IP: 54.123.45.67, current endpoint: None
Auto-populated HTTPS endpoint for worker abc123: https://54.123.45.67
Performing CML service health check for worker abc123 at https://54.123.45.67
✅ CML service health check passed for worker abc123 - service marked as AVAILABLE (licensed=True, enterprise=True)
CML API check for worker abc123: status=RUNNING, has_endpoint=True, endpoint=https://54.123.45.67, service_status=AVAILABLE
Attempting to query CML API for worker abc123 at https://54.123.45.67
Worker abc123 CML stats: Version=2.9.0, Ready=True, Licensed=True, Nodes=5/10, CPUs allocated=20
```

### Expected Log Sequence (Service Not Ready)

```
Worker abc123 has public IP: 54.123.45.67, current endpoint: None
Auto-populated HTTPS endpoint for worker abc123: https://54.123.45.67
Performing CML service health check for worker abc123 at https://54.123.45.67
❌ CML service not accessible for worker abc123: Connection timeout - service marked as UNAVAILABLE
CML API check for worker abc123: status=RUNNING, has_endpoint=True, endpoint=https://54.123.45.67, service_status=UNAVAILABLE
Skipping CML API query for worker abc123 - not meeting requirements (status=RUNNING, has_endpoint=True, service_status=UNAVAILABLE)
```

## Next Steps

1. **Restart the application** to load the updated code with health check
2. **Click the Refresh button** on a running worker
3. **Check the logs** for the health check sequence
4. **The service status should auto-update** based on CML service availability

The health check now runs **automatically on every refresh**, so you should see the service status change from `UNAVAILABLE` → `AVAILABLE` once the CML service is accessible.
