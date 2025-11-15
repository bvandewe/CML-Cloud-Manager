# Makefile Quick Reference

This document provides a quick reference for all available `make` commands in the System Designer project.

## 🚀 Quick Start Commands

```bash
make setup        # Complete setup (install dependencies + build UI)
make run          # Run application locally
make docker-up    # Run with Docker
make help         # Show all commands
```

## 📋 All Commands

### General

- `make help` - Display help message with all commands

### Docker Commands

| Command | Description |
|---------|-------------|
| `make docker-build` | Build Docker image |
| `make docker-dev` | Build and start Docker services (with logs) |
| `make docker-rebuild` | Rebuild services from scratch (no cache) |
| `make docker-up` | Start services in background |
| `make docker-down` | Stop and remove services |
| `make docker-restart` | Restart all services |
| `make docker-logs` | Show logs from all services |
| `make docker-logs-app` | Show logs from app service only |
| `make docker-ps` | Show running containers |
| `make docker-clean` | ⚠️ Stop services and remove volumes (deletes data!) |

### Local Development

| Command | Description |
|---------|-------------|
| `make install` | Install Python dependencies with Poetry |
| `make install-ui` | Install Node.js dependencies for UI |
| `make build-ui` | Build frontend assets |
| `make dev-ui` | Start UI development server with hot-reload |
| `make run` | Run the application locally (requires build-ui first) |
| `make run-debug` | Run with debug logging |

### Testing & Quality

| Command | Description |
|---------|-------------|
| `make test` | Run tests |
| `make test-cov` | Run tests with coverage report |
| `make lint` | Run linting checks |
| `make format` | Format code with Black |

### Cleanup

| Command | Description |
|---------|-------------|
| `make clean` | Clean up generated files and caches |
| `make clean-all` | Clean everything including Docker volumes |

### Environment Setup

| Command | Description |
|---------|-------------|
| `make setup` | Complete setup for new developers |
| `make env-check` | Check environment requirements |

### Information

| Command | Description |
|---------|-------------|
| `make status` | Show current environment status |
| `make info` | Show project information and URLs |

## 🎯 Common Workflows

### First Time Setup

```bash
# Clone the repository (if needed)
git clone <repository-url>
cd system-designer

# Check environment
make env-check

# Complete setup
make setup

# Run the application
make run
```

### Daily Development (Local)

```bash
# Start UI development server (Terminal 1)
make dev-ui

# Start backend with hot-reload (Terminal 2)
make run
```

### Daily Development (Docker)

```bash
# Start all services
make docker-up

# View logs
make docker-logs

# Stop services when done
make docker-down
```

### Before Committing

```bash
# Format code
make format

# Run linting
make lint

# Run tests
make test-cov

# Clean up
make clean
```

### Troubleshooting

```bash
# Check status
make status

# Rebuild Docker from scratch
make docker-rebuild

# Clean everything and start fresh
make clean-all
make setup
```

## 🎨 Color-Coded Output

The Makefile uses color-coded output for better readability:

- 🔵 **Blue** - Informational messages
- 🟢 **Green** - Success messages
- 🟡 **Yellow** - Warning messages
- 🔴 **Red** - Error messages

## 💡 Tips

1. **Tab Completion**: Most shells support tab completion for make targets
2. **Parallel Execution**: Some targets can be run in parallel (e.g., `dev-ui` and `run`)
3. **Environment Variables**: Commands respect `.env` file settings
4. **Safety First**: Destructive commands (like `docker-clean`) require confirmation

## 📚 Additional Resources

- See `README.md` for comprehensive documentation
- See `SETUP_COMPLETE.md` for setup summary
- Run `make info` for quick reference of URLs and test users
