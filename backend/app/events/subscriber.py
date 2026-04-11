"""
Base async subscriber for the Arni event bus.

Usage::

    async def handle_event(channel: str, message: str) -> None:
        data = json.loads(message)
        # dispatch on data["event"]

    subscriber = EventSubscriber(redis_client)
    await subscriber.subscribe("arni:meet-1:*", handle_event)
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, str], Awaitable[None]]


class EventSubscriber:
    """Thin wrapper around a Redis pub/sub connection."""

    def __init__(self, redis: object) -> None:
        self._redis = redis

    async def subscribe(self, pattern: str, handler: MessageHandler) -> None:
        """
        Subscribe to a Redis channel pattern and dispatch each message to
        ``handler(channel, message_json)``.

        Runs until cancelled.
        """
        pubsub = self._redis.pubsub()  # type: ignore[attr-defined]
        await pubsub.psubscribe(pattern)
        logger.info("EventSubscriber: listening on pattern '%s'", pattern)

        try:
            async for message in pubsub.listen():
                if message is None:
                    continue
                if message.get("type") not in ("pmessage", "message"):
                    continue
                channel = message.get("channel", "")
                data = message.get("data", "")
                try:
                    await handler(channel, data)
                except Exception as exc:  # noqa: BLE001
                    logger.error("EventSubscriber handler error on %s: %s", channel, exc)
        except asyncio.CancelledError:
            logger.info("EventSubscriber cancelled for pattern '%s'", pattern)
            await pubsub.punsubscribe(pattern)
            raise
