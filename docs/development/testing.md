# Testing Guide

## Overview

This project uses a comprehensive, modular test suite built with pytest. All tests follow strict typing conventions and are organized by architectural layer, making it easy to maintain and extend test coverage.

## Quick Start

### Running Tests

```bash
# Run all tests
make test

# Or using poetry directly
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/domain/test_task_entity.py -v

# Run tests by marker
poetry run pytest -m unit        # Unit tests only
poetry run pytest -m integration # Integration tests only
poetry run pytest -m command     # Command handler tests
poetry run pytest -m query       # Query handler tests
```

### Running Tests with Coverage

```bash
# Generate coverage report
poetry run pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

# Open coverage report in browser
open htmlcov/index.html
```

## Test Organization

### Directory Structure

```
tests/
├── conftest.py                    # Shared fixtures and pytest configuration
├── fixtures/
│   ├── __init__.py
│   ├── factories.py               # Test data factories
│   └── mixins.py                  # Reusable test utilities
├── domain/
│   └── test_task_entity.py        # Domain entity tests
├── infrastructure/
│   └── test_session_stores.py     # Infrastructure layer tests
├── application/
│   ├── test_commands.py           # Command handler tests
│   └── test_queries.py            # Query handler tests
└── api/
    └── (future API tests)
```

### Test Categories

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests with no external dependencies
- `@pytest.mark.integration` - Tests involving external services (MongoDB, Redis)
- `@pytest.mark.slow` - Tests that take several seconds to complete
- `@pytest.mark.asyncio` - Async tests requiring event loop
- `@pytest.mark.auth` - Authentication and authorization tests
- `@pytest.mark.repository` - Repository layer tests
- `@pytest.mark.command` - Command handler tests
- `@pytest.mark.query` - Query handler tests
- `@pytest.mark.smoke` - Critical functionality smoke tests

## Test Infrastructure

### Fixtures

The test suite provides several pre-configured fixtures in `tests/conftest.py`:

#### `session_store: SessionStore`

Provides an in-memory session store for testing authentication.

```python
def test_session_creation(session_store):
    session_id = session_store.create_session(tokens, user_info)
    assert session_id is not None
```

#### `auth_service: DualAuthService`

Provides a configured authentication service with session store.

```python
def test_authentication(auth_service):
    user = auth_service.get_user_from_jwt(token)
    assert user is not None
```

#### `mock_repository: MagicMock`

Pre-configured mock repository with typed async methods.

```python
def test_command_handler(mock_repository):
    mock_repository.get_by_id_async = AsyncMock(return_value=task)
    # Use in your tests
```

#### `mongo_client: AsyncIOMotorClient` / `mongo_db: AgnosticDatabase`

MongoDB test fixtures with automatic cleanup.

```python
@pytest.mark.integration
async def test_with_mongodb(mongo_db):
    collection = mongo_db["test_collection"]
    await collection.insert_one({"test": "data"})
```

### Test Data Factories

Located in `tests/fixtures/factories.py`, factories provide easy test data generation:

#### TaskFactory

```python
from tests.fixtures.factories import TaskFactory

# Create task with defaults
task = TaskFactory.create()

# Create task with specific values
task = TaskFactory.create(
    title="My Task",
    status=TaskStatus.IN_PROGRESS,
    priority=TaskPriority.HIGH
)

# Create multiple tasks
tasks = TaskFactory.create_many(5, department="Engineering")

# Convenience methods
task = TaskFactory.create_with_assignee("user123")
task = TaskFactory.create_with_department("Sales")
task = TaskFactory.create_with_status(TaskStatus.COMPLETED)
```

#### TokenFactory

```python
from tests.fixtures.factories import TokenFactory

# Generate authentication tokens
tokens = TokenFactory.create_tokens()
# Returns: {"access_token": "...", "refresh_token": "...", "id_token": "..."}

# Generate user info
user_info = TokenFactory.create_user_info()
# Returns: {"sub": "uuid", "email": "...", "name": "...", "roles": [...]}

# Generate JWT claims
claims = TokenFactory.create_jwt_claims()
```

#### SessionFactory

