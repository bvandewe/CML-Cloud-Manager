# Documentation

This directory contains comprehensive documentation for the Starter App, organized by topic for easy reference.

## 📚 Documentation Structure

### [Security](./security/)

Security, authentication and authorization system documentation:

- **[Authentication Flows](./security/authentication-flows.md)** - Dual authentication architecture (session cookies + JWT)
- **[Authorization](./security/authorization.md)** - OAuth2/OIDC concepts and RBAC implementation
- **[Session Management](./security/session-management.md)** - Redis session store implementation
- **Keycloak Integration** - OAuth2/OIDC setup and configuration

**Start Here**: If implementing authentication/authorization or troubleshooting security issues

### [Architecture](./architecture/)

Application architecture patterns and design:

- **[CQRS Pattern](./architecture/cqrs-pattern.md)** - Command/Query separation with Mediator
- **[Dependency Injection](./architecture/dependency-injection.md)** - Neuroglia DI system
- **Controller Design** - API controller patterns
- **Repository Pattern** - Data access layer

**Start Here**: If understanding or extending the application architecture

### [Frontend](./frontend/)

Frontend build process and JavaScript architecture:

- **[Build Process](./frontend/build-process.md)** - Nunjucks + Parcel pipeline
- **Frontend Architecture** - ES6 module structure
- **Component Design** - UI patterns and best practices

**Start Here**: If working on UI or troubleshooting frontend builds

### [Infrastructure](./infrastructure/)

Development environment and deployment:

- **[Docker Environment](./infrastructure/docker-environment.md)** - Complete Docker Compose stack
- **Python Environment** - Local development setup
- **MongoDB Configuration** - Database setup
- **Observability** - OpenTelemetry tracing

**Start Here**: If setting up development environment or deploying

### [Troubleshooting](./troubleshooting/)

Known issues and solutions:

- **[Common Issues](./troubleshooting/common-issues.md)** - Frequent problems and fixes
- **[Neuroglia MongoDB Bug](./troubleshooting/neuroglia-mongo-import.md)** - Framework import issue
- **Debugging Guide** - Diagnostic tools and techniques

**Start Here**: If something isn't working

### [Development](./development/)

Development workflows and guides:

- **[Makefile Reference](./development/makefile-reference.md)** - All make commands
- **Development Workflow** - Daily development process
- **Testing Guide** - Unit and integration testing
- **Contributing** - Code style and PR guidelines

**Start Here**: If joining the project or need quick command reference

## 🚀 Quick Start Paths

### New Developer Setup

1. [Docker Environment](./infrastructure/docker-environment.md) - Get services running
2. [Makefile Reference](./development/makefile-reference.md) - Learn commands
3. [Architecture Overview](./architecture/cqrs-pattern.md) - Understand patterns
4. [Development Workflow](./development/workflow.md) - Daily process

### Implementing Features

1. [CQRS Pattern](./architecture/cqrs-pattern.md) - Create commands/queries
2. [Dependency Injection](./architecture/dependency-injection.md) - Wire up dependencies
3. [Security](./security/authentication-flows.md) - Protect endpoints
4. [Frontend Build](./frontend/build-process.md) - Add UI

### Debugging Issues

1. [Common Issues](./troubleshooting/common-issues.md) - Check known problems
2. [Docker Environment](./infrastructure/docker-environment.md) - Service debugging
3. [Build Process](./frontend/build-process.md) - Frontend issues

## 📖 Documentation Standards

All documentation follows these principles:

✅ **Portable** - No development timeline, just how it works
✅ **Practical** - Code examples and commands
✅ **Organized** - Topic-based, not chronological
✅ **Complete** - Enough context to understand
✅ **Maintained** - Updated with code changes

## 🔍 Finding Information

### By Topic

- **Authentication/Authorization** → `authentication/`
- **Application Design** → `architecture/`
- **UI/Frontend** → `frontend/`
- **Environment Setup** → `infrastructure/`
- **Problems/Bugs** → `troubleshooting/`
- **Commands/Workflow** → `development/`

### By Task

- **First time setup** → `infrastructure/docker-environment.md`
- **Add API endpoint** → `architecture/cqrs-pattern.md`
- **Protect endpoint** → `authentication/overview.md`
- **Build UI** → `frontend/build-process.md`
- **Deploy** → `infrastructure/`
- **Debug** → `troubleshooting/common-issues.md`

### By Component

- **FastAPI/Controllers** → `architecture/`
- **Commands/Queries** → `architecture/cqrs-pattern.md`
- **MongoDB** → `architecture/dependency-injection.md`
- **Redis/Sessions** → `security/session-management.md`
- **Keycloak** → `security/`
- **Docker** → `infrastructure/docker-environment.md`
- **Parcel/Build** → `frontend/build-process.md`

## 🛠️ Using This Starter App

This is a template/starter application. When adapting for your project:

### Keep

✅ Authentication patterns (session + JWT)
✅ CQRS architecture
✅ Dependency injection setup
✅ Frontend build pipeline
✅ Docker development environment
✅ Observability foundation

### Customize

🔧 Domain entities (replace Task with your models)
🔧 UI components and styling
🔧 Keycloak realm and roles
🔧 Database schema
🔧 API endpoints

### Extend

➕ Additional authentication providers
➕ More command/query handlers
➕ Event sourcing
➕ Background jobs
➕ API versioning
➕ Rate limiting

## 📝 Contributing to Documentation

When adding new features, please:

1. **Update existing docs** if behavior changes
2. **Add new docs** for new patterns/components
3. **Keep examples current** with actual code
4. **Follow structure** - put docs in appropriate directory
5. **Link related docs** - help readers navigate

### Documentation Template

```markdown
# Feature Name

Brief description of what this is.

## Purpose

Why this exists and what problem it solves.

## How It Works

High-level explanation with diagrams if helpful.

## Implementation

Code examples and configuration.

## Usage

How to use in practice.

## Troubleshooting

Common issues and solutions.

## Related Documentation

Links to related docs.
```

## 🔗 External Resources

### Frameworks

- [Neuroglia Framework](https://github.com/neuroglia-io/python-framework) - Application framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Motor](https://motor.readthedocs.io/) - Async MongoDB driver

### Tools

- [Keycloak](https://www.keycloak.org/documentation) - Identity and access management
- [Docker Compose](https://docs.docker.com/compose/) - Multi-container orchestration
- [Parcel](https://parceljs.org/) - Web application bundler

### Patterns

- [CQRS](https://martinfowler.com/bliki/CQRS.html) - Command Query Responsibility Segregation
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Layered architecture
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html) - Data access abstraction

## 📄 License

See [LICENSE](../LICENSE) in project root.

## 🤝 Support

For questions or issues:

1. Check [Common Issues](./troubleshooting/common-issues.md)
2. Review relevant topic documentation
3. Search existing GitHub issues
4. Create new issue with details

---

**Last Updated**: January 2025
**Documentation Version**: 1.0
**Starter App Version**: 1.0
