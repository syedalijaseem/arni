"""
Grace Period Manager — host disconnect auto-end timer.

When the host disconnects from a meeting, a grace period countdown begins.
If the host reconnects before expiry, the countdown is canceled.
If the expiry is reached, an auto_end callback is invoked (which ends the meeting
and publishes `meeting.auto_ended` with reason='host_timeout').

Usage::

    mgr = GracePeriodManager()
    await mgr.on_host_disconnect("meet-1", "host-1", auto_end_callback=end_meeting)
    mgr.on_host_reconnect("meet-1")
    mgr.is_in_grace_period("meet-1")  # → bool
"""

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class GracePeriodManager:
    """Manages per-meeting host disconnect grace period timers."""

    def __init__(self, grace_period_seconds: Optional[int] = None) -> None:
        settings = get_settings()
        self._grace_period_seconds: int = (
            grace_period_seconds
            if grace_period_seconds is not None
            else settings.HOST_GRACE_PERIOD_MINUTES * 60
        )
        self._tasks: dict[str, asyncio.Task] = {}

    async def on_host_disconnect(
        self,
        meeting_id: str,
        host_id: str,
        auto_end_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """
        Start the grace period countdown for ``meeting_id``.

        Args:
            meeting_id: The affected meeting.
            host_id: The disconnected host's user ID (for logging).
            auto_end_callback: Async callable invoked with meeting_id if expiry is reached.
        """
        # Cancel any existing timer for this meeting
        self._cancel(meeting_id)

        async def _countdown() -> None:
            try:
                await asyncio.sleep(self._grace_period_seconds)
                logger.warning(
                    "Grace period expired for meeting=%s host=%s — auto-ending",
                    meeting_id,
                    host_id,
                )
                await auto_end_callback(meeting_id)
            except asyncio.CancelledError:
                logger.info("Grace period canceled for meeting=%s (host reconnected)", meeting_id)

        task = asyncio.create_task(_countdown())
        self._tasks[meeting_id] = task
        logger.info(
            "Grace period started for meeting=%s host=%s (%ds)",
            meeting_id,
            host_id,
            self._grace_period_seconds,
        )

    def on_host_reconnect(self, meeting_id: str) -> None:
        """Cancel the grace period countdown because the host reconnected."""
        self._cancel(meeting_id)

    def is_in_grace_period(self, meeting_id: str) -> bool:
        """Return True if a grace period timer is currently active for ``meeting_id``."""
        task = self._tasks.get(meeting_id)
        return task is not None and not task.done()

    def _cancel(self, meeting_id: str) -> None:
        task = self._tasks.pop(meeting_id, None)
        if task is not None and not task.done():
            task.cancel()


# Module-level singleton
grace_period_manager = GracePeriodManager()
