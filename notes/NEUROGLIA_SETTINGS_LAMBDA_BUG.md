# Neuroglia Framework Bug: Lambda Registration Breaks DI Resolution

## Issue Summary

**Version Affected:** Neuroglia 0.6.6
**Severity:** High - Prevents dependency injection from working when command/query handlers depend on application settings
**Component:** `neuroglia.hosting.web.WebApplicationBuilder`

The `WebApplicationBuilder.__init__` method registers `app_settings` using a lambda function, which causes the DI container to crash when trying to resolve services that depend on the settings type.

---

## Error Details

### Stack Trace

```python
File "/usr/local/lib/python3.11/site-packages/neuroglia/dependency_injection/service_provider.py", line 598, in _build_service
    service_generic_type = service_descriptor.implementation_type.__origin__ if is_service_generic else None
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'function' object has no attribute '__origin__'
```

### When Does This Occur?

When a command or query handler (or any service) declares a dependency on the settings type:

```python
class CreateCMLWorkerCommandHandler(CommandHandler[...]):
    def __init__(
        self,
        mediator: Mediator,
        mapper: Mapper,
        settings: Settings,  # ← This triggers the bug
    ):
        self.settings = settings
```

---

## Root Cause Analysis

### Current Code (Broken)

**File:** `neuroglia/hosting/web/web_application_builder.py`
**Line:** 33

```python
def __init__(self, app_settings: Optional[Union[ApplicationSettings, "ApplicationSettingsWithObservability"]] = None):
    # ... other initialization ...

    # Auto-register app_settings in DI container if provided
    if app_settings:
        self.services.add_singleton(type(app_settings), lambda: app_settings)  # ← PROBLEM HERE
```

### Why This Breaks

1. **Lambda registered as implementation type**: The DI container stores `lambda: app_settings` as the `implementation_type` in the service descriptor.

2. **Generic type inspection fails**: When resolving a service that depends on `Settings`, the container tries to inspect the lambda:

   ```python
   # service_provider.py line ~598
   service_generic_type = service_descriptor.implementation_type.__origin__ if is_service_generic else None
   ```

3. **Functions don't have `__origin__`**: Lambda functions are not classes and don't have the `__origin__` attribute used for generic type inspection.

4. **Crash**: `AttributeError: 'function' object has no attribute '__origin__'`

### Why Singleton Instance Registration Works

When using `singleton=instance`:

```python
self.services.add_singleton(type(app_settings), singleton=app_settings)
```

The DI container:

- Stores the actual instance, not a factory function
- Doesn't attempt to inspect it for generic parameters
- Simply returns the pre-built singleton when requested
- Works correctly with dependency resolution

---

## Proposed Fix

### Option 1: Register as Singleton Instance (Recommended) ⭐

**Change in `web_application_builder.py` line 33:**

```python
# Before (broken)
if app_settings:
    self.services.add_singleton(type(app_settings), lambda: app_settings)

# After (fixed)
if app_settings:
    self.services.add_singleton(type(app_settings), singleton=app_settings)
```

**Why This Is Better:**

✅ **Semantically correct** - `app_settings` is already a singleton instance; wrapping it in a lambda adds unnecessary indirection
✅ **Performance improvement** - Eliminates lambda invocation overhead on every DI resolution
✅ **Type safety** - DI container can properly inspect the service type
✅ **100% backward compatible** - Behavior from consumer perspective is identical
✅ **One-line fix** - Minimal code change with maximum impact
✅ **Aligns with DI best practices** - Matches patterns in Microsoft.Extensions.DependencyInjection, Spring, etc.

---

### Option 2: Add Defensive Check in Service Provider

**Change in `service_provider.py` line ~595:**

```python
# Before
is_service_generic = typing.get_origin(service_descriptor.implementation_type) is not None
service_generic_type = service_descriptor.implementation_type.__origin__ if is_service_generic else None

# After
is_service_generic = (
    hasattr(service_descriptor.implementation_type, '__origin__') and
    typing.get_origin(service_descriptor.implementation_type) is not None
)
service_generic_type = (
    service_descriptor.implementation_type.__origin__
    if is_service_generic
    else None
)
```

**Pros:**
✅ Prevents crashes from non-class implementation types
✅ Defensive coding practice
✅ Backward compatible

**Cons:**
⚠️ Doesn't fix the inefficiency of lambda invocation
⚠️ Treats symptom rather than root cause

---

### Option 3: Special Handling for Factory Functions

**Add in `service_provider.py` `_build_service` method:**

```python
# Early in _build_service, before generic type inspection
if callable(service_descriptor.implementation_type) and not isinstance(service_descriptor.implementation_type, type):
    # It's a factory function/lambda, invoke it directly
    service = service_descriptor.implementation_type()
    return service
```

**Pros:**
✅ Supports both lambda factories and proper classes
✅ Backward compatible

**Cons:**
⚠️ More complex logic
⚠️ Still has lambda invocation overhead
⚠️ Doesn't address the semantic incorrectness

