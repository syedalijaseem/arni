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


async def inject_audio(audio_bytes: bytes, meeting_id: str, bot=None) -> None:
    """
    Inject audio bytes into the Daily.co meeting via Arni's bot track.

    Args:
        audio_bytes: PCM/MP3 audio data produced by TTS.
        meeting_id: The meeting the audio should be injected into.
        bot: Optional ArniBot instance. When provided, uses its Daily.co
             client to send the audio. When None (e.g., in tests), logs only.
    """
    if not audio_bytes:
        logger.warning("inject_audio called with empty audio_bytes — skipping for meeting %s", meeting_id)
        return

    if bot is None:
        from app.bot.bot_manager import bot_manager
        bot = bot_manager.active_bots.get(meeting_id)

    if bot is None:
        logger.info(
            "inject_audio: no bot instance for meeting %s — audio injection skipped (test/fallback mode)",
            meeting_id,
        )
        return

    try:
        # Daily.co: send audio frames via the bot's call client
        # The bot's microphone track must already be tagged with AI_AUDIO_TRACK_TAG
        logger.info(
            "Injecting %d bytes of audio into meeting %s via ai-source track",
            len(audio_bytes),
            meeting_id,
        )
        # In production this calls bot.client.send_app_message or writes PCM
        # frames to the virtual microphone track.
        # The actual Daily.co API call is delegated to the bot instance.
        await bot.send_audio(audio_bytes)
    except Exception as exc:
        logger.error("inject_audio failed for meeting %s: %s", meeting_id, exc)
