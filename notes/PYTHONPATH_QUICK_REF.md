# Python Path Configuration - Quick Reference

## TLDR

All imports are relative to `./src`:

```python
from domain.entities import Task, User
from application.commands import LoginCommand
from settings import settings
```

## Running the Application

### Local Development

```bash
make run           # Starts with PYTHONPATH=./src
```

### Docker

```bash
make docker-up     # PYTHONPATH configured in container
```

## Configuration Files

- ✅ `.env` - PYTHONPATH=./src
- ✅ `.vscode/settings.json` - Auto-sets PYTHONPATH in VS Code
- ✅ `Makefile` - Runs from src/ with PYTHONPATH=.
- ✅ `Dockerfile` - WORKDIR /app/src + PYTHONPATH=/app/src
- ✅ `docker-compose.yml` - PYTHONPATH=/app/src
- ✅ `start.sh` - exports PYTHONPATH=./src

## Import Examples

```python
# Domain layer
from domain.entities import Task, User
from domain.repositories import TaskRepository, UserRepository

# Application layer
from application.commands import LoginCommand, CreateTaskCommand
from application.queries import GetTasksQuery

# API layer
from api.controllers import AuthController, TasksController

# UI layer
from ui.controllers import UIController

# Integration layer
from integration.repositories import InMemoryTaskRepository

# Settings
from settings import settings
```

## Verification

```bash
cd src
PYTHONPATH=. poetry run python -c "from domain.entities import Task; print('✅ OK')"
```

---

See `PYTHONPATH_CONFIGURED.md` for complete documentation.