```python
from tests.fixtures.factories import SessionFactory

# Create complete session data
tokens, user_info = SessionFactory.create_session_data()

# Create expired session
tokens, user_info = SessionFactory.create_expired_session_data()
```

### Test Mixins

Located in `tests/fixtures/mixins.py`, mixins provide reusable test utilities:

#### AsyncTestMixin

```python
class MyTest(AsyncTestMixin):
    async def test_with_timeout(self):
        result = await self.await_with_timeout(
            some_async_operation(),
            timeout=5.0
        )

    async def test_wait_for_condition(self):
        await self.wait_for_condition(
            lambda: operation_completed,
            timeout=3.0
        )
```

#### AssertionMixin

```python
class MyTest(AssertionMixin):
    def test_task_comparison(self):
        self.assert_task_equals(actual_task, expected_task)

    def test_dict_subset(self):
        self.assert_dict_subset(
            {"key": "value"},
            {"key": "value", "extra": "data"}
        )
```

#### MockHelperMixin

```python
class MyTest(MockHelperMixin):
    def test_with_async_mock(self):
        mock = self.create_async_mock(return_value=task)

    def test_partial_call_verification(self):
        self.assert_mock_called_once_with_partial(
            mock,
            task_id="123",
            title="Test"
        )
```

#### SessionTestMixin

```python
class MyTest(SessionTestMixin):
    def test_session_operations(self, session_store):
        session_id, tokens, user_info = self.create_test_session(
            session_store,
            user_email="test@example.com"
        )

        self.assert_session_exists(session_store, session_id)

        session_store.delete_session(session_id)
        self.assert_session_not_exists(session_store, session_id)
```

#### BaseTestCase

Combines all mixins for convenient inheritance:

```python
from tests.fixtures.mixins import BaseTestCase

class TestMyFeature(BaseTestCase):
    """Inherits all mixin utilities."""

    async def test_feature(self):
        # Can use any mixin method
        mock = self.create_async_mock(return_value=data)
        result = await self.await_with_timeout(operation())
        self.assert_dict_subset(expected, result)
```

## Writing Tests

### Domain Layer Tests

Test domain entities and business logic without external dependencies.

```python
"""Test task entity behavior."""
import pytest
from domain.entities import Task
from domain.enums import TaskStatus, TaskPriority
from tests.fixtures.factories import TaskFactory


class TestTaskEntity:
    """Test Task entity."""

    def test_create_task_with_defaults(self) -> None:
        """Test creating a task with default values."""
        task: Task = TaskFactory.create(
            title="Test Task",
            description="Test Description"
        )

        assert task.state.title == "Test Task"
        assert task.state.status == TaskStatus.PENDING
        assert task.state.priority == TaskPriority.MEDIUM

    def test_update_task_status_generates_event(self) -> None:
        """Test status update generates domain event."""
        task: Task = TaskFactory.create()

        result: bool = task.update_status(TaskStatus.COMPLETED)

        assert result is True
        assert task.state.status == TaskStatus.COMPLETED
        assert len(task.domain_events) > 0
```

### Infrastructure Layer Tests

Test infrastructure components like repositories and session stores.

```python
"""Test session store behavior."""
import pytest
from infrastructure import InMemorySessionStore
from tests.fixtures.factories import TokenFactory
from tests.fixtures.mixins import BaseTestCase


class TestSessionStore(BaseTestCase):
    """Test session store operations."""

    def test_create_and_retrieve_session(
        self, session_store: InMemorySessionStore
    ) -> None:
        """Test creating and retrieving a session."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = session_store.create_session(tokens, user_info)

        retrieved_tokens = session_store.get_tokens(session_id)
        retrieved_user = session_store.get_user_info(session_id)

        assert retrieved_tokens == tokens
        assert retrieved_user == user_info
```

### Application Layer Tests

Test command and query handlers with mocked dependencies.

#### Command Handler Tests

