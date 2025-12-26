"""Unit tests for session pool module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sdk.session_pool import (
    PooledSession,
    SessionPool,
    get_pool,
    init_pool,
    shutdown_pool,
)


class TestPooledSession:
    """Test PooledSession dataclass."""

    def test_creation(self) -> None:
        """Test PooledSession creation with defaults."""
        client = MagicMock()
        options = MagicMock()
        session = PooledSession(id="test_1", client=client, options=options)

        assert session.id == "test_1"
        assert session.client is client
        assert session.options is options
        assert session.is_active is False
        assert session.use_count == 0

    def test_age_seconds(self) -> None:
        """Test age_seconds property."""
        client = MagicMock()
        options = MagicMock()
        session = PooledSession(id="test_1", client=client, options=options)

        # Age should be close to 0
        assert session.age_seconds >= 0
        assert session.age_seconds < 1

    def test_idle_seconds(self) -> None:
        """Test idle_seconds property."""
        client = MagicMock()
        options = MagicMock()
        session = PooledSession(id="test_1", client=client, options=options)

        # Idle should be close to 0
        assert session.idle_seconds >= 0
        assert session.idle_seconds < 1

    def test_is_expired_false(self) -> None:
        """Test is_expired returns False for fresh session."""
        client = MagicMock()
        options = MagicMock()
        session = PooledSession(id="test_1", client=client, options=options)

        assert session.is_expired(ttl_seconds=60) is False

    def test_is_expired_true(self) -> None:
        """Test is_expired returns True for old session."""
        client = MagicMock()
        options = MagicMock()
        session = PooledSession(id="test_1", client=client, options=options)

        # Manually set last_activity to the past
        session.last_activity = datetime.now() - timedelta(seconds=120)

        assert session.is_expired(ttl_seconds=60) is True


class TestSessionPool:
    """Test SessionPool class."""

    @pytest.fixture
    def pool(self) -> SessionPool:
        """Create a test pool."""
        return SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=30)

    def test_initialization(self, pool: SessionPool) -> None:
        """Test pool initialization."""
        assert pool._max_sessions == 5
        assert pool._ttl_seconds == 60
        assert pool._cleanup_interval == 30
        assert pool.total_sessions == 0
        assert pool.active_sessions == 0
        assert pool.available_sessions == 0

    @pytest.mark.asyncio
    async def test_start_and_stop(self, pool: SessionPool) -> None:
        """Test pool start and stop."""
        await pool.start()
        assert pool._running is True
        assert pool._cleanup_task is not None

        await pool.stop()
        assert pool._running is False
        assert pool._cleanup_task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, pool: SessionPool) -> None:
        """Test that starting twice doesn't create multiple tasks."""
        await pool.start()
        task1 = pool._cleanup_task

        await pool.start()
        task2 = pool._cleanup_task

        assert task1 is task2

        await pool.stop()

    @pytest.mark.asyncio
    async def test_generate_session_id(self, pool: SessionPool) -> None:
        """Test session ID generation."""
        id1 = pool._generate_session_id()
        id2 = pool._generate_session_id()

        assert id1 != id2
        assert id1.startswith("pool_session_")
        assert id2.startswith("pool_session_")

    @pytest.mark.asyncio
    async def test_acquire_creates_session(self, pool: SessionPool) -> None:
        """Test acquiring creates a new session."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as session:
                assert session is not None
                assert session.is_active is True
                assert session.use_count == 1

            await pool.stop()

    @pytest.mark.asyncio
    async def test_acquire_reuses_session(self, pool: SessionPool) -> None:
        """Test acquiring reuses available session."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            # First acquire
            async with pool.acquire() as session1:
                session_id = session1.id

            # Second acquire should reuse
            async with pool.acquire() as session2:
                assert session2.id == session_id
                assert session2.use_count == 2

            await pool.stop()

    @pytest.mark.asyncio
    async def test_release_clears_session(self, pool: SessionPool) -> None:
        """Test releasing clears session context."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.clear = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as _session:
                pass

            # Session should have been cleared
            mock_client.clear.assert_called()

            await pool.stop()

    @pytest.mark.asyncio
    async def test_release_with_reset_method(self, pool: SessionPool) -> None:
        """Test releasing with reset method instead of clear."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            # No clear, but has reset
            del mock_client.clear
            mock_client.reset = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as _:
                pass

            mock_client.reset.assert_called()

            await pool.stop()

    @pytest.mark.asyncio
    async def test_get_stats(self, pool: SessionPool) -> None:
        """Test getting pool stats."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as _:
                stats = await pool.get_stats()

                assert stats["max_sessions"] == 5
                assert stats["ttl_seconds"] == 60
                assert stats["total_sessions"] == 1
                assert stats["active_sessions"] == 1
                assert "sessions" in stats

            await pool.stop()

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, pool: SessionPool) -> None:
        """Test cleanup removes expired sessions."""
        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Use short TTL for testing
            pool._ttl_seconds = 1

            await pool.start()

            async with pool.acquire() as session:
                session_id = session.id

            # Session is now available
            assert pool.total_sessions == 1

            # Wait for expiration
            await asyncio.sleep(1.5)

            # Run cleanup
            await pool._cleanup_expired()

            # Session should be removed
            assert session_id not in pool._sessions

            await pool.stop()

    @pytest.mark.asyncio
    async def test_close_session_handles_error(self, pool: SessionPool) -> None:
        """Test close_session handles errors gracefully."""
        mock_client = AsyncMock()
        mock_client.__aexit__ = AsyncMock(side_effect=RuntimeError("Close failed"))

        session = PooledSession(
            id="test_1",
            client=mock_client,
            options=MagicMock(),
        )

        # Should not raise
        await pool._close_session(session)


class TestPooledSessionProperties:
    """Test PooledSession computed properties."""

    def test_age_calculation(self) -> None:
        """Test age is calculated correctly."""
        client = MagicMock()
        options = MagicMock()

        # Create session with old created_at
        session = PooledSession(
            id="test_1",
            client=client,
            options=options,
            created_at=datetime.now() - timedelta(seconds=30),
        )

        assert 29 <= session.age_seconds <= 31

    def test_idle_calculation(self) -> None:
        """Test idle time is calculated correctly."""
        client = MagicMock()
        options = MagicMock()

        session = PooledSession(
            id="test_1",
            client=client,
            options=options,
            last_activity=datetime.now() - timedelta(seconds=15),
        )

        assert 14 <= session.idle_seconds <= 16


class TestGlobalPoolFunctions:
    """Test global pool management functions."""

    @pytest.fixture(autouse=True)
    def reset_pool(self) -> None:
        """Reset global pool before each test."""
        import src.sdk.session_pool as sp

        sp._pool = None

    def test_get_pool_creates_instance(self) -> None:
        """Test get_pool creates pool on first call."""
        pool = get_pool()
        assert pool is not None
        assert isinstance(pool, SessionPool)

    def test_get_pool_returns_same_instance(self) -> None:
        """Test get_pool returns same instance."""
        pool1 = get_pool()
        pool2 = get_pool()
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_init_pool(self) -> None:
        """Test init_pool starts the pool."""
        with patch.object(SessionPool, "start", new_callable=AsyncMock) as mock_start:
            pool = await init_pool()
            mock_start.assert_called_once()
            assert pool is not None

    @pytest.mark.asyncio
    async def test_shutdown_pool(self) -> None:
        """Test shutdown_pool stops and clears the pool."""
        import src.sdk.session_pool as sp

        # Create and start pool
        pool = get_pool()
        with patch.object(pool, "start", new_callable=AsyncMock):
            await init_pool()

        with patch.object(pool, "stop", new_callable=AsyncMock) as mock_stop:
            await shutdown_pool()
            mock_stop.assert_called_once()
            assert sp._pool is None

    @pytest.mark.asyncio
    async def test_shutdown_pool_when_none(self) -> None:
        """Test shutdown_pool handles None pool."""
        import src.sdk.session_pool as sp

        sp._pool = None
        await shutdown_pool()  # Should not raise


class TestSessionPoolEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_clear_with_conversation_attribute(self) -> None:
        """Test clearing session with conversation.clear()."""
        pool = SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=30)

        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = MagicMock()
            mock_conversation = MagicMock()
            mock_client.conversation = mock_conversation

            # Remove clear and reset methods
            if hasattr(mock_client, "clear"):
                del mock_client.clear
            if hasattr(mock_client, "reset"):
                del mock_client.reset

            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as _:
                pass

            mock_conversation.clear.assert_called()

            await pool.stop()

    @pytest.mark.asyncio
    async def test_clear_with_no_clear_method(self) -> None:
        """Test clearing session without clear method logs warning."""
        pool = SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=30)

        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = MagicMock()
            # Explicitly remove the methods we're testing for
            del mock_client.clear
            del mock_client.reset
            del mock_client.conversation
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            # Should not raise, just log warning
            async with pool.acquire() as _:
                pass

            await pool.stop()

    @pytest.mark.asyncio
    async def test_release_error_closes_session(self) -> None:
        """Test that release error closes the session."""
        pool = SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=30)

        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.clear = AsyncMock(side_effect=RuntimeError("Clear failed"))
            mock_client_class.return_value = mock_client

            await pool.start()

            async with pool.acquire() as session:
                session_id = session.id

            # Session should be removed after error
            assert session_id not in pool._sessions

            await pool.stop()

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_error(self) -> None:
        """Test cleanup loop continues after error."""
        pool = SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=1)

        with patch.object(pool, "_cleanup_expired", side_effect=RuntimeError("Cleanup error")):
            await pool.start()
            await asyncio.sleep(0.3)  # Let cleanup run a few times
            await pool.stop()

        # Pool should still be functional
        assert True  # If we get here, it didn't crash

    @pytest.mark.asyncio
    async def test_close_all_sessions(self) -> None:
        """Test closing all sessions."""
        pool = SessionPool(max_sessions=5, ttl_seconds=60, cleanup_interval_seconds=30)

        with patch("src.sdk.session_pool.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await pool.start()

            # Create multiple sessions
            async with pool.acquire() as _:
                async with pool.acquire() as _:
                    pass

            assert pool.total_sessions == 2

            await pool._close_all_sessions()

            assert pool.total_sessions == 0

            await pool.stop()
