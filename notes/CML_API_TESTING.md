# CML API Testing Guide

## Overview

The CML API client has been implemented with JWT authentication support. Testing is pending until workers have properly configured HTTPS endpoints.

## Current Worker Status

Both workers are currently:

- **Status**: `running`
- **Service Status**: `unavailable`
- **HTTPS Endpoint**: `null` ❌
- **Public IP**: `null` ❌

**Cannot test until workers are fully provisioned and CML service is available.**

## Authentication Method

The CML API uses **JWT Bearer tokens**, not Basic auth:

1. POST `/api/v0/authenticate` with `{"username": "admin", "password": "password"}`  <!-- pragma: allowlist secret -->
2. Response is a JWT token string
3. Use token in subsequent requests: `Authorization: Bearer <token>`
4. Token expires after some time, client auto-refreshes

## Test Script Usage

### When workers are ready

```bash
# Test specific endpoint
python scripts/test_cml_api.py --endpoint https://52.1.2.3 --username admin --password cisco

# Test by worker ID
python scripts/test_cml_api.py --worker-id 9b42b7e7-af50-4b55-ac1a-e0d9f00eefdf

# Test all RUNNING workers
python scripts/test_cml_api.py --test-all --password cisco
```

## CML API Endpoints Reference

### Authentication

- `POST /api/v0/authenticate` - Get JWT token
- `POST /api/v0/logout` - Invalidate token
- `GET /api/v0/authok` - Check if authenticated

### System Information

- `GET /api/v0/system_information` - CML version, ready status, uptime, hostname
- `GET /api/v0/system_stats` - CPU, memory, disk usage + dominfo (nodes, CPUs allocated)
- `GET /api/v0/system_health` - Health check status
- `GET /api/v0/system/compute_hosts` - List compute hosts

### Labs & Nodes

- `GET /api/v0/labs` - List all labs
- `GET /api/v0/labs/{lab_id}` - Get lab details
- `GET /api/v0/labs/{lab_id}/nodes` - List nodes in lab
- `GET /api/v0/labs/{lab_id}/nodes/{node_id}` - Get node details
- `PUT /api/v0/labs/{lab_id}/nodes/{node_id}/state/start` - Start node
- `PUT /api/v0/labs/{lab_id}/nodes/{node_id}/state/stop` - Stop node
- `PUT /api/v0/labs/{lab_id}/nodes/{node_id}/wipe_disks` - Wipe node

### Licensing

- `GET /api/v0/licensing/product_license` - Get license status
- `POST /api/v0/licensing/register` - Register license

## Quick OpenAPI Lookups

```bash
# Find all system-related endpoints
jq -r '.paths | keys[] | select(contains("system"))' notes/cml_v2.9_openapi.json

# Get details for specific endpoint
jq '.paths["/system_stats"]' notes/cml_v2.9_openapi.json

# List all authentication endpoints
jq -r '.paths | keys[] | select(contains("auth"))' notes/cml_v2.9_openapi.json

# Find all lab-related endpoints
jq -r '.paths | keys[] | select(contains("lab"))' notes/cml_v2.9_openapi.json | head -20
```

## Implementation Status

### ✅ Completed

- JWT authentication implementation
- `CMLApiClient` with token caching and auto-refresh
- `system_stats` endpoint integration
- Parsing of computes, dominfo, and resource metrics
- Test script with multiple test modes
- Error handling for unreachable instances

### 📋 Pending (blocked by worker provisioning)

- Live API testing against real CML instance
- Validation of parsed metrics accuracy
- Token expiration and refresh testing
- Integration into RefreshWorkerMetricsCommand

### 🔮 Future Enhancements

- Additional endpoints (labs, nodes, licensing)
- WebSocket support for real-time events
- Lab lifecycle management
- Node control (start/stop/wipe)
- License management integration

## Key Insights from cmlctl.py

The utility script shows:

1. **Authentication**: Uses same JWT pattern we implemented
2. **Node Operations**: Start/stop/wipe require lab_id + node_id
3. **State Polling**: Must poll node state after operations (STOPPED, STARTED, BOOTED)
4. **Lab Discovery**: Can auto-discover which lab contains a device by name
5. **Concurrent Operations**: Uses ThreadPoolExecutor for multiple devices

## Next Steps

1. **Wait for worker provisioning**:
   - Instances need public IPs assigned
   - CML service must reach AVAILABLE status
   - HTTPS endpoint must be configured

2. **Once workers are ready**:

   ```bash
   # Update worker with endpoint (if not auto-detected)
   # Then run test
   python scripts/test_cml_api.py --test-all --password <actual-password>
   ```

3. **Verify integration**:
   - Check RefreshWorkerMetricsCommand logs
   - Verify cml_* fields populated in worker state
   - Confirm OTEL metrics show labs_count

## Configuration

Current settings in `src/application/settings.py`:

```python
cml_worker_api_username: str = "admin"
cml_worker_api_password: str = "admin"  # Change in production!
```

These credentials are used by `RefreshWorkerMetricsCommand` to query CML API when worker is RUNNING + AVAILABLE.
