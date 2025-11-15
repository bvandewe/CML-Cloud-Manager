# Neuroglia MongoDB Package Import Bug

## Issue Summary

The `neuroglia.data.infrastructure.mongo` package has an unnecessary and problematic import structure that forces **pymongo** as a dependency even when only using **Motor** (the async driver).

## Problem Description

### Current Behavior

When importing `MotorRepository` from `neuroglia.data.infrastructure.mongo`:

```python
from neuroglia.data.infrastructure.mongo import MotorRepository
```

The import **fails** with:

```
ModuleNotFoundError: No module named 'pymongo'
```

### Root Cause

The package's `__init__.py` eagerly imports ALL repository implementations:

```python
# neuroglia/data/infrastructure/mongo/__init__.py
from .enhanced_mongo_repository import EnhancedMongoRepository  # ← This imports pymongo
from .mongo_repository import MongoRepository                    # ← This also imports pymongo
from .motor_repository import MotorRepository                   # ← Only needs motor
```

The problem occurs at line 13:

```python
from .enhanced_mongo_repository import EnhancedMongoRepository
```

Which in turn imports (from `enhanced_mongo_repository.py` line 14):

```python
from pymongo import MongoClient
```

### Why This is Wrong

1. **Motor is NOT a pymongo wrapper** - Motor is a completely independent async driver that reimplements the MongoDB wire protocol for asyncio
2. **MotorRepository doesn't use pymongo** - Confirmed by checking imports in `motor_repository.py` - NO pymongo imports found
3. **Forces unnecessary dependencies** - Users who only want async support (Motor) are forced to install pymongo (the sync driver)
4. **Violates separation of concerns** - Sync and async implementations should be independent

## Expected Behavior

Users should be able to use `MotorRepository` with ONLY the `motor` package installed, without requiring `pymongo`.

## Proposed Solutions

### Option 1: Lazy Imports (Recommended)

Use conditional/lazy imports in `__init__.py`:

```python
"""
MongoDB data infrastructure for Neuroglia.
"""

from .motor_repository import MotorRepository
from .serialization_helper import MongoSerializationHelper
from .typed_mongo_query import TypedMongoQuery, with_typed_mongo_query

__all__ = [
    "MotorRepository",
    "TypedMongoQuery",
    "with_typed_mongo_query",
    "MongoSerializationHelper",
]

# Lazy import sync repositories only when accessed
def __getattr__(name):
    if name == "EnhancedMongoRepository":
        from .enhanced_mongo_repository import EnhancedMongoRepository
        return EnhancedMongoRepository
    elif name == "MongoRepository":
        from .mongo_repository import MongoRepository
        return MongoRepository
    elif name == "MongoQueryProvider":
        from .mongo_repository import MongoQueryProvider
        return MongoQueryProvider
    elif name == "MongoRepositoryOptions":
        from .mongo_repository import MongoRepositoryOptions
        return MongoRepositoryOptions
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### Option 2: Separate Subpackages

Split into explicit subpackages:

```
neuroglia/data/infrastructure/mongo/
├── __init__.py           # Base exports only
├── async_/
│   ├── __init__.py      # from .motor_repository import MotorRepository
│   └── motor_repository.py
└── sync/
    ├── __init__.py      # Imports pymongo-based repos
    ├── mongo_repository.py
    └── enhanced_mongo_repository.py
```

Usage:

```python
# Async only - no pymongo needed
from neuroglia.data.infrastructure.mongo.async_ import MotorRepository

# Sync - pymongo required
from neuroglia.data.infrastructure.mongo.sync import MongoRepository
```

### Option 3: Make pymongo Optional

Update `pyproject.toml` to make pymongo an optional dependency:

```toml
[tool.poetry.dependencies]
motor = "^3.0"  # Always required

[tool.poetry.extras]
sync = ["pymongo>=4.0"]
```

Then guard imports:

```python
try:
    from .enhanced_mongo_repository import EnhancedMongoRepository
    from .mongo_repository import MongoRepository
    SYNC_AVAILABLE = True
except ImportError:
    SYNC_AVAILABLE = False
```

## Impact

### Current Workaround

Users must install pymongo even when only using Motor:

```toml
[tool.poetry.dependencies]
motor = "^3.7.1"
pymongo = "^4.10.1"  # ← Should NOT be needed!
```

### After Fix

Only motor would be required for async applications:

```toml
[tool.poetry.dependencies]
motor = "^3.7.1"  # ← Only this!
```

## Verification

### Check MotorRepository Dependencies

```bash
# MotorRepository.py has NO pymongo imports
grep -n 'from pymongo' motor_repository.py
# Returns: (nothing)
```

### Check What Breaks the Import

```bash
# The __init__.py eagerly imports everything
cat __init__.py
# Line 13: from .enhanced_mongo_repository import EnhancedMongoRepository
```

### Check Enhanced Repository

```bash
# Enhanced repository imports pymongo
grep -n 'from pymongo' enhanced_mongo_repository.py
# Line 14: from pymongo import MongoClient
```

## Environment Details

- **Neuroglia Version**: 0.6.2
- **Python Version**: 3.11
- **Motor Version**: 3.7.1
- **Error Location**: `neuroglia/data/infrastructure/mongo/__init__.py` line 13

## Related Documentation

From the package's own docstring:

```python
"""
For async applications (FastAPI, asyncio), use MotorRepository.
For sync applications, use MongoRepository or EnhancedMongoRepository.
"""
```

This clearly indicates these are **separate use cases** and should not have coupled dependencies.

## Recommendation

**Implement Option 1 (Lazy Imports)** as it:

- ✅ Maintains backward compatibility (same import paths)
- ✅ Separates sync/async dependencies
- ✅ Follows Python best practices (PEP 562)
- ✅ Minimal code changes required
- ✅ No breaking changes for existing users

## Testing After Fix

Should be able to run:

```python
# Install ONLY motor
pip install motor

# Import should work without pymongo
from neuroglia.data.infrastructure.mongo import MotorRepository
# ✅ Success!

# Sync imports should still work (with pymongo installed)
pip install pymongo
from neuroglia.data.infrastructure.mongo import MongoRepository
# ✅ Success!
```

---

**Filed by**: Bruno van de Werve
**Date**: November 7, 2025
**Priority**: Medium (workaround available but adds unnecessary dependencies)
**Component**: `neuroglia.data.infrastructure.mongo`
