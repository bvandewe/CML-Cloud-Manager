# Docker Environment

This document outlines the Docker environment for the starter application.

## Services

The `docker-compose.yml` file defines the following services:

- **app**: The main Python application.
- **ui-builder**: A service that automatically rebuilds UI assets on file changes.
- **keycloak**: The authentication server.
- **mongodb**: The database.
- **mongo-express**: A web-based MongoDB admin interface.
- **redis**: A Redis instance for session storage.
- **event-player**: A tool for event gateway/sink, visualization and replay.
- **otel-collector**: The OpenTelemetry collector for observability.

## Data Flow Diagram

The following diagram illustrates the services and their interactions within the Docker environment.

```mermaid
graph TD
    subgraph "User"
        U[User Browser]
    end

    subgraph "Docker Network"
        U -- "HTTPS" --> A(app)
        U -- "UI Assets" --> UB(ui-builder)

        A -- "Authentication" --> K(keycloak)
        A -- "Session Data" --> R(redis)
        A -- "Application Data" --> M(mongodb)
        A -- "Events" --> EP(event-player)
        A -- "Telemetry" --> OC(otel-collector)

        ME(mongo-express) -- "Admin" --> M
    end

    U -.-> ME
    U -.-> K
    U -.-> EP
```

## Usage

## Usage

1. Copy the `.env.example` to `.env` and edit it as you see fit...

2. Start the environment, run:

    ```bash
    make up
    ```

3. Check available services, run:

    ```bash
    make urls
    ```

4. Stop the environment, run:

    ```bash
    make down
    ```
