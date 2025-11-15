# Running the Application

Once you have installed the dependencies, you can run the application using Docker Compose.

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

## Server Binding Configuration

For security, the Uvicorn server binds to `127.0.0.1` by default. If you need to expose the API outside of your machine, explicitly override the binding address:

```bash
export APP_HOST=0.0.0.0
export APP_PORT=8080
```

Only use `0.0.0.0` when you understand the networking implications and have secured the environment.
