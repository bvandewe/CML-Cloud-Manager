# Multi-Service Architecture Refactoring

**Date:** 2025-01-20
**Status:** COMPLETED

## Overview

The CML Cloud Manager has been refactored from a monolithic application into a multi-service architecture with three independent microservices. This enables better separation of concerns, independent scaling, and prepares the codebase for the Lablet Resource Manager implementation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CML Cloud Manager                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Control Plane API  │  │    Scheduler    │  │   Controller    │  │
│  │    (Port 8020)      │  │   (Port 8081)   │  │   (Port 8082)   │  │
│  │                     │  │                 │  │                 │  │
│  │  • REST API         │  │  • Leader       │  │  • Leader       │  │
│  │  • Bootstrap 5 UI   │  │    Election     │  │    Election     │  │
│  │  • MongoDB Writer   │  │  • Placement    │  │  • Reconcile    │  │
│  │  • Auth (Keycloak)  │  │    Algorithm    │  │  • Auto-Scale   │  │
│  │  • SSE Events       │  │  • Queue Watch  │  │  • Cloud SPI    │  │
│  └─────────┬───────────┘  └────────┬────────┘  └────────┬────────┘  │
│            │                       │                     │           │
│            └───────────────────────┼─────────────────────┘           │
│                                    │                                 │
│                        ┌───────────┴───────────┐                     │
│                        │        etcd           │                     │
│                        │    (Port 2379)        │                     │
│                        │  • State Store        │                     │
│                        │  • Leader Election    │                     │
│                        │  • Watch Triggers     │                     │
│                        └───────────────────────┘                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
cml-cloud-manager/
├── src/
│   ├── control-plane-api/     # Main API + UI service
│   │   ├── api/               # REST controllers
│   │   ├── application/       # Commands, queries, services
│   │   ├── domain/            # Entities, repositories (interfaces)
│   │   ├── infrastructure/    # Session stores, adapters
│   │   ├── integration/       # MongoDB, AWS, CML clients
│   │   ├── observability/     # OTEL instrumentation
│   │   ├── ui/                # Bootstrap 5 SPA (Parcel)
│   │   ├── tests/             # pytest test suite
│   │   ├── main.py            # FastAPI app factory
│   │   ├── Dockerfile         # Multi-stage with UI build
│   │   ├── Makefile           # Service-specific commands
│   │   ├── pyproject.toml     # Poetry dependencies
│   │   └── pytest.ini         # Test configuration
│   │
│   ├── scheduler/             # LabletInstance placement service
│   │   ├── application/       # Settings, scheduler service
│   │   ├── domain/            # (Future: scheduling domain logic)
│   │   ├── integration/       # etcd client, API client
│   │   ├── tests/             # pytest test suite
│   │   ├── main.py            # Service entry point
│   │   ├── Dockerfile
│   │   ├── Makefile
│   │   ├── pyproject.toml
│   │   └── pytest.ini
│   │
│   └── controller/            # Resource reconciliation service
│       ├── application/       # Settings, controller service
│       ├── domain/            # (Future: controller domain logic)
│       ├── integration/       # Cloud provider SPI, etcd client
│       │   └── providers/     # AWS EC2 implementation
│       ├── tests/             # pytest test suite
│       ├── main.py            # Service entry point
│       ├── Dockerfile
│       ├── Makefile
│       ├── pyproject.toml
│       └── pytest.ini
│
├── docker-compose.yml         # All services orchestration
├── Makefile                   # Root orchestration commands
├── ccm.code-workspace         # VS Code multi-root workspace
└── ...
```

## Service Responsibilities

### Control Plane API (`src/control-plane-api/`)

**Purpose:** Central API gateway and UI, single writer to MongoDB

- REST API endpoints for all CRUD operations
- Bootstrap 5 SPA with Server-Side Events (SSE)
- Keycloak OAuth2/OIDC authentication
- MongoDB as source of truth
- Background worker for existing functionality

**Port:** 8020 (HTTP), 5680 (Debug)

### Scheduler (`src/scheduler/`)

**Purpose:** LabletInstance placement decisions

- Leader election via etcd
- Watches etcd for PENDING instances
- Placement algorithm (bin-packing with resource constraints)
- Updates instance state via Control Plane API

**Port:** 8081 (Health), 5681 (Debug)

**Key Components:**

- `SchedulerService`: Main scheduling loop with leader election
- `EtcdClient`: etcd state store wrapper
- `ControlPlaneClient`: HTTP client for API calls

### Controller (`src/controller/`)

**Purpose:** Resource reconciliation and auto-scaling

- Leader election via etcd
- Reconciliation loop (actual vs. desired state)
- Cloud Provider SPI (Service Provider Interface)
- AWS EC2 implementation for worker provisioning
- Scale-up/scale-down decisions

**Port:** 8082 (Health), 5682 (Debug)

**Key Components:**

- `ControllerService`: Main reconciliation loop
- `CloudProviderInterface`: Abstract cloud provider interface
- `AwsEc2Provider`: AWS EC2 implementation

## Development Commands

### Root Level (Orchestration)

```bash
# Docker operations
make up              # Start all services
make down            # Stop all services
make dev             # Build and run with logs
make logs            # All service logs
make logs-api        # Control plane API logs
make logs-scheduler  # Scheduler logs
make logs-controller # Controller logs
make urls            # Show all service URLs

