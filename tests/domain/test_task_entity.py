"""Domain layer tests for Task entity.

Tests the core domain logic including:
- Task creation and initialization
- Task state updates (title, description, status, priority, etc.)
- Domain events generation
- Business rules enforcement
"""

from domain.entities import Task
from domain.enums import TaskPriority, TaskStatus
from domain.events.task import (
    TaskAssigneeUpdatedDomainEvent,
    TaskCreatedDomainEvent,
    TaskDepartmentUpdatedDomainEvent,
    TaskDescriptionUpdatedDomainEvent,
    TaskPriorityUpdatedDomainEvent,
    TaskStatusUpdatedDomainEvent,
    TaskTitleUpdatedDomainEvent,
)
from tests.fixtures.factories import TaskFactory


class TestTaskCreation:
    """Test Task entity creation."""

    def test_create_task_with_defaults(self) -> None:
        """Test creating a task with default values."""
        task: Task = Task(title="Test Task", description="Test Description")

        assert task.state.title == "Test Task"
        assert task.state.description == "Test Description"
        assert task.state.status == TaskStatus.PENDING
        assert task.state.priority == TaskPriority.MEDIUM
        assert task.state.assignee_id is None
        assert task.state.department is None
        assert task.state.id != ""
        assert task.state.created_at is not None
        assert task.state.updated_at is not None

    def test_create_task_with_all_parameters(self) -> None:
        """Test creating a task with all parameters specified."""
        task: Task = Task(
            title="Complete Task",
            description="Full description",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            assignee_id="user123",
            department="Engineering",
            created_by="admin",
        )

        assert task.state.title == "Complete Task"
        assert task.state.description == "Full description"
        assert task.state.status == TaskStatus.IN_PROGRESS
        assert task.state.priority == TaskPriority.HIGH
        assert task.state.assignee_id == "user123"
        assert task.state.department == "Engineering"
        assert task.state.created_by == "admin"

    def test_create_task_generates_domain_event(self) -> None:
        """Test that task creation generates TaskCreatedDomainEvent."""
        task: Task = Task(title="Test", description="Test")

        # Check that domain events were registered
        events = task.domain_events
        assert len(events) > 0
        # The first event should be TaskCreatedDomainEvent
        assert isinstance(events[0], TaskCreatedDomainEvent)
        assert events[0].title == "Test"

    def test_task_id_is_unique(self) -> None:
        """Test that each task gets a unique ID."""
        task1: Task = Task(title="Task 1", description="Description 1")
        task2: Task = Task(title="Task 2", description="Description 2")

        assert task1.state.id != task2.state.id


class TestTaskStatusUpdate:
    """Test Task status update operations."""

    def test_update_task_status(self) -> None:
        """Test updating task status."""
        task: Task = TaskFactory.create(status=TaskStatus.PENDING)
        original_updated_at = task.state.updated_at

        result: bool = task.update_status(TaskStatus.IN_PROGRESS)

        assert result is True
        assert task.state.status == TaskStatus.IN_PROGRESS
        assert task.state.updated_at > original_updated_at

    def test_update_status_generates_event(self) -> None:
        """Test that status update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_status(TaskStatus.COMPLETED)

        events = task.domain_events
        # Should have TaskCreatedDomainEvent and TaskStatusUpdatedDomainEvent
        assert len(events) >= 2
        assert any(isinstance(e, TaskStatusUpdatedDomainEvent) for e in events)


class TestTaskTitleUpdate:
    """Test Task title update operations."""

    def test_update_task_title(self) -> None:
        """Test updating task title."""
        task: Task = TaskFactory.create(title="Original Title")

        result: bool = task.update_title("New Title")

        assert result is True
        assert task.state.title == "New Title"

    def test_update_title_generates_event(self) -> None:
        """Test that title update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_title("Updated Title")

        events = task.domain_events
        assert any(isinstance(e, TaskTitleUpdatedDomainEvent) for e in events)


