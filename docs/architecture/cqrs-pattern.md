# CQRS Architecture with Neuroglia

This application implements Command Query Responsibility Segregation (CQRS) using the Neuroglia framework's Mediator pattern.

## What is CQRS?

CQRS separates operations that modify data (Commands) from operations that read data (Queries), providing clearer separation of concerns and better scalability.

### Commands (Write Operations)

- **Purpose**: Modify system state
- **Return**: Void or simple success indicator
- **Examples**: CreateTask, UpdateTask, DeleteTask
- **Side Effects**: Yes (database writes, events)

### Queries (Read Operations)

- **Purpose**: Retrieve data
- **Return**: Data objects
- **Examples**: GetTasks, GetTaskById
- **Side Effects**: No (read-only)

## Architecture Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                      Controller (API Layer)                     │
│                   Receives HTTP request                         │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Mediator (Neuroglia)                        │
│            Routes command/query to handler                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
       ┌───────────────────────┐  ┌──────────────────┐
       │   Command Handler     │  │  Query Handler   │
       │  (Business Logic)     │  │  (Data Retrieval)│
       └───────────────────────┘  └──────────────────┘
                    │                     │
                    ▼                     ▼
       ┌───────────────────────┐  ┌──────────────────┐
       │      Repository       │  │    Repository    │
       │   (Write to DB)       │  │   (Read from DB) │
       └───────────────────────┘  └──────────────────┘
```

## Project Structure

### Self-Contained Modules

Each command/query lives in a single file with its handler:

```
src/application/
├── commands/
│   ├── __init__.py
│   ├── create_task_command.py     # CreateTaskCommand + Handler
│   ├── update_task_command.py     # UpdateTaskCommand + Handler
│   └── delete_task_command.py     # DeleteTaskCommand + Handler
└── queries/
    ├── __init__.py
    └── get_tasks_query.py         # GetTasksQuery + Handler
```

**Benefits:**

- High cohesion - request and handler together
- Easy to find - one file per operation
- Simple imports - just import what you need

## Command Example

### CreateTaskCommand

File: `src/application/commands/create_task_command.py`

```python
from dataclasses import dataclass
from neuroglia.core import OperationResult
from neuroglia.mediation import Command, CommandHandler
from domain.repositories import TaskRepository
from domain.entities import Task

@dataclass
class CreateTaskCommand(Command[OperationResult]):
    """Command to create a new task."""
    title: str
    description: str
    priority: str = "medium"
    user_info: dict | None = None

class CreateTaskCommandHandler(CommandHandler[CreateTaskCommand, OperationResult]):
    """Handle task creation."""

    def __init__(self, task_repository: TaskRepository):
        super().__init__()
        self.task_repository = task_repository

    async def handle_async(self, command: CreateTaskCommand) -> OperationResult:
        """Handle create task command."""
        task = Task(
            title=command.title,
            description=command.description,
            priority=command.priority,
            status="pending"
        )
        if command.user_info:
            task.created_by = command.user_info.get("user_id")
            task.department = command.user_info.get("department")

        saved_task = await self.task_repository.add_async(task)

        return self.ok({
            "id": str(saved_task.id),
            "title": saved_task.title,
        })
```

## Query Example

### GetTasksQuery

File: `src/application/queries/get_tasks_query.py`

```python
from dataclasses import dataclass
from neuroglia.core import OperationResult
from neuroglia.mediation import Query, QueryHandler
from domain.repositories import TaskRepository

@dataclass
class GetTasksQuery(Query[OperationResult]):
    """Query to retrieve tasks with role-based filtering."""
    user_info: dict

class GetTasksQueryHandler(QueryHandler[GetTasksQuery, OperationResult]):
    """Handle task retrieval with role-based filtering."""

    def __init__(self, task_repository: TaskRepository):
        super().__init__()
        self.task_repository = task_repository

    async def handle_async(self, query: GetTasksQuery) -> OperationResult:
        """Handle get tasks query with RBAC logic."""
        user_roles = query.user_info.get("roles", [])

        if "admin" in user_roles:
            tasks = await self.task_repository.get_all_async()
        elif "manager" in user_roles:
            department = query.user_info.get("department")
            tasks = await self.task_repository.get_by_department_async(department) if department else []
        else:
            user_id = query.user_info.get("sub") or query.user_info.get("user_id")
            tasks = await self.task_repository.get_by_assignee_async(user_id) if user_id else []

        task_dtos = [{"id": str(t.id), "title": t.title, "status": t.status} for t in tasks]
        return self.ok(task_dtos)
```

## Controller Usage

### Sending Commands/Queries

Controllers use the Mediator to dispatch requests:

```python
from classy_fastapi.decorators import get, post
from fastapi import Depends
from neuroglia.mvc import ControllerBase
from pydantic import BaseModel

from api.dependencies import get_current_user
from application.commands import CreateTaskCommand
from application.queries import GetTasksQuery

class CreateTaskRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"

class TasksController(ControllerBase):

    @post("/")
    async def create_task(
        self,
        request: CreateTaskRequest,
        user: dict = Depends(get_current_user)
    ):
        # Create command
        command = CreateTaskCommand(
            title=request.title,
            description=request.description,
            priority=request.priority,
            user_info=user
        )

        # Send via mediator
        result = await self.mediator.execute_async(command)
        return self.process(result)

    @get("/")
    async def get_tasks(
        self,
        user: dict = Depends(get_current_user)
    ):
        # Create query
        query = GetTasksQuery(user_info=user)

        # Send via mediator
        result = await self.mediator.execute_async(query)
        return self.process(result)
