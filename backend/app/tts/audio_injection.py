"""
Audio injection into Daily.co meeting via Arni's bot track.

Arni's microphone track is tagged with `audio_track_tag: "ai-source"` so
that Deepgram STT will never receive or transcribe Arni's own speech
(FR-034, §3 Audio Feedback Loop Prevention).
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# This tag is set on Arni's Daily.co microphone track so the audio
# routing layer can identify and exclude it from STT.
AI_AUDIO_TRACK_TAG = "ai-source"


async def inject_audio(audio_bytes: bytes, meeting_id: str, bot=None) -> bool:
    """
    Inject audio bytes into the Daily.co meeting via Arni's bot track.

    Returns True on success, False on failure.
    Retries up to 2 times on transient failures.
    """
    if not audio_bytes:
        logger.warning("inject_audio called with empty audio_bytes — skipping for meeting %s", meeting_id)
        return False

    if bot is None:
        from app.bot.bot_manager import bot_manager
        bot = bot_manager.active_bots.get(meeting_id)

    if bot is None:
        logger.error(
            "inject_audio: no active bot for meeting %s — cannot inject audio",
            meeting_id,
        )
        return False

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(
                "inject_audio: attempt %d/%d, %d bytes, meeting=%s",
                attempt, max_attempts, len(audio_bytes), meeting_id,
            )
            await bot.send_audio(audio_bytes)
            logger.info("inject_audio: SUCCESS for meeting=%s", meeting_id)
            return True
        except Exception as exc:
            logger.error(
                "inject_audio: attempt %d/%d FAILED for meeting=%s: %s",
                attempt, max_attempts, meeting_id, exc,
            )
            if attempt < max_attempts:
                await asyncio.sleep(0.5 * attempt)

    logger.error("inject_audio: all %d attempts failed for meeting=%s", max_attempts, meeting_id)
    return False
