"""
TTS client — ElevenLabs primary, Deepgram Aura fallback.

Converts response text to raw 16-bit PCM audio at 16 kHz mono.
ElevenLabs convert() returns an iterator — we consume chunks eagerly
so the caller gets audio as fast as possible.
If ElevenLabs fails, falls back to Deepgram Aura.
On total failure: returns None for text-only fallback per NFR-010.
"""

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


async def _elevenlabs_tts(text: str) -> Optional[bytes]:
    """Try ElevenLabs Flash TTS. Returns PCM bytes or None."""
    settings = get_settings()

    if not settings.ELEVENLABS_API_KEY:
        logger.debug("ELEVENLABS_API_KEY not set — skipping ElevenLabs")
        return None

    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        voice_id = settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
        model_id = settings.ELEVENLABS_MODEL or "eleven_flash_v2_5"

        # convert() returns an iterator of bytes chunks — consume eagerly
        audio_chunks = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format="pcm_16000",
        )

        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            return None

        logger.info("ElevenLabs TTS produced %d bytes for %d chars", len(audio_bytes), len(text))
        return audio_bytes

    except Exception as exc:
        logger.warning("ElevenLabs TTS failed: %s — falling back to Deepgram Aura", exc)
        return None


async def _deepgram_tts(text: str) -> Optional[bytes]:
    """Fallback: Deepgram Aura TTS. Returns PCM bytes or None."""
    settings = get_settings()

    if not settings.DEEPGRAM_API_KEY:
        logger.error("DEEPGRAM_API_KEY not set — no TTS fallback available")
        return None

    try:
        from deepgram import DeepgramClient, SpeakOptions

        client = DeepgramClient(settings.DEEPGRAM_API_KEY)

        options = SpeakOptions(
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        )

        response = await client.speak.asyncrest.v("1").stream_memory(
            {"text": text},
            options,
        )

        audio_bytes: bytes = response.stream_memory.getbuffer().tobytes()
        if not audio_bytes:
            return None

        logger.info("Deepgram TTS fallback produced %d bytes for %d chars", len(audio_bytes), len(text))
        return audio_bytes

    except Exception as exc:
        logger.error("Deepgram TTS fallback also failed: %s", exc)
        return None


async def text_to_speech(text: str) -> Optional[bytes]:
    """
    Convert *text* to speech. Tries ElevenLabs first, then Deepgram Aura.

    Returns:
        bytes of 16-bit linear-PCM at 16 kHz mono on success; None on total failure.
    """
    if not text or not text.strip():
        logger.warning("text_to_speech called with empty text — skipping")
        return None

    audio = await _elevenlabs_tts(text)
    if audio:
        return audio

    return await _deepgram_tts(text)
