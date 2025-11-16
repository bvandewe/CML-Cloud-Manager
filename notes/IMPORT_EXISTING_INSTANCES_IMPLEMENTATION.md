# Import Existing EC2 Instances Feature - Implementation Summary

## ✅ Implementation Complete

Successfully implemented the ability to import existing EC2 instances as CML Workers without creating new instances.

---

## Files Created

### 1. Domain Layer

- **File**: `src/domain/events/cml_worker.py`
- **Added**: `CMLWorkerImportedDomainEvent`
  - Tracks when existing instances are imported into the system
  - Contains: instance details, AMI info, IP addresses, creation metadata

### 2. Application Layer

- **File**: `src/application/commands/import_cml_worker_command.py`
- **Classes**:
  - `ImportCMLWorkerCommand` - Command with search criteria (instance_id, ami_id, or ami_name)
  - `ImportCMLWorkerCommandHandler` - Orchestrates discovery, validation, and registration

### 3. API Layer

- **File**: `src/api/models/cml_worker_requests.py`
- **Added**: `ImportCMLWorkerRequest`
  - Validation: Requires at least one search criterion
  - Supports: instance_id (direct), ami_id (search), ami_name (pattern)
  - Includes: Pydantic validators and comprehensive examples

### 4. Test Suite

- **File**: `tests/application/test_import_cml_worker_command.py`
- **Coverage**:
  - Command creation tests
  - Handler success scenarios (by instance_id, by ami_id)
  - Error scenarios (no criteria, not found, already registered)
  - Factory method tests (state mapping)

---

## Files Modified

### 1. Domain Entity

- **File**: `src/domain/entities/cml_worker.py`
- **Changes**:
  - Added import for `CMLWorkerImportedDomainEvent`
  - Added event handler: `on(CMLWorkerImportedDomainEvent)`
    - Maps EC2 instance states → CMLWorkerStatus
    - Sets all worker attributes from imported instance
  - Added static factory method: `import_from_existing_instance()`
    - Creates worker without going through standard `__init__`
    - Emits `CMLWorkerImportedDomainEvent`
    - Returns fully initialized worker

### 2. API Controller

- **File**: `src/api/controllers/workers_controller.py`
- **Changes**:
  - Added import for `ImportCMLWorkerRequest` and `ImportCMLWorkerCommand`
  - Added endpoint: `POST /api/workers/region/{aws_region}/workers/import`
    - Requires `admin` role
    - Accepts: instance_id, ami_id, or ami_name
    - Returns: CMLWorkerInstanceDto

### 3. Module Exports

- **File**: `src/application/commands/__init__.py`
  - Exported `ImportCMLWorkerCommand` and `ImportCMLWorkerCommandHandler`
- **File**: `src/api/models/__init__.py`
  - Exported `ImportCMLWorkerRequest`

---

## API Endpoint Details

### POST `/api/workers/region/{aws_region}/workers/import`

**Authentication**: Requires JWT token with `admin` role

**Request Body** (one of the following):

```json
// Option 1: Import by Instance ID (Direct lookup)
{
  "aws_instance_id": "i-0abcdef1234567890",
  "name": "imported-worker-01"
}

// Option 2: Import by AMI ID (Search)
{
  "ami_id": "ami-0c55b159cbfafe1f0",
  "name": "imported-worker-02"
}

// Option 3: Import by AMI Name (Pattern search)
{
  "ami_name": "cml-worker-ami-2.7.0",
  "name": "imported-worker-03"
}
```

**Response** (201 Created):

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "aws_instance_id": "i-0abcdef1234567890",
  "aws_region": "us-east-1",
  "instance_name": "imported-worker-01",
  "ami_id": "ami-0c55b159cbfafe1f0",
  "ami_name": "cml-worker-ami",
  "instance_type": "c5.2xlarge",
  "instance_state": "running",
  "security_group_ids": [],
  "subnet_id": "",
  "public_ip": null,
  "private_ip": null,
  "tags": {}
}
```

**Error Responses**:

- `400 Bad Request`: No search criteria provided
- `400 Bad Request`: No matching instance found
- `400 Bad Request`: Instance already registered
- `401 Unauthorized`: Missing or invalid JWT token
- `403 Forbidden`: User lacks `admin` role

---

## Implementation Highlights

### ✅ Feature Completeness

1. **Domain Event Sourcing**: Full audit trail via `CMLWorkerImportedDomainEvent`
2. **Validation**: Prevents duplicate imports
3. **Flexible Search**: Three ways to find instances (ID, AMI ID, AMI name)
4. **State Mapping**: Correctly maps EC2 states → CML Worker status
5. **Error Handling**: Comprehensive exception handling with user-friendly messages

### ✅ Best Practices

1. **CQRS Pattern**: Command separates mutation from queries
2. **DDD**: Factory method on aggregate for domain logic
3. **Tracing**: OpenTelemetry spans for observability
4. **Type Safety**: Full type hints throughout
5. **Testing**: Unit tests for all critical paths

### ✅ Security

1. **Authorization**: Requires `admin` role
2. **Audit Trail**: Tracks `created_by` user
3. **Validation**: Prevents malicious input via Pydantic

### ✅ Observability

1. **Logging**: Info/error logs at key decision points
2. **Tracing**: 4 spans per import operation:
   - `discover_ec2_instance`
   - `check_duplicate_worker`
   - `create_worker_from_import`
   - `save_imported_worker`
3. **Attributes**: Rich span attributes for debugging

---

## Usage Examples

### Example 1: Import by Instance ID (Direct)

```bash
curl -X POST \
  'http://localhost:8030/api/workers/region/us-east-1/workers/import' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "aws_instance_id": "i-0abcdef1234567890",
    "name": "imported-prod-worker"
  }'