---

## Recommendation

**Implement Option 1** - Change `lambda: app_settings` to `singleton=app_settings`

**Rationale:**

1. Simplest fix with the most benefits
2. Improves performance and correctness
3. Zero risk of breaking changes
4. Aligns with how other DI containers handle pre-built instances
5. Makes the intent explicit: "this is a singleton instance, not a factory"

---

## Current Workaround

Until this is fixed in the framework, users must add this after creating `WebApplicationBuilder`:

```python
from application.settings import Settings, app_settings

builder = WebApplicationBuilder(app_settings=app_settings)

# Workaround: Replace lambda registration with singleton instance
for descriptor in list(builder.services):
    if descriptor.service_type == Settings:
        builder.services.remove(descriptor)
        break
builder.services.add_singleton(Settings, singleton=app_settings)
```

---

## Impact Assessment

### Breaking Changes

**None** - The change is fully backward compatible. From a consumer's perspective, the behavior is identical.

### Performance Impact

**Positive** - Eliminates unnecessary lambda invocation on every settings resolution.

### Affected Scenarios

Any application where:

- `WebApplicationBuilder` is initialized with `app_settings`
- Command handlers, query handlers, or other services depend on the settings type
- The application uses the standard CQRS pattern with Mediator

### Test Cases to Verify Fix

```python
def test_settings_resolution_with_handler():
    """Test that settings can be injected into command handlers."""
    from application.settings import Settings, app_settings
    from neuroglia.hosting.web import WebApplicationBuilder

    builder = WebApplicationBuilder(app_settings=app_settings)
    provider = builder.services.build()

    # Should not raise AttributeError
    resolved_settings = provider.get_service(Settings)
    assert resolved_settings is app_settings


def test_command_handler_with_settings_dependency():
    """Test that command handlers depending on Settings can be resolved."""
    from neuroglia.mediation import Mediator

    builder = WebApplicationBuilder(app_settings=app_settings)
    Mediator.configure(builder, ["application.commands"])
    provider = builder.services.build()

    # Should not raise AttributeError when resolving handler
    from application.commands import CreateCMLWorkerCommandHandler
    handler = provider.get_service(CreateCMLWorkerCommandHandler)
    assert handler.settings is app_settings
```

---

## Related Code References

### File: `neuroglia/hosting/web/web_application_builder.py`

- **Line 33**: Lambda registration that needs to change

### File: `neuroglia/dependency_injection/service_provider.py`

- **Line 598**: Where the crash occurs when inspecting lambda

### File: `neuroglia/dependency_injection/service_collection.py`

- `add_singleton` method supports both factory and singleton patterns

---

## Proposed PR Changes

### Change 1: Fix Settings Registration

**File:** `neuroglia/hosting/web/web_application_builder.py`

```diff
         # Auto-register app_settings in DI container if provided
         if app_settings:
-            self.services.add_singleton(type(app_settings), lambda: app_settings)
+            self.services.add_singleton(type(app_settings), singleton=app_settings)
```

### Change 2: Add Test Coverage

**File:** `tests/hosting/test_web_application_builder.py` (new or existing)

```python
def test_settings_registration_not_lambda():
    """Verify settings are registered as singleton instance, not lambda."""
    from neuroglia.hosting.abstractions import ApplicationSettings

    settings = ApplicationSettings(app_name="test", app_version="1.0.0")
    builder = WebApplicationBuilder(app_settings=settings)

    # Find the settings descriptor
    settings_descriptor = None
    for descriptor in builder.services:
        if descriptor.service_type == type(settings):
            settings_descriptor = descriptor
            break

    assert settings_descriptor is not None, "Settings should be registered"

    # Implementation should be the instance itself, not a lambda
    assert not callable(settings_descriptor.implementation_type) or isinstance(settings_descriptor.implementation_type, type), \
        "Settings should be registered as singleton instance, not factory function"
```

---

## Documentation Updates

Update the documentation to clarify the difference between factory registration and singleton registration:

```python
# Registering a singleton instance (preferred for pre-built objects)
builder.services.add_singleton(MyService, singleton=my_service_instance)

# Registering a factory (useful for lazy initialization)
builder.services.add_singleton(MyService, factory=lambda: MyService())
```

---

## Timeline

- **Discovered:** November 16, 2025
- **Workaround Deployed:** November 16, 2025
- **Framework Version:** Neuroglia 0.6.6
- **Python Version:** 3.11

---

## Additional Context

This issue was discovered while implementing a CML Worker management system using CQRS with Neuroglia. The `CreateCMLWorkerCommandHandler` required access to AWS credentials stored in application settings, which triggered the bug during DI resolution.

The workaround (removing and re-registering the settings) is functional but requires every application using Neuroglia to implement it manually. A framework-level fix would benefit all users.

---

## Contact

For questions or discussion about this issue:

- **Reporter:** [Your Name/Handle]
- **Repository:** CML-Cloud-Manager
- **Date:** November 16, 2025
