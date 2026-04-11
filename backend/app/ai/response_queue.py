"""
AI Response Queue — per-meeting FIFO request queue.

Enforces:
- 10-second cooldown between triggers (RL-001)
- Maximum 30 AI responses per meeting (RL-002)
- Sequential (FIFO) processing — next request starts only after previous completes

Design:
- One MeetingQueue instance per meeting_id, held in a module-level registry.
- The queue stores (request_id, command, speaker_id) tuples.
- process_all() drains the queue sequentially.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from app.ai.ai_service import ai_respond
from app.ai.context_manager import build_context

logger = logging.getLogger(__name__)

RATE_LIMIT_SENTINEL = "__rate_limit__"
MAX_RESPONSES_PER_MEETING = 30
DEFAULT_COOLDOWN_SECONDS = 10


class MeetingQueue:
    """
    Per-meeting sequential AI request queue.

    Attributes:
        meeting_id: Identifier of the meeting this queue serves.
        _queue: asyncio.Queue of (request_id, command, speaker_id) tuples.
        _response_count: Number of responses already generated this meeting.
        _last_trigger_time: Epoch time of the last accepted enqueue.
        _cooldown_seconds: Minimum seconds between accepted requests.
        _processing: Whether the queue consumer is running.
    """

    def __init__(self, meeting_id: str) -> None:
        self.meeting_id = meeting_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._response_count: int = 0
        self._last_trigger_time: float = 0.0
        self._cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS
        self._processing: bool = False

    async def enqueue(
        self,
        meeting_id: str,
        command: str,
        speaker_id: str,
    ) -> Optional[str]:
        """
        Attempt to add a new AI request to the queue.

        Returns:
            - A new request_id string if accepted.
            - None if dropped due to cooldown.
            - RATE_LIMIT_SENTINEL if the per-meeting cap is reached.
        """
        if self._response_count >= MAX_RESPONSES_PER_MEETING:
            logger.info(
                "Rate limit reached for meeting=%s (%d responses)",
                meeting_id,
                self._response_count,
            )
            return RATE_LIMIT_SENTINEL

        now = time.monotonic()
        elapsed = now - self._last_trigger_time
        if elapsed < self._cooldown_seconds:
            logger.info(
                "Cooldown active for meeting=%s (%.1fs < %.1fs), dropping",
                meeting_id,
                elapsed,
                self._cooldown_seconds,
            )
            return None

        self._last_trigger_time = now
        request_id = str(uuid.uuid4())
        await self._queue.put((request_id, command, speaker_id))
        logger.debug("Enqueued request_id=%s for meeting=%s", request_id, meeting_id)
        return request_id

    async def enqueue_correction(
        self,
        meeting_id: str,
        correction_text: str,
        source_document: str,
        source_excerpt: str,
    ) -> None:
        """
        Enqueue a fact-check correction item.

        The item is tagged with response_type='fact_check' so consumers can
        route it separately from regular AI responses.
        """
        item = {
            "response_type": "fact_check",
            "meeting_id": meeting_id,
            "correction_text": correction_text,
            "source_document": source_document,
            "source_excerpt": source_excerpt,
        }
        await self._queue.put(item)
        logger.debug(
            "Enqueued fact_check correction for meeting=%s", meeting_id
        )

    async def process_all(self) -> None:
        """
        Drain the queue sequentially, processing one request at a time.
        Each item calls context_manager.build_context() then ai_respond().
        """
        if self._processing:
            return
        self._processing = True
        try:
            while not self._queue.empty():
                request_id, command, speaker_id = await self._queue.get()
                try:
                    context = await build_context(self.meeting_id)
                    result = await ai_respond(self.meeting_id, command, context)
                    self._response_count += 1
                    logger.info(
                        "Processed request_id=%s for meeting=%s (total=%d)",
                        request_id,
                        self.meeting_id,
                        self._response_count,
                    )
                    yield_result = result  # noqa: F841 — callers use broadcast
                except Exception as exc:
                    logger.error(
                        "Error processing request_id=%s: %s", request_id, exc
                    )
                finally:
                    self._queue.task_done()
        finally:
            self._processing = False


# Module-level registry — one MeetingQueue per meeting_id
_queue_registry: dict[str, MeetingQueue] = {}


def get_or_create_queue(meeting_id: str) -> MeetingQueue:
    """Return the existing MeetingQueue for meeting_id, or create one."""
    if meeting_id not in _queue_registry:
        _queue_registry[meeting_id] = MeetingQueue(meeting_id)
        logger.debug("Created new MeetingQueue for meeting=%s", meeting_id)
    return _queue_registry[meeting_id]
