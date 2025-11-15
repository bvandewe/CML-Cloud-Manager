"""Infrastructure layer tests for session stores.

Tests session management implementations:
- InMemorySessionStore
- Session creation, retrieval, update, and deletion
- Session expiration
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from infrastructure import InMemorySessionStore, SessionStore
from tests.fixtures.factories import TokenFactory
from tests.fixtures.mixins import SessionTestMixin


class TestInMemorySessionStore:
    """Test InMemorySessionStore implementation."""

    def test_create_session(self, session_store: SessionStore) -> None:
        """Test creating a new session."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = session_store.create_session(tokens, user_info)

        assert session_id is not None
        assert len(session_id) > 0

    def test_get_session(self, session_store: SessionStore) -> None:
        """Test retrieving an existing session."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = session_store.create_session(tokens, user_info)
        session: dict[str, Any] | None = session_store.get_session(session_id)

        assert session is not None
        assert session["tokens"]["access_token"] == tokens["access_token"]
        assert session["user_info"]["email"] == user_info["email"]

    def test_get_nonexistent_session(self, session_store: SessionStore) -> None:
        """Test retrieving a non-existent session returns None."""
        result: dict[str, Any] | None = session_store.get_session("nonexistent-id")
        assert result is None

    def test_refresh_session(self, session_store: SessionStore) -> None:
        """Test refreshing session tokens."""
        tokens: dict[str, str] = TokenFactory.create_tokens(
            access_token="old_access_token"
        )
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = session_store.create_session(tokens, user_info)

        new_tokens: dict[str, str] = TokenFactory.create_tokens(
            access_token="new_access_token"
        )
        session_store.refresh_session(session_id, new_tokens)

        session: dict[str, Any] | None = session_store.get_session(session_id)
        assert session is not None
        assert session["tokens"]["access_token"] == "new_access_token"

    def test_delete_session(self, session_store: SessionStore) -> None:
        """Test deleting a session."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = session_store.create_session(tokens, user_info)
        session_store.delete_session(session_id)

        session: dict[str, Any] | None = session_store.get_session(session_id)
        assert session is None

    def test_delete_nonexistent_session(self, session_store: SessionStore) -> None:
        """Test deleting a non-existent session doesn't raise error."""
        # Should not raise any exception
        session_store.delete_session("nonexistent-id")

    def test_session_expiration(self) -> None:
        """Test that sessions expire after the timeout period."""
        # Create store with 1-hour timeout
        store: InMemorySessionStore = InMemorySessionStore(session_timeout_hours=1)

        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = store.create_session(tokens, user_info)

        # Manually expire the session by modifying its timestamp
        if hasattr(store, "_sessions") and session_id in store._sessions:
            expired_time: datetime = datetime.now(timezone.utc) - timedelta(hours=2)
            store._sessions[session_id]["last_accessed"] = expired_time

        # Try to get expired session
        session: dict[str, Any] | None = store.get_session(session_id)
        assert session is None

    def test_multiple_sessions(self, session_store: SessionStore) -> None:
        """Test managing multiple sessions simultaneously."""
        tokens1: dict[str, str] = TokenFactory.create_tokens(access_token="token1")
        user_info1: dict[str, Any] = TokenFactory.create_user_info(
            email="user1@example.com"
        )

        tokens2: dict[str, str] = TokenFactory.create_tokens(access_token="token2")
        user_info2: dict[str, Any] = TokenFactory.create_user_info(
            email="user2@example.com"
        )

        session_id1: str = session_store.create_session(tokens1, user_info1)
        session_id2: str = session_store.create_session(tokens2, user_info2)

        assert session_id1 != session_id2

        session1: dict[str, Any] | None = session_store.get_session(session_id1)
        session2: dict[str, Any] | None = session_store.get_session(session_id2)

        assert session1 is not None
        assert session2 is not None
        assert session1["user_info"]["email"] == "user1@example.com"
        assert session2["user_info"]["email"] == "user2@example.com"


class TestSessionStoreWithMixin(SessionTestMixin):
    """Test SessionStore using test mixins."""

    def test_create_and_assert_exists(self, session_store: SessionStore) -> None:
        """Test creating session and asserting it exists."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = self.create_test_session(session_store, tokens, user_info)
        self.assert_session_exists(session_store, session_id)

    def test_delete_and_assert_not_exists(self, session_store: SessionStore) -> None:
        """Test deleting session and asserting it doesn't exist."""
        tokens: dict[str, str] = TokenFactory.create_tokens()
        user_info: dict[str, Any] = TokenFactory.create_user_info()

        session_id: str = self.create_test_session(session_store, tokens, user_info)
        session_store.delete_session(session_id)
        self.assert_session_not_exists(session_store, session_id)
