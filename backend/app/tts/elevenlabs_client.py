"""
ElevenLabs TTS client.

Converts response text to audio bytes via the ElevenLabs API.
On any failure (missing key, API error, empty text): returns None so the
caller can display text-only fallback per NFR-010.
"""

import logging
from typing import Optional

from elevenlabs.client import ElevenLabs

from app.config import get_settings

logger = logging.getLogger(__name__)


async def text_to_speech(text: str) -> Optional[bytes]:
    """
    Convert text to speech using ElevenLabs.

    Args:
        text: The response text to synthesise.

    Returns:
        bytes containing audio data on success; None on any failure.
    """
    if not text or not text.strip():
        logger.warning("text_to_speech called with empty text — skipping")
        return None

    settings = get_settings()

    if not settings.ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY is not set — returning None (text-only fallback)")
        return None

    try:
        client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        voice_id = settings.ELEVENLABS_VOICE_ID or "Rachel"

        audio_chunks = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_monolingual_v1",
        )

        audio_bytes = b"".join(audio_chunks)
        logger.info("TTS produced %d bytes for %d chars of text", len(audio_bytes), len(text))
        return audio_bytes

    except Exception as exc:
        logger.error("ElevenLabs TTS error: %s — returning None (text-only fallback)", exc)
        return None
