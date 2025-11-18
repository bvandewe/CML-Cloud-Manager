# Service Registration Pattern Unification

**Date**: 2025-11-18
**Status**: Complete
**Related**: `CONTROLLER_DEPENDENCIES.md`, `APSCHEDULER_REFACTORING_SUMMARY.md`

## Overview

Unified service registration patterns across all services in `src/application/services/` to use consistent `@staticmethod` decorator, `implementation_factory` pattern, and `None` return type.

## Motivation

Three services had inconsistent registration patterns:

1. **SSEEventRelayHostedService** - Used `@classmethod`, returned builder
2. **WorkerMetricsService** - Used inline factory function, returned None
3. **BackgroundTaskScheduler** - Used lambda factories, returned builder

This inconsistency made the codebase harder to understand and maintain.

## Standard Pattern

### Unified Configuration Method Signature

```python
@staticmethod
def configure(builder: Any, *args) -> None:
    """Register and configure <service> in the application builder.

    Args:
        builder: Application builder instance
        [additional args as needed]
    """
```

### Registration Style

**Prefer**: `implementation_factory` with lambda for services with dependencies

```python
builder.services.add_singleton(
    WorkerMetricsService,
    implementation_factory=lambda provider: WorkerMetricsService(
        aws_ec2_client=provider.get_required_service(AwsEc2Client),
        scheduler=provider.get_required_service(BackgroundTaskScheduler),
    ),
)
```

**Reason**: Makes dependencies explicit, avoids inline function definitions

### Logging Style

Unified log messages with ✅ emoji:

```python
logger.info("✅ <ServiceName> configured as singleton")
```

### Return Type

Always `None` - no need to return builder since it's modified in-place.

## Changes Made

### 1. SSEEventRelayHostedService

**Before**:

```python
@classmethod
def configure(cls, builder) -> Any:
    # ...
    log.info("SSEEventRelayHostedService configured")
    return builder
```

**After**:

```python
@staticmethod
def configure(builder: Any) -> None:
    """Register and configure SSE event relay services.

    Args:
        builder: Application builder instance
    """
    # ...
    log.info("✅ SSEEventRelayHostedService configured as singleton")
```

### 2. WorkerMetricsService

**Before**:

```python
@staticmethod
def configure(builder) -> None:
    def create_service(provider):
        return WorkerMetricsService(
            aws_ec2_client=provider.get_required_service(AwsEc2Client),
            scheduler=provider.get_required_service(BackgroundTaskScheduler),
        )

    builder.services.add_singleton(
        WorkerMetricsService, singleton=create_service
    )
```

**After**:

```python
@staticmethod
def configure(builder: Any) -> None:
    """Register and configure worker metrics service.

    Args:
        builder: Application builder instance
    """
    builder.services.add_singleton(
        WorkerMetricsService,
        implementation_factory=lambda provider: WorkerMetricsService(
            aws_ec2_client=provider.get_required_service(AwsEc2Client),
            scheduler=provider.get_required_service(BackgroundTaskScheduler),
        ),
    )
    logger.info("✅ WorkerMetricsService configured as singleton")
```

### 3. BackgroundTaskScheduler

**Before**:

```python
@staticmethod
def configure(builder, modules: list[str]):
    # ...
    log.info("Background task scheduler services registered successfully")
    return builder
```

**After**:

```python
@staticmethod
def configure(builder, modules: list[str]) -> None:
    """Register and configure background task services.

    Args:
        builder: Application builder instance
        modules: List of module names to scan for background tasks
    """
    # ...
    log.info("✅ Background task scheduler services registered successfully")
```

## Benefits

1. **Consistency**: All services follow the same pattern
2. **Readability**: Clear dependency injection with lambdas (no nested functions)
3. **Type Safety**: Explicit return type `None` prevents confusion
4. **Documentation**: Consistent docstrings with Args section
5. **Maintainability**: Easy to add new services following established pattern

## Usage in main.py

All services called identically:

```python
# Configure background services
BackgroundTaskScheduler.configure(builder, modules=["application.jobs"])
WorkerMetricsService.configure(builder)
SSEEventRelayHostedService.configure(builder)
```

## Testing

- ✅ Application starts successfully
- ✅ All services registered correctly (verified in logs)
- ✅ WorkerMetricsService tests pass (9/10, 1 pre-existing failure)
- ✅ No regression in existing functionality

## Guidelines for New Services

When creating new services in `application/services/`, follow this pattern:

```python
class MyService:
    def __init__(self, dependency1, dependency2):
        self._dep1 = dependency1
        self._dep2 = dependency2

    @staticmethod
    def configure(builder: Any) -> None:
        """Register and configure MyService in the application builder.

        Args:
            builder: Application builder instance
        """
        builder.services.add_singleton(
            MyService,
            implementation_factory=lambda provider: MyService(
                dependency1=provider.get_required_service(Dependency1),
                dependency2=provider.get_required_service(Dependency2),
            ),
        )
        logger.info("✅ MyService configured as singleton")
```

## References

- Neuroglia DI: `WebApplicationBuilder.services.add_singleton()`
- Implementation factory pattern: Neuroglia best practices
- See: `CONTROLLER_DEPENDENCIES.md` for controller DI patterns
