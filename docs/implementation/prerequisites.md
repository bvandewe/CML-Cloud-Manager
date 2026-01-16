# Prerequisites & Environment Setup

| Attribute | Value |
|-----------|-------|
| **Document Version** | 0.1.0 |
| **Status** | Draft |
| **Created** | 2026-01-16 |
| **Parent** | [Implementation Plan](./README.md) |

---

## 1. Infrastructure Requirements

### 1.1 etcd Cluster

**Development (Local/Docker)**

```yaml
# docker-compose.yml addition
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.11
    container_name: ccm-etcd
    environment:
      - ETCD_NAME=etcd0
      - ETCD_DATA_DIR=/etcd-data
      - ETCD_LISTEN_CLIENT_URLS=http://0.0.0.0:2379
      - ETCD_ADVERTISE_CLIENT_URLS=http://etcd:2379
      - ETCD_LISTEN_PEER_URLS=http://0.0.0.0:2380
      - ETCD_INITIAL_ADVERTISE_PEER_URLS=http://etcd:2380
      - ETCD_INITIAL_CLUSTER=etcd0=http://etcd:2380
      - ETCD_INITIAL_CLUSTER_STATE=new
      - ETCD_INITIAL_CLUSTER_TOKEN=ccm-etcd-cluster
    ports:
      - "2379:2379"
      - "2380:2380"
    volumes:
      - etcd-data:/etcd-data
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  etcd-data:
```

**Production (3-node cluster)**

- Deploy via Helm chart or managed etcd (AWS EKS, etc.)
- Minimum 3 nodes for quorum
- Persistent storage with backup strategy
- TLS encryption enabled

### 1.2 S3/MinIO for Artifact Storage

**Development (Local MinIO)**

```yaml
# docker-compose.yml addition
services:
  minio:
    image: minio/minio:latest
    container_name: ccm-minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=minioadmin
      - MINIO_ROOT_PASSWORD=minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  minio-data:
```

**Production**

- AWS S3 bucket with versioning enabled
- IAM role with least-privilege access
- Server-side encryption (SSE-S3 or SSE-KMS)

---

## 2. Python Dependencies

### 2.1 New Dependencies

Add to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
# etcd client (async support)
aioetcd3 = "^1.0.0"       # or etcd3-py with async wrapper

# S3 client (already have boto3, may need)
aiobotocore = "^2.7.0"    # Async S3 operations

# YAML processing (for lab YAML rewriting)
ruamel-yaml = "^0.18.0"   # Preserves formatting/comments

# CloudEvents SDK
cloudevents = "^1.10.0"   # CloudEvents Python SDK
```

### 2.2 Installation

```bash
# Install new dependencies
poetry add aioetcd3 aiobotocore ruamel-yaml cloudevents

# Update lock file
poetry lock

# Install all dependencies
make install
```

---

## 3. Configuration Updates

### 3.1 Settings Extensions

Add to `src/application/settings.py`:

```python
# etcd Configuration
ETCD_HOST: str = "localhost"
ETCD_PORT: int = 2379
ETCD_USERNAME: str | None = None
ETCD_PASSWORD: str | None = None
ETCD_CA_CERT: str | None = None  # Path to CA cert for TLS
ETCD_CERT_KEY: str | None = None  # Path to client cert
ETCD_CERT_CERT: str | None = None  # Path to client key

# S3/MinIO Configuration
ARTIFACT_STORAGE_ENDPOINT: str = "http://localhost:9000"
ARTIFACT_STORAGE_ACCESS_KEY: str = "minioadmin"
ARTIFACT_STORAGE_SECRET_KEY: str = "minioadmin"
ARTIFACT_STORAGE_BUCKET: str = "lablet-artifacts"
ARTIFACT_STORAGE_REGION: str = "us-east-1"
ARTIFACT_STORAGE_USE_SSL: bool = False

# Scheduler Configuration
SCHEDULER_ENABLED: bool = True
SCHEDULER_RECONCILE_INTERVAL_SECONDS: int = 30
SCHEDULER_LEADER_LEASE_TTL_SECONDS: int = 15
SCHEDULER_LEAD_TIME_MINUTES: int = 35  # Worker boot + lab instantiation

# Resource Controller Configuration
CONTROLLER_ENABLED: bool = True
CONTROLLER_RECONCILE_INTERVAL_SECONDS: int = 30
CONTROLLER_SCALE_DOWN_GRACE_PERIOD_MINUTES: int = 30

# Worker Templates
WORKER_TEMPLATES_CONFIG_PATH: str = "config/worker-templates.yaml"