```

## Dependency Injection

### Handler Registration

Neuroglia auto-discovers handlers via module scanning:

```python
# src/main.py
from neuroglia.dependency_injection import ServiceCollectionBuilder
from neuroglia.mediation import Mediator

builder = ServiceCollectionBuilder()

# Auto-discover handlers in these modules
Mediator.configure(builder, [
    "application.commands",
    "application.queries"
])

# Handlers are automatically registered
```

### Repository Injection

Handlers receive dependencies through constructor:

```python
class CreateTaskCommandHandler(CommandHandler[CreateTaskCommand, OperationResult]):
    def __init__(
        self,
        task_repository: TaskRepository  # Injected
    ):
        super().__init__()
        self.task_repository = task_repository
```

Repository registration:

```python
# src/main.py
from domain.repositories import TaskRepository
from integration.repositories.motor_task_repository import MongoTaskRepository

# In WebApplicationBuilder setup
services.add_scoped(TaskRepository, MongoTaskRepository)
```

## Benefits

### Separation of Concerns

- **Controllers**: HTTP handling only
- **Handlers**: Business logic only
- **Repositories**: Data access only

### Testability

Each handler can be unit tested independently:

```python
async def test_create_task_handler():
    # Arrange
    mock_repository = Mock(TaskRepository)
    handler = CreateTaskCommandHandler(
        mediator=mock_mediator,
        task_repository=mock_repository
    )
    command = CreateTaskCommand(
        title="Test",
        description="Test task",
        user_id="user123"
    )

    # Act
    task_id = await handler.handle_async(command, None)

    # Assert
    mock_repository.add_async.assert_called_once()
    assert task_id is not None
```

### Scalability

- Commands can be queued/async processed
- Queries can be cached separately
- Read/write databases can differ
- Independent scaling of read/write operations

### Maintainability

- One file per operation
- Clear request → handler → repository flow
- Easy to add new operations
- No controller bloat

## Common Patterns

### Command with Events

```python
class CreateTaskCommandHandler(RequestHandlerBase):
    async def handle_async(self, request, cancellation_token) -> str:
        # Create task
        task = Task(...)
        await self.task_repository.add_async(task)

        # Publish event
        await self.mediator.publish(TaskCreatedEvent(task_id=task.id))

        return task.id
```

### Query with Caching

```python
class GetTasksQueryHandler(RequestHandlerBase):
    def __init__(self, mediator, task_repository, cache):
        super().__init__(mediator)
        self.task_repository = task_repository
        self.cache = cache

    async def handle_async(self, request, cancellation_token):
        # Check cache
        cache_key = f"tasks:{request.user_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # Query database
        tasks = await self.task_repository.find_by_user_async(
            request.user_id
        )

        # Cache results
        await self.cache.set(cache_key, tasks, ttl=300)

        return tasks
```

### Command Validation

```python
class CreateTaskCommandHandler(RequestHandlerBase):
    async def handle_async(self, request, cancellation_token) -> str:
        # Validate
        if not request.title or len(request.title) < 3:
            raise ValueError("Title must be at least 3 characters")

        if len(request.title) > 200:
            raise ValueError("Title too long")

        # Proceed with creation
        task = Task(...)
        await self.task_repository.add_async(task)
        return task.id
```

## Observability

### OpenTelemetry Tracing

Handlers and repositories are automatically traced by Neuroglia's middleware. You can add custom attributes and spans for more detailed business context.

```python
import time
from neuroglia.observability.tracing import add_span_attributes
from opentelemetry import trace
from observability import task_processing_time, tasks_created

tracer = trace.get_tracer(__name__)

class CreateTaskCommandHandler(CommandHandler[CreateTaskCommand, OperationResult]):
    async def handle_async(self, command: CreateTaskCommand) -> OperationResult:
        start_time = time.time()

        # Add business context to automatic span created by CQRS middleware
        add_span_attributes({
            "task.title": command.title,
            "task.priority": command.priority,
        })

        # Create custom span for task creation logic
        with tracer.start_as_current_span("create_task_entity") as span:
            task = Task(title=command.title, description=command.description)
            span.set_attribute("task.status", task.status)

        # Repository operations are auto-traced by TracedRepositoryMixin
        saved_task = await self.task_repository.add_async(task)

        # Record custom metrics
        tasks_created.add(1, {"priority": command.priority})
        processing_time_ms = (time.time() - start_time) * 1000
        task_processing_time.record(processing_time_ms, {"operation": "create"})

        return self.ok({"id": str(saved_task.id)})
```

## Best Practices

✅ **One responsibility per handler** - Don't mix concerns
✅ **Commands return minimal data** - ID or success status
✅ **Queries are read-only** - No side effects
✅ **Validation in handlers** - Business rules in application layer
✅ **Use repositories** - Don't access DB directly
✅ **Handle exceptions** - Proper error messages
✅ **Add tracing** - For debugging and monitoring

## Related Documentation

- [Dependency Injection](./dependency-injection.md) - DI patterns
- [Data Layer](./data-layer.md) - Repository pattern and domain entities
- [Architecture Overview](./overview.md) - Core concepts and patterns