```python
"""Test command handlers."""
import pytest
from unittest.mock import MagicMock
from typing import Any

from neuroglia.core import OperationResult
from application.commands.create_task_command import (
    CreateTaskCommand,
    CreateTaskCommandHandler
)
from tests.fixtures.factories import TaskFactory
from tests.fixtures.mixins import BaseTestCase


class TestCreateTaskCommand(BaseTestCase):
    """Test CreateTaskCommand handler."""

    @pytest.fixture
    def handler(self, mock_repository: MagicMock) -> CreateTaskCommandHandler:
        """Create handler with mocked dependencies."""
        # Setup handler with required dependencies
        return CreateTaskCommandHandler(
            mediator=MagicMock(),
            mapper=MagicMock(),
            cloud_event_bus=MagicMock(),
            cloud_event_publishing_options=MagicMock(),
            task_repository=mock_repository,
        )

    @pytest.mark.asyncio
    async def test_create_task_success(
        self,
        handler: CreateTaskCommandHandler,
        mock_repository: MagicMock
    ) -> None:
        """Test successful task creation."""
        command: CreateTaskCommand = CreateTaskCommand(
            title="New Task",
            description="Task description"
        )

        created_task = TaskFactory.create(
            title="New Task",
            description="Task description"
        )
        mock_repository.add_async = self.create_async_mock(
            return_value=created_task
        )

        result: OperationResult[Any] = await handler.handle_async(command)

        assert result.is_success
        assert result.status_code == 200
        mock_repository.add_async.assert_called_once()
```

#### Query Handler Tests

```python
"""Test query handlers."""
import pytest
from unittest.mock import MagicMock
from typing import Any

from neuroglia.core import OperationResult
from application.queries.get_tasks_query import (
    GetTasksQuery,
    GetTasksQueryHandler
)
from tests.fixtures.factories import TaskFactory
from tests.fixtures.mixins import BaseTestCase


class TestGetTasksQuery(BaseTestCase):
    """Test GetTasksQuery handler."""

    @pytest.fixture
    def handler(self, mock_repository: MagicMock) -> GetTasksQueryHandler:
        """Create handler with mocked repository."""
        return GetTasksQueryHandler(task_repository=mock_repository)

    @pytest.mark.asyncio
    async def test_admin_sees_all_tasks(
        self,
        handler: GetTasksQueryHandler,
        mock_repository: MagicMock
    ) -> None:
        """Test admin users can see all tasks."""
        tasks = [
            TaskFactory.create(title="Task 1"),
            TaskFactory.create(title="Task 2"),
        ]
        mock_repository.get_all_async = self.create_async_mock(
            return_value=tasks
        )

        query: GetTasksQuery = GetTasksQuery(
            user_info={"roles": ["admin"], "sub": "admin1"}
        )

        result: OperationResult[Any] = await handler.handle_async(query)

        assert result.is_success
        mock_repository.get_all_async.assert_called_once()
```

## Best Practices

### 1. Type Hints

Always use strict type hints for better code clarity and type safety:

```python
def test_example(self) -> None:
    """Test with proper typing."""
    task: Task = TaskFactory.create()
    result: bool = task.update_status(TaskStatus.COMPLETED)
    events: list[Any] = task.domain_events

    assert result is True
```

### 2. Descriptive Test Names

Use clear, descriptive test names that explain what is being tested:

```python
# Good
def test_admin_can_update_any_task(self) -> None:
    """Test that admin users can update tasks assigned to others."""

# Bad
def test_update(self) -> None:
    """Test update."""
```

### 3. Arrange-Act-Assert Pattern

Structure tests clearly with three sections:

```python
def test_feature(self) -> None:
    """Test description."""
    # Arrange - Set up test data and mocks
    task = TaskFactory.create()
    mock_repo.get_by_id_async = self.create_async_mock(return_value=task)

    # Act - Execute the code under test
    result = await handler.handle_async(command)

    # Assert - Verify expectations
    assert result.is_success
    mock_repo.get_by_id_async.assert_called_once()
```

### 4. Test Isolation

Each test should be independent and not rely on other tests:

