"""
Lobby Manager — Redis-backed waiting room state.

Waiting room state is ephemeral (Redis only, never MongoDB).
Each meeting's waiting room is stored in a Redis hash:
  Key:   lobby:{meeting_id}
  Field: user_id
  Value: joined_at timestamp (ISO string)
  TTL:   24 hours

Usage::

    manager = LobbyManager()
    await manager.add_to_waiting_room("meet-1", "user-2")
    users = await manager.get_waiting_room("meet-1")
    await manager.remove_from_waiting_room("meet-1", "user-2")
    await manager.clear_waiting_room("meet-1")
"""

import logging
from datetime import datetime, timezone

from app.database import get_redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "lobby"
_TTL_SECONDS = 86_400  # 24 hours


def _key(meeting_id: str) -> str:
    return f"{_KEY_PREFIX}:{meeting_id}"


class LobbyManager:
    """Redis-backed per-meeting waiting room."""

    async def add_to_waiting_room(self, meeting_id: str, user_id: str) -> None:
        """Add a user to the waiting room for ``meeting_id``."""
        redis = get_redis()
        joined_at = datetime.now(timezone.utc).isoformat()
        await redis.hset(_key(meeting_id), user_id, joined_at)
        await redis.expire(_key(meeting_id), _TTL_SECONDS)
        logger.info("Lobby: added user=%s to waiting room for meeting=%s", user_id, meeting_id)

    async def get_waiting_room(self, meeting_id: str) -> list[str]:
        """Return a list of user IDs currently in the waiting room."""
        redis = get_redis()
        raw_keys = await redis.hkeys(_key(meeting_id))
        return [k.decode() if isinstance(k, bytes) else k for k in raw_keys]

    async def remove_from_waiting_room(self, meeting_id: str, user_id: str) -> None:
        """Remove a specific user from the waiting room."""
        redis = get_redis()
        await redis.hdel(_key(meeting_id), user_id)
        logger.info("Lobby: removed user=%s from waiting room for meeting=%s", user_id, meeting_id)

    async def clear_waiting_room(self, meeting_id: str) -> None:
        """Delete the entire waiting room hash for ``meeting_id``."""
        redis = get_redis()
        await redis.delete(_key(meeting_id))
        logger.info("Lobby: cleared waiting room for meeting=%s", meeting_id)


# Module-level singleton for use by routers
lobby_manager = LobbyManager()
