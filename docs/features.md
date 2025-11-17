# Key Features

## 🏗️ Architecture & Design Patterns

- **[Domain-Driven Design (DDD)](https://en.wikipedia.org/wiki/Domain-driven_design)**: Clean architecture with clear domain boundaries
- **[CQRS Pattern](https://microservices.io/patterns/data/cqrs.html)**: Command Query Responsibility Segregation for scalable operations
- **Domain Events**: Rich event model for worker lifecycle & telemetry (broadcast via SSE)
- **SubApp Pattern**: Clean separation between API and UI concerns
- **Repository Pattern**: Pluggable data access with in-memory and [MongoDB](https://www.mongodb.com/) implementations

## 🔐 Authentication & Security

- **[OAuth2](https://auth0.com/docs)/[OIDC](https://openid.net/connect/)**: Modern authentication standards
- **[Keycloak](https://www.keycloak.org/) Integration**: Enterprise-grade identity management
- **Backend-for-Frontend (BFF)**: Secure session-based authentication for UI
- **JWT Bearer Tokens**: API authentication with RS256 signature verification
- **[RBAC](https://en.wikipedia.org/wiki/Role-based_access_control)**: Role-based access control at the application layer
- **[Redis](https://redis.io/) Session Store**: Distributed sessions for horizontal scaling in Kubernetes

## 🎨 Frontend & UI

- **[Parcel Bundler](https://parceljs.org/)**: Zero-config build tool with hot module replacement
- **[Nunjucks Templates](https://mozilla.github.io/nunjucks/)**: Powerful templating engine
- **[Bootstrap 5](https://getbootstrap.com/docs/5.0/getting-started/introduction/)**: Modern responsive UI framework
- **[SCSS](https://sass-lang.com/)**: CSS preprocessing for maintainable styles
- **[Vanilla ES6](https://developer.mozilla.org/en-US/docs/Web/JavaScript)**: Modern JavaScript modules without heavy frameworks
- **Single Page Application (SPA)**: Smooth user experience with dynamic content

## 🔧 Backend & Infrastructure

- **[FastAPI](https://fastapi.tiangolo.com/)**: High-performance async web framework
- **[Neuroglia](https://bvandewe.github.io/pyneuro/)**: DDD/CQRS framework with Mediator pattern
- **[MongoDB](https://www.mongodb.com/)** with **[Motor](https://motor.readthedocs.io/)**: Async document database
- **[Mongo Express](https://github.com/mongo-express/mongo-express)**: Web-based database management
- **[CloudEvents](https://cloudevents.io/)**: Standardized event format with [Player](https://bvandewe.github.io/events-player/) for debugging
- **[OpenTelemetry](https://opentelemetry.io/)**: Metrics & distributed tracing for workers and background jobs
- **OTEL Collector**: Integrated pipeline for metrics/traces export
- **Server-Sent Events (SSE)**: Real-time push of worker metrics, status, labs, lifecycle events

## 🔄 Real-Time & Monitoring

- **SSE Endpoint**: `/api/events/stream` with heartbeat + reconnection support
- **Event Types**: `worker.created`, `worker.status.updated`, `worker.metrics.updated`, `worker.labs.updated`, `worker.terminated`
- **Labs Refresh Job**: Recurrent global job (`labs-refresh-global`) runs every 30 minutes + initial startup run
- **Metrics Polling**: Configurable interval for AWS/CML metrics collection
- **Status Badge**: Live connection indicator in Workers UI

## 🐳 Development & Deployment

- **[Docker](https://www.docker.com/)** + **[Docker Compose](https://docs.docker.com/compose/)**: Complete local development stack
- **[Poetry](https://python-poetry.org/)**: Modern Python dependency management
- **[pytest](https://docs.pytest.org/)**: Comprehensive test suite with 98% coverage
- **[Black](https://github.com/psf/black)** + **[Ruff](https://github.com/astral-sh/ruff)**: Code formatting and linting
- **[MkDocs Material](https://squidfunk.github.io/mkdocs-material/)**: Beautiful documentation site
- **Makefile Automation**: Simple commands for common development tasks
- **GitHub Template**: Project renaming utility (`scripts/rename_project.py`) for quick customization

## About Neuroglia-Python

**Neuroglia-python** is a framework for building applications based on Domain-Driven Design (DDD) and Command Query Responsibility Segregation (CQRS). It provides composable building blocks (Mediator, Repositories, Mapping, Observability) enabling testable modular architecture.

- **Framework Documentation**: https://bvandewe.github.io/pyneuro/
