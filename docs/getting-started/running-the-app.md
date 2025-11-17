# Running the Application

Once you have installed the dependencies, you can run the application and supporting services (database, auth, telemetry) using Docker Compose.

## Running with Docker

The `Makefile` provides several commands to manage the application services.

- **Start all services**:

    ```bash
    make up
    ```

    This will start the application, database, and other services in the background.

- **View service URLs**:

    ```bash
    make urls
    ```

    This command displays the URLs for the running services, including the main application, API docs, and Keycloak.

- **View logs**:

    ```bash
    make logs-app
    ```

    This will show the logs for the main application service.

- **Stop all services**:

    ```bash
    make down
    ```

    This will stop and remove all running containers.

## Accessing the Application

- **Web Application**: [http://localhost:8020](http://localhost:8020)
- **API Docs (Swagger UI)**: [http://localhost:8020/api/docs](http://localhost:8020/api/docs)
- **Keycloak Admin Console**: [http://localhost:8021](http://localhost:8021)
  - **Username**: `admin`
  - **Password**: `admin`

### Real-Time Status (SSE)

Open the Workers page to verify the Server-Sent Events stream:

1. Look for the connection status badge (top-right of the list or header area).
2. States:
    - `Live`: Connected and receiving events.
    - `Connecting`: Attempting reconnection (exponential backoff up to 30s).
    - `Disconnected`: Browser will continue retrying until success.
3. Trigger an event by creating or updating a worker; observe:
    - Toast notification (e.g. "Worker created", "Status updated").
    - Automatic inline refresh of metrics/status without manual reload.

Architecture details: [Real-Time Updates](../architecture/realtime-updates.md)

### Background Labs Refresh Job

The system runs a scheduled labs refresh task (on startup + every 30 minutes) to ensure the UI reflects current lab/instance state. Related SSE events (`worker.labs.updated`) propagate changes instantly to connected clients.

You can confirm the job is running via the application logs (`make logs-app`) or by observing periodic lab / instance updates in the UI without manual action.

### Quick Verification Checklist

```text
[ ] make up succeeded
[ ] Workers page loads
[ ] SSE badge shows Live
[ ] Creating a worker shows toast + list updates
[ ] Labs refresh events appear (optional: inspect logs)
```

## Server Binding Configuration

For security, the Uvicorn server binds to `127.0.0.1` by default. If you need to expose the API outside of your machine, explicitly override the binding address:

```bash
export APP_HOST=0.0.0.0
export APP_PORT=8080
```

Only use `0.0.0.0` when you understand the networking implications and have secured the environment.

## Troubleshooting

- **Badge stuck on Connecting**: Check that the backend process is running and the SSE endpoint (`/ui/events/stream` or configured path) is reachable; inspect browser console for network errors.
- **No toasts on worker changes**: Ensure domain events are firing; confirm backend logs for event dispatch; verify the browser tab has permission and is still connected.
- **Labs not refreshing**: Confirm scheduler started (look for startup log line) and wait for a 30-minute cycle or trigger manual lab updates if available.

## Next Steps

- Explore the feature matrix: [Features](../features.md)
- Dive deeper into architecture: [Background Scheduling](../architecture/background-scheduling.md) & [Real-Time Updates](../architecture/realtime-updates.md)
- Add a custom event handler or metric: see observability guides in `Observability` section.