# All services
make install-all     # Install deps for all services
make test-all        # Run all tests
make lint-all        # Lint all services
make setup           # Complete setup for new developers
```

### Per-Service Commands

```bash
# Control Plane API
make api-install     # Install Python deps
make api-install-ui  # Install Node.js deps
make api-build-ui    # Build frontend
make api-run         # Run locally
make api-test        # Run tests
make api-lint        # Run linting

# Scheduler
make scheduler-install
make scheduler-run
make scheduler-test
make scheduler-lint

# Controller
make controller-install
make controller-run
make controller-test
make controller-lint
```

## VS Code Workspace

The workspace file (`ccm.code-workspace`) includes:

- 📂 Folders for all three microservices
- 🚀 Launch configurations for running/debugging each service
- ⚙️ Tasks for common operations
- 🔌 Extension recommendations

### Launch Configurations

- `control-plane-api: Run` - Run API locally
- `scheduler: Run` - Run scheduler locally
- `controller: Run` - Run controller locally
- `All Services (Local)` - Run all three locally
- `All Services (Attach Docker)` - Attach debugger to Docker containers

## Docker Compose Services

| Service | Port(s) | Description |
|---------|---------|-------------|
| `control-plane-api` | 8020, 5680 | Main API + UI |
| `scheduler` | 8081, 5681 | Placement service |
| `controller` | 8082, 5682 | Reconciliation service |
| `worker` | 5683 | Legacy background worker |
| `etcd` | 2379, 2380 | State store |
| `mongodb` | 8022 | Primary database |
| `keycloak` | 8021 | Auth server |
| `redis` | 6379 | Session store |
| `event-player` | 8024 | Event visualization |
| `otel-collector` | 4317, 4318 | Observability |

## Key Design Decisions

### AD-1: Independent Dependencies

Each microservice has its own:

- `pyproject.toml` with Poetry
- `Dockerfile` with independent builds
- `Makefile` for service-specific commands
- `.venv` (created by Poetry)

**Rationale:** Enables independent versioning, deployment, and scaling.

### AD-2: Leader Election Pattern

Both scheduler and controller implement leader election via etcd.

**Rationale:** Ensures only one instance performs critical operations, preventing conflicts.

### AD-3: Cloud Provider SPI

Controller uses an abstract `CloudProviderInterface` with AWS EC2 implementation.

**Rationale:** Enables future support for other cloud providers (GCP, Azure) without changing controller logic.

### AD-4: Control Plane as Single Writer

Only the Control Plane API writes to MongoDB. Scheduler and Controller communicate via API.

**Rationale:** Prevents data conflicts, simplifies consistency, enables audit logging at single point.

## Migration Notes

### What Changed

1. All `src/` code moved to `src/control-plane-api/`
2. `tests/` and `pytest.ini` moved to `src/control-plane-api/`
3. New `src/scheduler/` and `src/controller/` services created
4. Root `docker-compose.yml` updated with all services
5. Root `Makefile` updated with orchestration commands
6. `ccm.code-workspace` updated with new folders

### What Didn't Change

1. All imports in control-plane-api remain the same (relative imports)
2. API endpoints remain the same
3. UI functionality unchanged
4. Test suite unchanged (just moved)

## Next Steps

1. **Implement real etcd client** - Replace mock with `etcd3-py`
2. **Add placement algorithm** - Bin-packing in scheduler
3. **Add reconciliation logic** - Actual vs desired state in controller
4. **Add health endpoints** - HTTP health checks for scheduler/controller
5. **Add integration tests** - Cross-service communication tests
6. **Update documentation** - MkDocs architecture diagrams

## References

- [Lablet Resource Manager Implementation Plan](docs/implementation-plan/)
- [Architecture Decision Records](notes/)
- [Neuroglia Framework](https://github.com/neuroglia-io/framework-python)
