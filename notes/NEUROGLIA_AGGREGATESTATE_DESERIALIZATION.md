# Neuroglia AggregateState Deserialization Findings

## Context

- Aggregate: `Task` implementing `AggregateRoot[TaskState, str]`
- Persistence: Mongo via `MotorRepository`
- Serialization: `JsonSerializer` from Neuroglia
- Runtime stack: FastAPI + Mediator pipeline, Python 3.11

## Observed Issues

1. **Postponed annotations break JsonSerializer**
   - Using `from __future__ import annotations` left `TaskState.__annotations__` populated with string values.
   - Neuroglia's `JsonSerializer._deserialize_nested` expects concrete `type` objects (e.g., to check `expected_type.__name__`).
   - Resulting failure: `AttributeError: 'str' object has no attribute '__name__'` while deserializing aggregates fetched from Mongo.

2. **Optional state members are dropped during hydration**

   - During aggregate hydration the serializer instantiates `TaskState` and populates attributes that exist in the persisted document.
   - Optional fields absent from older documents (e.g., `assignee_id`) are simply missing on the `TaskState` instance.
   - Application handlers expect these members to exist (possibly set to `None`). When they do not, attribute access fails with `AttributeError` despite the field being declared as `Optional[...]`.

## Local Mitigations

- Removed postponed annotations import from the aggregate module so typing metadata remains concrete at runtime. (Alternatively the serializer could resolve forward references.)
- Updated application code to reference `task.state.<field>` directly. We intentionally removed the `Task.__getattr__` delegation so the runtime failure remains visible until the framework handles optional population.

## Impact

- Without these adjustments any aggregate relying on `AggregateState` and postponed annotations will fail to deserialize from Mongo.
- Even after deserialization succeeds, aggregates must defensively check for missing optional state members, which leaks persistence concerns into application code.

## Proposed Framework Enhancements

1. **Serializer: resolve postponed annotations**
   - Detect `ForwardRef`/string annotations and resolve them via `typing.get_type_hints` before inspecting `expected_type`.
   - Ensures compatibility with PEP 563 style modules and Python 3.11 deferred evaluation (PEP 649 once available).

2. **Serializer: populate optional members when absent**

   - When reconstructing an `AggregateState`, inspect its annotations and set any optional fields that are missing from the payload to `None`.
   - This preserves backward compatibility with documents created before new optional members were introduced and avoids leaking persistence details into application code.
   - The behavior can live in the serializer or a helper invoked by repositories once a state instance is materialized.

3. **State population contract**
   - Clarify in documentation whether serializers must call `__init__` or bypass it, and whether state classes should defensively set defaults for optional members.

## Next Steps

- Share these findings with the Neuroglia team for consideration in the core serializer/AggregateRoot implementation.
- Package a reproducer (Mongo fixture + aggregate) that demonstrates the missing optional field scenario for the framework team.