class TestTaskDescriptionUpdate:
    """Test Task description update operations."""

    def test_update_task_description(self) -> None:
        """Test updating task description."""
        task: Task = TaskFactory.create(description="Original Description")

        result: bool = task.update_description("New Description")

        assert result is True
        assert task.state.description == "New Description"

    def test_update_description_generates_event(self) -> None:
        """Test that description update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_description("Updated Description")

        events = task.domain_events
        assert any(isinstance(e, TaskDescriptionUpdatedDomainEvent) for e in events)


class TestTaskPriorityUpdate:
    """Test Task priority update operations."""

    def test_update_task_priority(self) -> None:
        """Test updating task priority."""
        task: Task = TaskFactory.create(priority=TaskPriority.LOW)

        result: bool = task.update_priority(TaskPriority.HIGH)

        assert result is True
        assert task.state.priority == TaskPriority.HIGH

    def test_update_priority_generates_event(self) -> None:
        """Test that priority update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_priority(TaskPriority.HIGH)

        events = task.domain_events
        assert any(isinstance(e, TaskPriorityUpdatedDomainEvent) for e in events)


class TestTaskAssigneeUpdate:
    """Test Task assignee update operations."""

    def test_update_task_assignee(self) -> None:
        """Test updating task assignee."""
        task: Task = TaskFactory.create(assignee_id=None)

        result: bool = task.update_assignee("user456")

        assert result is True
        assert task.state.assignee_id == "user456"

    def test_update_assignee_generates_event(self) -> None:
        """Test that assignee update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_assignee("new-user")

        events = task.domain_events
        assert any(isinstance(e, TaskAssigneeUpdatedDomainEvent) for e in events)


class TestTaskDepartmentUpdate:
    """Test Task department update operations."""

    def test_update_task_department(self) -> None:
        """Test updating task department."""
        task: Task = TaskFactory.create(department="Engineering")

        result: bool = task.update_department("Sales")

        assert result is True
        assert task.state.department == "Sales"

    def test_update_department_generates_event(self) -> None:
        """Test that department update generates domain event."""
        task: Task = TaskFactory.create()
        task.update_department("Marketing")

        events = task.domain_events
        assert any(isinstance(e, TaskDepartmentUpdatedDomainEvent) for e in events)


class TestTaskFactory:
    """Test TaskFactory utility."""

    def test_create_task_with_factory(self) -> None:
        """Test creating task using TaskFactory."""
        task: Task = TaskFactory.create(
            title="Factory Task", priority=TaskPriority.HIGH
        )

        assert task.state.title == "Factory Task"
        assert task.state.priority == TaskPriority.HIGH

    def test_create_many_tasks(self) -> None:
        """Test creating multiple tasks with factory."""
        tasks: list[Task] = TaskFactory.create_many(3, department="IT")

        assert len(tasks) == 3
        assert all(task.state.department == "IT" for task in tasks)
        assert tasks[0].state.title == "Test Task 1"
        assert tasks[1].state.title == "Test Task 2"
        assert tasks[2].state.title == "Test Task 3"

    def test_create_pending_task(self) -> None:
        """Test creating a pending task."""
        task: Task = TaskFactory.create_pending()
        assert task.state.status == TaskStatus.PENDING

    def test_create_in_progress_task(self) -> None:
        """Test creating an in-progress task."""
        task: Task = TaskFactory.create_in_progress()
        assert task.state.status == TaskStatus.IN_PROGRESS

    def test_create_completed_task(self) -> None:
        """Test creating a completed task."""
        task: Task = TaskFactory.create_completed()
        assert task.state.status == TaskStatus.COMPLETED

    def test_create_high_priority_task(self) -> None:
        """Test creating a high priority task."""
        task: Task = TaskFactory.create_high_priority()
        assert task.state.priority == TaskPriority.HIGH

    def test_create_task_with_assignee(self) -> None:
        """Test creating a task with assignee."""
        task: Task = TaskFactory.create_with_assignee("user789")
        assert task.state.assignee_id == "user789"

    def test_create_task_for_department(self) -> None:
        """Test creating a task for specific department."""
        task: Task = TaskFactory.create_for_department("HR")
        assert task.state.department == "HR"
