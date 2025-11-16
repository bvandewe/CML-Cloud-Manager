# CML Worker API Endpoints Summary

## Overview

This document summarizes the REST API endpoints added to `workers_controller.py` for managing CML Worker lifecycle operations.

## New Endpoints

### 1. Create CML Worker

- **Method**: `POST`
- **Path**: `/region/{aws_region}/workers`
- **Auth**: `lablets-admin` role required
- **Request Body**: `CreateCMLWorkerRequest`
  - `name`: Worker instance name
  - `instance_type`: EC2 instance type
  - `ami_id`: AMI identifier
  - `ami_name`: AMI name
  - `cml_version`: CML version to deploy
- **Command**: `CreateCMLWorkerCommand`
- **Status**: ✅ Implemented

### 2. Terminate CML Worker

- **Method**: `DELETE`
- **Path**: `/region/{aws_region}/workers/{worker_id}`
- **Auth**: `lablets-admin` role required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Command**: `TerminateCMLWorkerCommand`
- **Status**: ✅ Implemented

### 3. Start CML Worker

- **Method**: `POST`
- **Path**: `/region/{aws_region}/workers/{worker_id}/start`
- **Auth**: `lablets-admin` role required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Command**: `StartCMLWorkerCommand`
- **Status**: ✅ Implemented

### 4. Stop CML Worker

- **Method**: `POST`
- **Path**: `/region/{aws_region}/workers/{worker_id}/stop`
- **Auth**: `lablets-admin` role required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Command**: `StopCMLWorkerCommand`
- **Status**: ✅ Implemented

### 5. Update CML Worker Tags

- **Method**: `POST`
- **Path**: `/region/{aws_region}/workers/{worker_id}/tags`
- **Auth**: `lablets-admin` role required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Request Body**: `UpdateCMLWorkerTagsRequest`
  - `tags`: Dictionary of tag key-value pairs
- **Command**: `UpdateCMLWorkerTagsCommand`
- **Status**: ✅ Implemented

### 6. Get CML Worker Status

- **Method**: `GET`
- **Path**: `/region/{aws_region}/workers/{worker_id}/status`
- **Auth**: Valid token required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Command**: `UpdateCMLWorkerStatusCommand`
- **Status**: ✅ Implemented

### 7. Register License (Placeholder)

- **Method**: `POST`
- **Path**: `/region/{aws_region}/workers/{worker_id}/license`
- **Auth**: `lablets-admin` role required
- **Path Parameters**:
  - `worker_id`: CML Worker UUID
- **Request Body**: `RegisterLicenseRequest`
  - `license_token`: License token string
- **Command**: Not yet implemented
- **Status**: ⏳ Placeholder (returns HTTP 501)

## Files Modified

### 1. `src/api/models/cml_worker_requests.py`

Created new request DTOs with Pydantic v2:

- `CreateCMLWorkerRequest`
- `UpdateCMLWorkerTagsRequest`
- `RegisterLicenseRequest`

### 2. `src/api/models/__init__.py`

Exported all request models for easy import.

### 3. `src/api/controllers/workers_controller.py`

- Added 7 new endpoint methods
- Updated imports to use new commands
- Added `worker_id_annotation` for UUID path parameters
- Maintained consistent authentication patterns

## Application Commands

All commands are fully implemented in `src/application/commands/`:

1. ✅ `CreateCMLWorkerCommand` - Provisions new EC2 instance
2. ✅ `StartCMLWorkerCommand` - Starts stopped instance
3. ✅ `StopCMLWorkerCommand` - Stops running instance
4. ✅ `TerminateCMLWorkerCommand` - Terminates and deletes instance
5. ✅ `UpdateCMLWorkerTagsCommand` - Manages instance tags
6. ✅ `UpdateCMLWorkerStatusCommand` - Syncs status from AWS

## Authentication & Authorization

- **Read Operations** (GET): Require valid JWT token via `validate_token`
- **Write Operations** (POST, DELETE): Require `lablets-admin` role via `has_role("lablets-admin")`

## Next Steps

1. Implement `RegisterCMLWorkerLicenseCommand` for license registration
2. Add response models for better OpenAPI documentation
3. Add integration tests for new endpoints
4. Update API documentation with examples

## Notes

- All commands follow CQRS pattern with CommandHandler base class
- Commands return `OperationResult` wrapped by `self.process()`
- Worker ID is UUID-based, not EC2 instance ID
- Commands don't require `aws_region` parameter as worker aggregate stores region
- All operations emit domain events via CloudEventBus
