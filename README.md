# Starter App - Neuroglia WebApplication

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Neuroglia](https://img.shields.io/badge/Neuroglia-0.6.6-purple.svg)](https://github.com/neuroglia-io/python-framework)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://bvandewe.github.io/starter-app/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-pytest-orange.svg)](https://docs.pytest.org/)
[![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen.svg)](htmlcov/index.html)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg?logo=docker)](docker-compose.yml)
[![Keycloak](https://img.shields.io/badge/auth-Keycloak-orange.svg?logo=keycloak)](https://www.keycloak.org/)
[![MongoDB](https://img.shields.io/badge/database-MongoDB-green.svg?logo=mongodb)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/sessions-Redis-red.svg?logo=redis)](https://redis.io/)

An opinionated Neuroglia FastAPI template showcasing multi-subapp architecture (API + UI), CQRS, RBAC, OAuth2/OIDC, and pluggable infrastructure:

- 🎨 **SubApp Pattern**: Clean separation between API and UI concerns
- 🔐 **OAuth2/OIDC Authentication**: Keycloak integration with Backend-for-Frontend pattern
- 🔴 **Redis Session Store**: Distributed sessions for horizontal scaling in Kubernetes
- 🛡️ **RBAC**: Role-based access control at the application layer
- 📋 **CQRS Pattern**: Command Query Responsibility Segregation
- 🎯 **Clean Architecture**: Domain-driven design with clear boundaries

![Starter App demo](./docs/assets/starter-app_v0.1.0.gif)

## 🏗️ Architecture

This application follows the **Simple UI** sample pattern from Neuroglia, implementing:

- **API SubApp** (`/api`): RESTful JSON endpoints with JWT authentication
- **UI SubApp** (`/`): Bootstrap 5 SPA with Parcel bundler
- **Domain Layer**: Task entities with repository pattern
- **Application Layer**: CQRS commands/queries with RBAC handlers
- **Integration Layer**: In-memory and MongoDB (motor) repositories (ready for PostgreSQL/Redis/...)

### Project Structure

```
starter-app/
├── src/
│   ├── main.py                      # FastAPI app factory entry point
│   ├── api/                         # API sub-app (mounted at /api)
│   │   ├── controllers/             # Route controllers
│   │   ├── dependencies.py          # Shared dependency helpers (auth, user)
│   │   └── services/                # API-specific service utilities (e.g. OpenAPI config)
│   ├── application/                 # Application layer (CQRS, mapping, settings)
│   │   ├── settings.py
│   │   ├── commands/                # Write operations
│   │   ├── queries/                 # Read operations
│   │   ├── events/                  # Domain/application events (placeholder)
│   │   ├── mapping/                 # Object mapping profiles
│   │   └── services/                # Cross-cutting services (logger, etc.)
│   ├── domain/                      # Pure domain model
│   │   ├── entities/                # Aggregate/entity classes (task, etc.)
│   │   └── repositories/            # Repository interfaces (ports)
│   ├── infrastructure/              # Technical adapters implementing ports
│   │   └── session_store.py         # Session store implementations (in-memory/redis)
│   ├── integration/                 # Concrete adapters / in-memory repos
│   │   └── models/
│   │   └── repositories/
│   ├── observability/               # Metrics, tracing, logging integration points
│   │   └── metrics.py
│   ├── ui/                          # Frontend build + controller sub-app
│   │   ├── controllers/             # UI route(s)
│   │   ├── src/                     # Parcel source (scripts, styles)
│   │   ├── package.json             # Frontend dependencies
├── tests/                           # Pytest suites (unit/integration)
│   └── test_rename_integrity.py     # Ensures no leftover starter branding post-rename
├── scripts/
│   └── rename_project.py            # Automated project rebranding utility
├── docs/                            # MkDocs documentation source
├── deployment/                      # Deployment & Keycloak realm config assets
├── notes/                           # Design / architecture scratchpad docs
├── static/                          # Published frontend bundle (built UI assets)
├── Makefile                         # Developer automation commands
├── docker-compose.yml               # Local service orchestration
├── Dockerfile                       # Application container build
├── pyproject.toml                   # Python dependencies & tool config (Poetry)
└── README.md                        # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Node.js 20+ (for UI build)
- Docker & Docker Compose (optional)

### Quick Setup (Recommended)

Use the Makefile for easy setup and management:

```bash
# Complete setup for new developers
make setup

# Run locally
make run

# Or run with Docker
make up

# See all available commands
make help
```

### Manual Local Development

1. **Install Python dependencies:**

   ```bash
   poetry install
   ```

2. **Install frontend dependencies and build UI:**

   ```bash
   make install-ui
   make build-ui
   ```

3. **Run the application:**

   ```bash
   make run
   ```

4. **Access the application:**
   - Application: http://localhost:8000/
   - API Documentation: http://localhost:8000/api/docs

### Frontend Development Mode

For hot-reload during UI development:

```bash
# Terminal 1: Watch and rebuild frontend assets
make dev-ui

# Terminal 2: Start backend with hot-reload
make run
```

### Docker Development

Run the complete stack with Docker Compose using the **Makefile** (recommended):

```bash
# Copy environment variables (first time only)
cp .env.example .env

# Build and start services
make up

# View logs
make logs

# Stop services
make down

# Rebuild from scratch
make rebuild
```

Or use docker-compose directly:

```bash
# Start all services
docker-compose up

# Or run in background
docker-compose up -d
```

This will start:

- ✅ Starter App App (http://localhost:8020)
- ✅ MongoDB (localhost:8022) and Mongo Express (http://localhost:8023)
- ✅ Keycloak (http://localhost:8021)
- ✅ OpenTelemetry Collector
- ✅ UI Builder (auto-rebuild)
- ✅ Redis (localhost:6379)
- ✅ Event Player (http://localhost:8024)

## 👥 Test Users

The application includes test users with different roles:

| Username | Password | Role | Access Level |
|----------|----------|------|--------------|
| admin | test | admin | All tasks |
| manager | test | manager | Department tasks |
| user | test | user | Only assigned tasks |

See [deployment/keycloak/starter-app-realm-export.json](./deployment/keycloak/starter-app-realm-export.json)

## 🔐 Authentication & RBAC

### JWT Authentication

- **Stateless**: No server-side sessions required
- **Token Storage**: localStorage (not cookies)
- **Expiration**: 24 hours (configurable)
- **Claims**: username, user_id, roles, department

### Role-Based Access Control

Authorization happens in the **application layer** (handlers), not controllers:

- **Admin**: Can view and manage all tasks, can delete tasks
- **Manager**: Can view tasks in their department
- **User**: Can only view their assigned tasks

Example RBAC logic in `GetTasksQueryHandler`:

```python
if "admin" in user_roles:
    tasks = await self.task_repository.get_all_async()
elif "manager" in user_roles:
    tasks = await self.task_repository.get_by_department_async(department)
else:
    tasks = await self.task_repository.get_by_assignee_async(user_id)
```

## 🛠️ Configuration

### Environment Variables

Create a `.env` file (or use `.env.example`):

```bash
# Application server
APP_HOST=127.0.0.1         # Override only if you must expose the API externally
APP_PORT=8080

# Keycloak OAuth2/OIDC
KEYCLOAK_SERVER_URL=http://keycloak:8080
KEYCLOAK_REALM=starter-app
KEYCLOAK_CLIENT_ID=portal-web-app

# Redis Session Storage (for production horizontal scaling)
REDIS_ENABLED=false          # Set to true for production
REDIS_URL=redis://redis:6379/0
REDIS_KEY_PREFIX=session:

# Database
MONGODB_PASSWORD=neuroglia123
```

### Redis Session Store

The application supports two session storage backends:

**Development (default)**: `InMemorySessionStore`

- ⚡ Fast, no external dependencies
- ⚠️ Sessions lost on restart
- ❌ Not suitable for multiple instances

**Production**: `RedisSessionStore`

- 🔴 Distributed, shared across pods
- 📈 Enables horizontal scaling in Kubernetes
- 💪 Sessions survive pod restarts
- ⏰ Auto-expiring via Redis TTL

To enable Redis for production:

```bash
# In .env file
REDIS_ENABLED=true
```

See `notes/REDIS_SESSION_STORE.md` for detailed documentation on:

- Kubernetes deployment strategies
- Redis configuration options
- Testing horizontal scaling
- Security best practices

### VS Code Setup

The project includes VS Code settings for:

- ✅ Automatic Poetry venv activation
- ✅ Python formatter (Black)
- ✅ Import organization
- ✅ Pytest integration

## 📚 Documentation

### API Documentation

Once running, visit http://localhost:8020/api/docs for interactive API documentation.

### Project Documentation

Comprehensive documentation is available in the `docs/` directory and online:

- **Online**: https://bvandewe.github.io/starter-app
- **Local**: Run `make docs-serve` and visit http://127.0.0.1:8000

#### Documentation Topics

- [**Getting Started**](https://bvandewe.github.io/starter-app/getting-started/installation/) - How to install and run the application.
- [**Architecture**](https://bvandewe.github.io/starter-app/architecture/overview/) - CQRS pattern, dependency injection, design patterns
- [**Security**](https://bvandewe.github.io/starter-app/security/authentication-flows/) - Dual auth system (session + JWT), OAuth2/OIDC, RBAC
- [**Development**](https://bvandewe.github.io/starter-app/development/makefile-reference/) - Makefile reference, workflow, testing
- [**Deployment**](https://bvandewe.github.io/starter-app/deployment/docker-environment/) - Docker environment, deployment, configuration
- [**Troubleshooting**](https://bvandewe.github.io/starter-app/troubleshooting/common-issues/) - Common issues, known bugs, solutions

#### Documentation Commands

```bash
# Install documentation dependencies
make docs-install

# Serve documentation locally with live reload
make docs-serve

# Build documentation site
make docs-build

# Deploy to GitHub Pages (maintainers only)
make docs-deploy
```

### Key Endpoints

#### Authentication

- `POST /api/auth/login` - Login and get JWT token

#### Tasks

- `GET /api/tasks` - Get tasks (role-filtered)
- `POST /api/tasks` - Create new task
- `PUT /api/tasks/{task_id}` - Update task (with authorization)

All task endpoints require `Authorization: Bearer {token}` header.

## �️ Makefile Commands

The project includes a comprehensive Makefile for easy development workflow management:

### Docker Commands

- `make build` - Build Docker image
- `make dev` - Build and start Docker services with logs
- `make rebuild` - Rebuild services from scratch (no cache)
- `make up` - Start services in background
- `make down` - Stop and remove services
- `make restart` - Restart all services
- `make logs` - Show logs from all services
- `make clean` - Stop services and remove volumes ⚠️

### Local Development Commands

- `make setup` - Complete setup for new developers (install + build)
- `make install` - Install Python dependencies with Poetry
- `make install-ui` - Install Node.js dependencies
- `make build-ui` - Build frontend assets
- `make dev-ui` - Start UI dev server with hot-reload
- `make run` - Run application locally with auto-reload
- `make run-debug` - Run with debug logging

### Testing & Quality Commands

- `make test` - Run tests
- `make test-cov` - Run tests with coverage report
- `make lint` - Run linting checks
- `make format` - Format code with Black

### Utility Commands

- `make clean` - Clean up caches and generated files
- `make clean-all` - Clean everything including Docker volumes
- `make status` - Show current environment status
- `make info` - Display project information and URLs
- `make env-check` - Check environment requirements
- `make help` - Display all available commands

**Example Workflow:**

```bash
# New developer setup
make setup

# Start local development
make run

# Or use Docker
make docker-up
make docker-logs

# Stop Docker services
make docker-down
```

## �🔗 Related Documentation

- [Neuroglia Python Framework](https://bvandewe.github.io/pyneuro/)
- [Simple UI Sample](https://bvandewe.github.io/pyneuro/samples/simple-ui/)
- [RBAC Guide](https://bvandewe.github.io/pyneuro/guides/rbac-authorization/)
- [OAuth & JWT Reference](https://bvandewe.github.io/pyneuro/references/oauth-oidc-jwt/)

## 🧪 Testing

```bash
# Run tests
poetry run pytest
```

## 🪝 Pre-Commit Hooks

Automated formatting, linting, and security checks run before you commit to keep the codebase consistent.

### What's Included

- Trailing whitespace / EOF / merge conflict checks
- Black (Python formatting) + isort (imports)
- Flake8 (lint) and optional Ruff/extra rules if enabled
- Prettier for JS/TS/CSS/HTML/JSON/YAML/Markdown
- Markdownlint (auto-fix basic style issues)
- Yamllint (with relaxed config)
- Bandit (Python security scanning)
- Detect-Secrets (prevents committing secrets)

### Setup

```bash
poetry add --group dev pre-commit
poetry run pre-commit install --install-hooks
poetry run pre-commit run --all-files  # Run on entire repo once
```

If you later update hooks:

```bash
poetry run pre-commit autoupdate
```

### Enforcing Consistency

CI should run:

```bash
poetry run pre-commit run --all-files
```

### DCO Reminder

Pre-commit does not enforce DCO; ensure commits include:

```
Signed-off-by: Your Name <you@example.com>
```

Use `git commit -s` to auto-add this line.


## 🔁 Rebranding / Forking as a New Project

You can turn this repository into a new project quickly without manually hunting for every
`starter-app` occurrence.

### Option 1: Built-in Rename Script (Recommended)

Run a dry run first:

```bash
python scripts/rename_project.py --new-name "Acme Tasks" --dry-run
```

Apply the changes:

```bash
python scripts/rename_project.py --new-name "Acme Tasks"
```

This will replace variants:

- `starter-app` (slug)
- `starter_app` (snake)
- `Starter App` (title)
- `StarterApp` (Pascal)
- `STARTER_APP` (UPPER_SNAKE)
- `Starter App API`

Optional flags:

```bash
# Also adjust Keycloak realm/client identifiers (you must reconfigure Keycloak manually afterward)
python scripts/rename_project.py --new-name "Acme Tasks" --update-keycloak

# Limit to certain folders
python scripts/rename_project.py --new-name "Acme Tasks" --include src docs

# Override derived name styles explicitly
python scripts/rename_project.py --new-name "Acme Tasks" \
    --slug acme-tasks --snake acme_tasks --pascal AcmeTasks --upper ACME_TASKS
```

Post-rename checklist:

1. Rename the repository folder and remote (e.g., `git remote set-url origin ...`).
2. Adjust Docker image tags / compose service names if needed.
3. Update Keycloak realm + client IDs if `--update-keycloak` was used.
4. Search for any remaining branding (e.g., README examples, docs URLs).
5. Run tests: `poetry run pytest -q`.
6. Rebuild UI assets: `make build-ui`.

### Option 2: GitHub Template Repo

Using GitHub's built‑in Template feature lets you create a clean copy of the repository without forking the full commit history. Workflow:

1. Maintainer: In the original repo, go to Settings → General → Enable "Template repository".
2. Consumer: Click "Use this template" (instead of Fork). GitHub scaffolds a brand‑new repo with the current contents (no upstream remote linkage).
3. In your new repo clone, run the rename script (Option 1) to apply your branding and identifiers.
4. Update any secrets / realms (Keycloak) and run tests.

Why combine both? The template feature handles repository creation & initial history isolation; the rename script performs systematic text/style replacements so you don't miss lingering `starter-app` variants. If you skip the script, manual edits are error‑prone (especially mixed case variants and service identifiers).

### Option 3: Cookiecutter (Future)

You can evolve this into a Cookiecutter template for parameter prompts. A future `cookiecutter.json` might include: app_name, slug, docker_image, keycloak_realm, enable_redis, etc.

### Verify No Leftover Names

Run the rename integrity test (after the script has been applied and test added):

```bash
poetry run pytest -k rename_integrity -q
```

If it fails, it lists files containing residual references.

### Run with coverage

```bash
poetry run pytest --cov=. --cov-report=html
```

## 📦 Deployment

### Production Checklist

- [ ] Change `JWT_SECRET_KEY` to a strong random value
- [ ] Set `DEBUG=False` in settings
- [ ] Configure proper database (MongoDB/PostgreSQL)
- [ ] Set up Keycloak for production OAuth/OIDC
- [ ] Configure CORS for production domains
- [ ] Set up proper logging and monitoring
- [ ] Use environment-specific `.env` files

### Docker Production Build

```bash
docker build -t starter-app:latest .
docker run -p 8000:8000 starter-app:latest
```

## 🤝 Contributing

This project follows the Neuroglia Python Framework patterns. See the [development guide](https://bvandewe.github.io/pyneuro/guides/local-development/) for more information.

## 📄 License

Licensed under the Apache License, Version 2.0. See `LICENSE` for the full text.

Copyright © 2025 Starter App Contributors.

You may not use this project except in compliance with the License. Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

---

Built with ❤️ using [Neuroglia Python Framework](https://github.com/bvandewe/pyneuro)