```python
# Good - Each test creates its own data
def test_feature_a(self) -> None:
    task = TaskFactory.create()
    # Test feature A

def test_feature_b(self) -> None:
    task = TaskFactory.create()
    # Test feature B

# Bad - Tests share state
class TestSuite:
    task = None  # Shared state!

    def test_feature_a(self) -> None:
        self.task = TaskFactory.create()

    def test_feature_b(self) -> None:
        # Depends on test_feature_a running first!
        self.task.update_status(TaskStatus.COMPLETED)
```

### 5. Use Fixtures for Common Setup

Leverage pytest fixtures for repeated setup:

```python
@pytest.fixture
def authenticated_user(self) -> dict[str, Any]:
    """Provide authenticated user context."""
    return {
        "sub": "user123",
        "email": "user@example.com",
        "roles": ["user"],
        "department": "Engineering"
    }

def test_with_auth(self, authenticated_user: dict[str, Any]) -> None:
    """Test using the fixture."""
    assert authenticated_user["sub"] == "user123"
```

### 6. Mock External Dependencies

Always mock external dependencies (databases, APIs, etc.) in unit tests:

```python
@pytest.mark.asyncio
async def test_command_handler(
    self,
    handler: CommandHandler,
    mock_repository: MagicMock
) -> None:
    """Test handler with mocked repository."""
    # Mock returns specific value
    mock_repository.get_by_id_async = self.create_async_mock(
        return_value=task
    )

    result = await handler.handle_async(command)

    # Verify mock was called correctly
    mock_repository.get_by_id_async.assert_called_once_with("task_id")
```

### 7. Test Edge Cases

Don't just test the happy path:

```python
def test_update_task_not_found(self) -> None:
    """Test updating non-existent task."""
    mock_repository.get_by_id_async = self.create_async_mock(
        return_value=None
    )

    # Should handle gracefully
    with pytest.raises(AttributeError):
        await handler.handle_async(command)

def test_update_task_forbidden(self) -> None:
    """Test user cannot update other users' tasks."""
    result = await handler.handle_async(command)

    assert not result.is_success
    assert result.status_code == 400
```

## Running Tests in CI/CD

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install Poetry
        run: |
          curl -sSL https://install.python-poetry.org | python3 -
          echo "$HOME/.local/bin" >> $GITHUB_PATH

      - name: Install dependencies
        run: poetry install

      - name: Run tests with coverage
        run: |
          poetry run pytest tests/ \
            --cov=src \
            --cov-report=xml \
            --cov-report=term-missing

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          file: ./coverage.xml
```

## Test Coverage Goals

### Current Coverage

- **Domain Layer:** 18 tests (100% entity coverage)
- **Infrastructure Layer:** 11 tests (session stores)
- **Application Layer:** 31 tests (commands + queries)
- **Overall:** 60+ tests with 98%+ passing rate

### Coverage Targets

- **Domain Entities:** 100% - All business logic must be tested
- **Command Handlers:** 90%+ - All CRUD operations and edge cases
- **Query Handlers:** 90%+ - All queries and RBAC scenarios
- **Infrastructure:** 80%+ - Core infrastructure components
- **API Controllers:** 80%+ - All endpoints and auth flows

## Troubleshooting

### Common Issues

#### Tests Not Discovered

```bash
# Clear pytest cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type d -name .pytest_cache -exec rm -rf {} +

# Verify pytest.ini is correct
cat pytest.ini
```

#### Async Tests Failing

Ensure pytest-asyncio is installed:

```bash
poetry add --group dev pytest-asyncio
```

And pytest.ini has:

```ini
[pytest]
asyncio_mode = auto
```

#### Import Errors

Ensure pythonpath is set correctly in pytest.ini:

```ini
[pytest]
pythonpath = src
```

#### Mock Not Being Awaited

Use `create_async_mock()` helper:

```python
# Good
mock_repo.method = self.create_async_mock(return_value=value)

# Bad
mock_repo.method = MagicMock(return_value=value)  # Not async!
```

### Getting Help

1. Check test logs: `poetry run pytest tests/ -v --tb=long`
2. Run specific test with debug: `poetry run pytest tests/path/to/test.py::test_name -vv`
3. Check existing tests for examples
4. Review the TEST_SUITE_SUMMARY.md file in the project root for detailed documentation

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