# CloudEvents Configuration
CLOUDEVENTS_SINK_URL: str | None = None  # URL to send CloudEvents
CLOUDEVENTS_SOURCE: str = "ccm"
```

### 3.2 Environment Variables

Add to `.env.example`:

```bash
# etcd
ETCD_HOST=etcd
ETCD_PORT=2379

# Artifact Storage (MinIO/S3)
ARTIFACT_STORAGE_ENDPOINT=http://minio:9000
ARTIFACT_STORAGE_ACCESS_KEY=minioadmin
ARTIFACT_STORAGE_SECRET_KEY=minioadmin
ARTIFACT_STORAGE_BUCKET=lablet-artifacts

# Scheduler
SCHEDULER_ENABLED=true
SCHEDULER_LEAD_TIME_MINUTES=35

# Resource Controller
CONTROLLER_ENABLED=true

# CloudEvents
CLOUDEVENTS_SINK_URL=http://cloud-streams:8080/events
```

---

## 4. Worker Template Configuration

### 4.1 Template File Structure

Create `config/worker-templates.yaml`:

```yaml
# Worker Template Definitions
# These are seeded into MongoDB on application startup

templates:
  - name: "personal-standard"
    description: "Standard worker with Personal CML license"
    instance_type: "m5zn.metal"
    capacity:
      cpu_cores: 48
      memory_gb: 192
      storage_gb: 500
    license_type: "PERSONAL"
    max_nodes: 20
    ami_pattern: "CML-2.9.*"
    regions:
      - "us-east-1"
      - "us-west-2"
    port_range:
      start: 2000
      end: 9999
    drain_timeout_hours: 4
    tags:
      Environment: "production"
      ManagedBy: "ccm"

  - name: "enterprise-large"
    description: "Large worker with Enterprise CML license"
    instance_type: "m5zn.metal"
    capacity:
      cpu_cores: 48
      memory_gb: 192
      storage_gb: 1000
    license_type: "ENTERPRISE"
    max_nodes: 500
    ami_pattern: "CML-2.9.*"
    regions:
      - "us-east-1"
    port_range:
      start: 2000
      end: 9999
    drain_timeout_hours: 6
    tags:
      Environment: "production"
      ManagedBy: "ccm"
      LicenseType: "enterprise"
```

---

## 5. Development Environment Validation

### 5.1 Validation Script

Create `scripts/validate-prerequisites.sh`:

```bash
#!/bin/bash
set -e

echo "🔍 Validating Lablet Resource Manager prerequisites..."

# Check etcd
echo -n "Checking etcd... "
if etcdctl --endpoints=http://localhost:2379 endpoint health &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED - etcd not accessible"
    exit 1
fi

# Check MinIO/S3
echo -n "Checking MinIO... "
if curl -s http://localhost:9000/minio/health/live &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED - MinIO not accessible"
    exit 1
fi

# Check MongoDB
echo -n "Checking MongoDB... "
if mongosh --eval "db.adminCommand('ping')" &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED - MongoDB not accessible"
    exit 1
fi

# Check Redis
echo -n "Checking Redis... "
if redis-cli ping &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED - Redis not accessible"
    exit 1
fi

echo ""
echo "✅ All prerequisites validated successfully!"
```

### 5.2 Makefile Additions

Add to `Makefile`:

```makefile
# Lablet Resource Manager targets
.PHONY: validate-prereqs start-lablet-infra

validate-prereqs:
 @bash scripts/validate-prerequisites.sh

start-lablet-infra:
 docker-compose -f docker-compose.yml -f docker-compose.lablet.yml up -d etcd minio
 @echo "Waiting for services to be healthy..."
 @sleep 5
 @$(MAKE) validate-prereqs
```

---

## 6. Checklist

### Pre-Implementation Checklist

- [ ] etcd container added to docker-compose.yml
- [ ] MinIO container added to docker-compose.yml
- [ ] Python dependencies added to pyproject.toml
- [ ] Settings class extended with new configuration
- [ ] Environment variables documented in .env.example
- [ ] Worker templates configuration file created
- [ ] Validation script created and tested
- [ ] Team has reviewed and understood architecture decisions (ADRs)

### Post-Setup Verification

- [ ] `make dev` starts all services including etcd and MinIO
- [ ] `make validate-prereqs` passes all checks
- [ ] etcd UI accessible (if using etcd-browser or similar)
- [ ] MinIO console accessible at http://localhost:9001
- [ ] Existing tests still pass (`make test`)

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-01-16 | Architecture Team | Initial draft |
