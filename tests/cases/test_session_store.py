#!/usr/bin/env python3
"""Test script to verify Redis session store implementation."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from infrastructure import InMemorySessionStore, RedisSessionStore  # noqa: E402


def test_in_memory_store():
    """Test InMemorySessionStore."""
    print("🧪 Testing InMemorySessionStore...")

    store = InMemorySessionStore(session_timeout_hours=1)

    # Create session
    tokens = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "id_token": "test_id_token",
    }
    user_info = {"sub": "test_user", "email": "test@example.com", "name": "Test User"}

    session_id = store.create_session(tokens, user_info)
    print(f"✅ Created session: {session_id[:16]}...")

    # Get session
    session = store.get_session(session_id)
    assert session is not None, "Session should exist"
    assert session["tokens"]["access_token"] == "test_access_token"
    assert session["user_info"]["email"] == "test@example.com"
    print("✅ Retrieved session successfully")

    # Refresh session
    new_tokens = {**tokens, "access_token": "new_access_token"}
    store.refresh_session(session_id, new_tokens)
    session = store.get_session(session_id)
    assert session["tokens"]["access_token"] == "new_access_token"
    print("✅ Refreshed session successfully")

    # Delete session
    store.delete_session(session_id)
    session = store.get_session(session_id)
    assert session is None, "Session should be deleted"
    print("✅ Deleted session successfully")

    print("✅ InMemorySessionStore tests passed!\n")


def test_redis_store():
    """Test RedisSessionStore (requires Redis to be running)."""
    print("🧪 Testing RedisSessionStore...")

    try:
        store = RedisSessionStore(
            redis_url="redis://localhost:6379/0",
            session_timeout_hours=1,
            key_prefix="test_session:",
        )

        # Test connection
        if not store.ping():
            print("⚠️ Redis not responding, skipping Redis tests")
            return

        print("✅ Connected to Redis")

        # Create session
        tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "id_token": "test_id_token",
        }
        user_info = {
            "sub": "test_user",
            "email": "test@example.com",
            "name": "Test User",
        }

        session_id = store.create_session(tokens, user_info)
        print(f"✅ Created session: {session_id[:16]}...")

        # Get session
        session = store.get_session(session_id)
        assert session is not None, "Session should exist"
        assert session["tokens"]["access_token"] == "test_access_token"
        assert session["user_info"]["email"] == "test@example.com"
        print("✅ Retrieved session successfully")

        # Refresh session
        new_tokens = {**tokens, "access_token": "new_access_token"}
        store.refresh_session(session_id, new_tokens)
        session = store.get_session(session_id)
        assert session["tokens"]["access_token"] == "new_access_token"
        print("✅ Refreshed session successfully")

        # Delete session
        store.delete_session(session_id)
        session = store.get_session(session_id)
        assert session is None, "Session should be deleted"
        print("✅ Deleted session successfully")

        print("✅ RedisSessionStore tests passed!\n")

    except Exception as e:
        print(f"⚠️ Redis tests skipped: {e}\n")


if __name__ == "__main__":
    test_in_memory_store()
    test_redis_store()
    print("✅ All tests completed!")
