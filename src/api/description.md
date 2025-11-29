## Overview

The CML Cloud Manager API provides programmatic access to manage AWS EC2-based Cisco Modeling Lab (CML) workers. This RESTful API enables automated provisioning, monitoring, and lifecycle management of CML infrastructure at scale.

**Key Features:**

- 🚀 Automated CML worker provisioning and lifecycle management
- 📊 Real-time monitoring with metrics collection from AWS CloudWatch and CML native telemetry
- 🔄 Server-Sent Events (SSE) for live status updates
- 🧪 Lab management (create, start, stop, wipe, delete)
- ⚡ Idle detection with automatic pause/resume capabilities
- 🔐 Dual authentication: OAuth2/OIDC (Keycloak) + JWT bearer tokens
- 🛡️ Role-based access control (RBAC) with admin/user permissions

## Authentication

This API supports **two authentication methods** to serve both browser-based applications and programmatic clients:

### 1. OAuth2 Authorization Code Flow (Browser)

For web applications and Swagger UI:

- Click "Authorize" button in Swagger UI
- Login via Keycloak SSO
- Access token automatically included in requests via httpOnly cookies
- Session managed server-side (Redis/in-memory)

### 2. JWT Bearer Token (Programmatic)

For API clients, scripts, and automation:

```bash
# Obtain token from Keycloak
TOKEN=$(curl -X POST "https://keycloak.example.com/realms/cml-cloud-manager/protocol/openid-connect/token" \
  -d "client_id=cml-cloud-manager-public" \
  -d "grant_type=password" \
  -d "username=user@example.com" \
  -d "password=your-password" | jq -r .access_token)

# Use token in API requests
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/api/workers
```

## Architecture

Built on **Neuroglia Framework** with:

- **CQRS Pattern**: Separate command (write) and query (read) operations
- **Event Sourcing**: Domain events for state changes with CloudEvents integration
- **Repository Pattern**: Abstracted data access with MongoDB persistence
- **Background Jobs**: APScheduler for recurring metrics collection and health checks
- **Clean Architecture**: Domain-driven design with clear layer boundaries

## Worker Lifecycle

CML workers follow this state machine:

```
pending → provisioning → running → stopping → stopped → terminated
                ↓           ↓
              error     paused (idle detection)
```

**Key States:**

- `pending`: Worker creation initiated
- `provisioning`: AWS EC2 instance launching
- `running`: Worker active and ready for labs
- `paused`: Automatically paused due to idle timeout
- `stopped`: Manually stopped or scheduled shutdown
- `terminated`: Permanently removed

## Monitoring & Metrics

Workers are continuously monitored via:

- **AWS CloudWatch**: CPU, memory, network, disk I/O metrics
- **CML Native API**: Lab-level resource utilization and node status
- **Idle Detection**: Configurable timeout with automatic pause

Metrics are collected at configurable intervals (default: 5 minutes) and exposed via:

- REST endpoints for historical data
- Server-Sent Events (SSE) for real-time updates
- Worker details modal in UI

## Rate Limits & Quotas

- API requests: No hard limits (consider implementing for production)
- Worker provisioning: Limited by AWS account quotas
- Concurrent lab operations: Limited by CML worker capacity
- SSE connections: One per authenticated user session

## API Versioning

Current version: **v1** (no version prefix in URLs)

Breaking changes will be introduced with new major versions (e.g., `/api/v2/workers`).

## Support & Documentation

- **Full Documentation**: [MkDocs Site](https://bvandewe.github.io/cml-cloud-manager/)
- **Source Code**: [GitHub Repository](https://github.com/bvandewe/CML-Cloud-Manager)
- **Issues**: [GitHub Issues](https://github.com/bvandewe/CML-Cloud-Manager/issues)

## Getting Started

1. Authenticate using OAuth2 or obtain a JWT token
2. List available workers: `GET /api/workers`
3. Create a new worker: `POST /api/workers/region/{region}/workers`
4. Monitor worker status: Subscribe to SSE at `GET /api/events/stream`
5. Manage labs: Use `/api/workers/region/{region}/workers/{worker_id}/labs` endpoints

**Admin-only operations** require the `admin` role in Keycloak.
