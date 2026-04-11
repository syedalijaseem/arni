"""
TDD tests for Task 6: Meeting Access Control.

Tests cover:
- require_host: host passes; non-host raises 403
- require_participant: invited user passes; uninvited raises 403 with correct message
- invite list email matching: case-insensitive
- lobby_manager: add/get/remove/clear operations
- grace_period: timer fires callback; canceled on reconnect
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# require_host dependency tests
# ---------------------------------------------------------------------------

class TestRequireHost:

    @pytest.mark.asyncio
    async def test_host_passes(self):
        """require_host returns meeting dict when current_user is the host."""
        from app.deps import require_host

        meeting = {"_id": "meet-1", "host_id": "user-1"}
        current_user = {"id": "user-1", "email": "host@example.com"}

        result = await require_host(meeting=meeting, current_user=current_user)
        assert result == meeting

    @pytest.mark.asyncio
    async def test_non_host_raises_403(self):
        """require_host raises 403 when current_user is not the host."""
        from fastapi import HTTPException
        from app.deps import require_host

        meeting = {"_id": "meet-1", "host_id": "user-1"}
        current_user = {"id": "user-2", "email": "participant@example.com"}

        with pytest.raises(HTTPException) as exc_info:
            await require_host(meeting=meeting, current_user=current_user)

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# require_participant dependency tests
# ---------------------------------------------------------------------------

class TestRequireParticipant:

    @pytest.mark.asyncio
    async def test_host_passes_even_without_invite_list(self):
        """require_participant allows host regardless of invite_list."""
        from app.deps import require_participant

        meeting = {
            "_id": "meet-1",
            "host_id": "user-1",
            "invite_list": [],
        }
        current_user = {"id": "user-1", "email": "host@example.com"}

        result = await require_participant(meeting=meeting, current_user=current_user)
        assert result == meeting

    @pytest.mark.asyncio
    async def test_invited_user_passes(self):
        """require_participant allows user whose email is in invite_list."""
        from app.deps import require_participant

        meeting = {
            "_id": "meet-1",
            "host_id": "user-1",
            "invite_list": ["alice@example.com"],
        }
        current_user = {"id": "user-2", "email": "alice@example.com"}

        result = await require_participant(meeting=meeting, current_user=current_user)
        assert result == meeting

    @pytest.mark.asyncio
    async def test_uninvited_user_raises_403(self):
        """require_participant raises 403 for user not in invite_list."""
        from fastapi import HTTPException
        from app.deps import require_participant

        meeting = {
            "_id": "meet-1",
            "host_id": "user-1",
            "invite_list": ["alice@example.com"],
        }
        current_user = {"id": "user-3", "email": "eve@example.com"}

        with pytest.raises(HTTPException) as exc_info:
            await require_participant(meeting=meeting, current_user=current_user)

        assert exc_info.value.status_code == 403
        assert "not authorized" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invite_list_email_match_is_case_insensitive(self):
        """require_participant matches emails case-insensitively."""
        from app.deps import require_participant

        meeting = {
            "_id": "meet-1",
            "host_id": "user-1",
            "invite_list": ["Alice@Example.COM"],
        }
        current_user = {"id": "user-2", "email": "alice@example.com"}

        result = await require_participant(meeting=meeting, current_user=current_user)
        assert result == meeting


# ---------------------------------------------------------------------------
# LobbyManager tests
# ---------------------------------------------------------------------------

class TestLobbyManager:

    @pytest.mark.asyncio
    async def test_add_to_waiting_room(self):
        """add_to_waiting_room stores user in Redis hash with TTL."""
        with patch("app.lobby.lobby_manager.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis_fn.return_value = mock_redis

            from app.lobby.lobby_manager import LobbyManager
            manager = LobbyManager()
            await manager.add_to_waiting_room("meet-1", "user-1")

        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_waiting_room_returns_user_ids(self):
        """get_waiting_room returns list of user IDs from Redis hash."""
        with patch("app.lobby.lobby_manager.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis_fn.return_value = mock_redis
            mock_redis.hkeys.return_value = [b"user-1", b"user-2"]

            from app.lobby.lobby_manager import LobbyManager
            manager = LobbyManager()
            result = await manager.get_waiting_room("meet-1")

        assert "user-1" in result
        assert "user-2" in result

    @pytest.mark.asyncio
    async def test_remove_from_waiting_room(self):
        """remove_from_waiting_room deletes user from Redis hash."""
        with patch("app.lobby.lobby_manager.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis_fn.return_value = mock_redis

            from app.lobby.lobby_manager import LobbyManager
            manager = LobbyManager()
            await manager.remove_from_waiting_room("meet-1", "user-1")

        mock_redis.hdel.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_waiting_room(self):
        """clear_waiting_room deletes the entire Redis hash."""
        with patch("app.lobby.lobby_manager.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis_fn.return_value = mock_redis

            from app.lobby.lobby_manager import LobbyManager
            manager = LobbyManager()
            await manager.clear_waiting_room("meet-1")

        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_waiting_room_uses_redis_not_mongo(self):
        """LobbyManager only uses Redis — never touches MongoDB."""
        import app.lobby.lobby_manager as lm_module

        # Verify get_database is not referenced in lobby_manager (Redis only)
        assert not hasattr(lm_module, "get_database"), (
            "lobby_manager must not import get_database — waiting room is Redis-only"
        )

        with patch("app.lobby.lobby_manager.get_redis") as mock_redis_fn:
            mock_redis = AsyncMock()
            mock_redis_fn.return_value = mock_redis

            from app.lobby.lobby_manager import LobbyManager
            manager = LobbyManager()
            await manager.add_to_waiting_room("meet-1", "user-1")
            await manager.clear_waiting_room("meet-1")

        # Verify only Redis was called
        mock_redis.hset.assert_called()
        mock_redis.delete.assert_called()


# ---------------------------------------------------------------------------
# GracePeriodManager tests
# ---------------------------------------------------------------------------

class TestGracePeriodManager:

    @pytest.mark.asyncio
    async def test_on_host_disconnect_fires_callback_after_grace_period(self):
        """Grace period fires the auto_end callback after the timeout."""
        callback = AsyncMock()

        from app.lobby.grace_period import GracePeriodManager
        mgr = GracePeriodManager(grace_period_seconds=0)  # 0s for test speed
        await mgr.on_host_disconnect("meet-1", "host-1", auto_end_callback=callback)

        # Give the task a tick to run
        import asyncio
        await asyncio.sleep(0.05)

        callback.assert_called_once_with("meet-1")

    @pytest.mark.asyncio
    async def test_reconnect_before_expiry_cancels_callback(self):
        """Host reconnect before expiry cancels the auto_end callback."""
        callback = AsyncMock()

        from app.lobby.grace_period import GracePeriodManager
        mgr = GracePeriodManager(grace_period_seconds=10)  # long enough not to fire
        await mgr.on_host_disconnect("meet-1", "host-1", auto_end_callback=callback)
        mgr.on_host_reconnect("meet-1")

        import asyncio
        await asyncio.sleep(0.05)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_in_grace_period_returns_true_while_active(self):
        """is_in_grace_period returns True while timer is running."""
        from app.lobby.grace_period import GracePeriodManager
        mgr = GracePeriodManager(grace_period_seconds=10)
        await mgr.on_host_disconnect("meet-1", "host-1", auto_end_callback=AsyncMock())

        assert mgr.is_in_grace_period("meet-1") is True

        mgr.on_host_reconnect("meet-1")

    @pytest.mark.asyncio
    async def test_is_in_grace_period_returns_false_for_unknown_meeting(self):
        """is_in_grace_period returns False for a meeting with no active timer."""
        from app.lobby.grace_period import GracePeriodManager
        mgr = GracePeriodManager()
        assert mgr.is_in_grace_period("no-such-meeting") is False