```

### Example 2: Import by AMI ID (Search)

```bash
curl -X POST \
  'http://localhost:8030/api/workers/region/us-west-2/workers/import' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "ami_id": "ami-0c55b159cbfafe1f0"
  }'
```

### Example 3: Import by AMI Name (Pattern)

```bash
curl -X POST \
  'http://localhost:8030/api/workers/region/eu-west-1/workers/import' \
  -H 'Authorization: Bearer YOUR_JWT_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "ami_name": "cml-worker-ami-2.7.0",
    "name": "eu-imported-worker"
  }'
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer                              │
│  POST /api/workers/region/{region}/workers/import           │
│  → WorkersController.import_existing_cml_worker()           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Application Layer                          │
│  ImportCMLWorkerCommand → ImportCMLWorkerCommandHandler     │
│  1. Validate search criteria                                │
│  2. Discover instance in AWS (via AwsEc2Client)             │
│  3. Check for duplicates (CMLWorkerRepository)              │
│  4. Create worker aggregate (import factory method)         │
│  5. Persist (emit events)                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Layer                             │
│  CMLWorker.import_from_existing_instance()                  │
│  → Emits: CMLWorkerImportedDomainEvent                      │
│  → Event Handler: Maps EC2 state → CML status              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                Infrastructure Layer                         │
│  AwsEc2Client: get_instance_details() / list_instances()    │
│  CMLWorkerRepository: add_async()                           │
│  MongoDB: Persistence                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## What's Different from CreateCMLWorkerCommand?

| Aspect | CreateCMLWorkerCommand | ImportCMLWorkerCommand |
|--------|------------------------|------------------------|
| **Purpose** | Provision NEW EC2 instance | Register EXISTING instance |
| **AWS Operation** | `ec2.create_instances()` | `ec2.describe_instances()` |
| **Domain Event** | `CMLWorkerCreatedDomainEvent` | `CMLWorkerImportedDomainEvent` |
| **Factory Method** | `CMLWorker.__init__()` | `CMLWorker.import_from_existing_instance()` |
| **Cost** | Creates billable resource | No AWS cost |
| **Use Case** | Deploy new CML worker | Adopt existing infrastructure |

---

## Benefits

✅ **Adoption Path**: Gradually migrate existing CML deployments
✅ **No Duplication**: Import manually-created instances
✅ **Cost Effective**: Reuse existing infrastructure
✅ **Flexibility**: Multiple search methods (ID, AMI)
✅ **Safety**: Duplicate prevention
✅ **Audit Trail**: Full event sourcing
✅ **Consistency**: Manage all workers through one system

---

## IAM Permissions Required

**No additional permissions needed!** The import feature uses existing permissions:

- ✅ `ec2:DescribeInstances` - Already granted
- ✅ `ec2:DescribeTags` - Already granted

---

## Testing

### Run Unit Tests

```bash
pytest tests/application/test_import_cml_worker_command.py -v
```

### Test Coverage

- ✅ Command creation (3 test cases)
- ✅ Handler success paths (2 test cases)
- ✅ Handler error paths (3 test cases)
- ✅ Factory method (2 test cases)
- **Total**: 10 comprehensive test cases

---

## Next Steps (Optional Enhancements)

### Phase 3: Discovery Query

Add a query to list unregistered instances:

- `ListUnregisteredInstancesQuery`
- Endpoint: `GET /api/workers/region/{region}/unregistered`
- Use case: "Show me all AWS instances not yet imported"

### Future Enhancements

1. **Batch Import**: Import multiple instances at once
2. **Dry Run Mode**: Preview what would be imported
3. **Auto-Discovery**: Scheduled job to auto-import new instances
4. **Import History**: Track all import operations
5. **Rollback**: Ability to un-import (mark as external)

---

## Documentation Updated

- ✅ Feature design doc: `notes/IMPORT_EXISTING_INSTANCES_FEATURE.md`
- ✅ Implementation summary: `notes/IMPORT_EXISTING_INSTANCES_IMPLEMENTATION.md` (this file)
- 📋 TODO: Update user guide with import instructions
- 📋 TODO: Update OpenAPI/Swagger docs

---

## Status: ✅ READY FOR TESTING

The import feature is fully implemented and ready for:

1. Restart the application service
2. Verify endpoint appears in OpenAPI docs
3. Test with real AWS instances
4. Deploy to staging environment
