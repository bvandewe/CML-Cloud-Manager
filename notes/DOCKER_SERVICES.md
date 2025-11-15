# Docker Compose Services - Complete Stack

## Services Overview

The System Designer application now includes a complete development stack with all supporting services.

## 🚀 Services

### Application Services

#### 📱 System Designer Application

- **Port:** 8020
- **Debug Port:** 5678
- **URL:** http://localhost:8020
- **API Docs:** http://localhost:8020/api/docs
- Hot-reload enabled for development

#### 🎨 UI Builder (Parcel)

- Automatically rebuilds frontend assets on file changes
- Node.js 20 Alpine
- Watches `src/ui/` directory

### Database Services

#### 🗄️ MongoDB Database

- **Port:** 27017 (configurable via `MONGODB_PORT`)
- **Version:** 6.0.21
- **URL:** mongodb://localhost:27017
- **Default Credentials:**
  - Username: `root`
  - Password: `neuroglia123`
  - Database: `neuroglia`

#### 📊 MongoDB Express (Admin UI)

- **Port:** 8081 (configurable via `MONGODB_EXPRESS_PORT`)
- **URL:** http://localhost:8081
- **Authentication:** Disabled (development only)
- Web-based MongoDB administration interface

### Identity & Access Management

#### 🔐 Keycloak (SSO/OAuth2)

- **Port:** 8090 (configurable via `KEYCLOAK_PORT`)
- **Version:** 22.0.5
- **URL:** http://localhost:8090
- **Admin Console:** http://localhost:8090/admin
- **Default Credentials:**
  - Username: `admin`
  - Password: `admin`
- **Realm:** system-designer
- Uses H2 database (persisted in volume)
- Import realm configurations on startup

### Event Management

#### 🎬 Event Player

- **Port:** 8085 (configurable via `EVENT_PLAYER_PORT`)
- **Version:** v0.4.4
- **URL:** http://localhost:8085
- Event visualization and replay service
- **Features:**
  - Event generation and publishing
  - Event replay capabilities
  - OAuth/OIDC authentication with Keycloak
  - Role-based access control
- **Roles:**
  - Admin: `manager`
  - Operator: `chef`
  - User: `driver`

### Observability

#### 🔭 OpenTelemetry Collector

- **Ports:**
  - 4317: OTLP gRPC receiver
  - 4318: OTLP HTTP receiver
  - 8888: Prometheus metrics
  - 13133: Health check endpoint
- **Version:** 0.110.0
- Receives, processes, and exports telemetry data
- Configuration: `deployment/otel-collector-config.yaml`

## 🌐 Port Summary

| Service | Port | URL |
|---------|------|-----|
| **System Designer App** | 8020 | http://localhost:8020 |
| **API Docs** | 8020 | http://localhost:8020/api/docs |
| **Debug Port** | 5678 | - |
| **Keycloak** | 8021 | http://localhost:8021 |
| **MongoDB** | 8022 | mongodb://localhost:8022|
| **MongoDB Express** | 8023 | http://localhost:8023 |
| **Event Player** | 8024 | http://localhost:8024 |
| **OTEL gRPC** | 4317 | - |
| **OTEL HTTP** | 4318 | - |
| **OTEL Metrics** | 8888 | - |
| **OTEL Health** | 13133 | - |

## 📝 Environment Variables

All ports and credentials are configurable via environment variables in `.env`:

```bash
APP_PORT=8020
KEYCLOAK_PORT=8021
MONGODB_PORT=8022
MONGODB_EXPRESS_PORT=8023
EVENT_PLAYER_PORT=8024
OTEL_COLLECTOR_GRPC_PORT=4317
OTEL_COLLECTOR_HTTP_PORT=4318
OTEL_COLLECTOR_METRICS_PORT=8888
OTEL_COLLECTOR_HEALTH_PORT=13133
```

## 🚀 Usage

### Start All Services

```bash
make docker-up
# or
docker compose up -d
```

### Start Specific Services

```bash
docker compose up -d mongodb mongo-express
docker compose up -d keycloak
docker compose up -d event-player
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f keycloak
docker compose logs -f event-player
```

### Stop Services

```bash
make docker-down
# or
docker compose down
```

### Rebuild and Restart

```bash
make docker-rebuild
```

## 🔗 Service Dependencies

```
app
├── mongodb (database)
├── keycloak (authentication)
└── ui-builder (frontend assets)

mongo-express
└── mongodb

event-player
└── keycloak

otel-collector
└── (no dependencies)
```

## 💾 Persistent Volumes

- `mongodb_data` - MongoDB database files
- `keycloak_data` - Keycloak H2 database and configurations

## 🌐 Network

All services communicate via the `system-designer-net` bridge network.

## 🔍 Service Access URLs

After starting with `make docker-up`:

1. **System Designer Application**
   - App: http://localhost:8020
   - API Docs: http://localhost:8020/api/docs
   - Login: admin/test, manager/test, user/test

2. **MongoDB Admin**
   - URL: http://localhost:8023
   - No authentication required

3. **Keycloak Admin**
   - URL: http://localhost:8021
   - Login: admin/admin

4. **Event Player**
   - URL: http://localhost:8024
   - Requires authentication via Keycloak

## 🛠️ Development Features

- **Hot Reload:** Application and UI automatically rebuild on changes
- **Debug Support:** Python debugger on port 5678
- **Health Checks:** OpenTelemetry health endpoint on port 13133
- **Observability:** Full telemetry stack with OTEL collector
- **Admin UIs:** MongoDB Express and Keycloak admin consoles

## 📚 Additional Resources

- MongoDB: https://www.mongodb.com/docs/
- Keycloak: https://www.keycloak.org/documentation
- OpenTelemetry: https://opentelemetry.io/docs/
- Event Player: https://github.com/bvandewe/events-player

---

**Complete Stack:** ✅ All services configured
**Ports:** ✅ Configurable via environment variables
**Persistence:** ✅ Volumes for data retention
**Ready to Run:** ✅ `make docker-up`
