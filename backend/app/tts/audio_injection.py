"""
Audio injection — delivers TTS audio to meeting participants.

Primary path: broadcast base64-encoded WAV over WebSocket so every
connected browser client can play it directly with the Web Audio API.
Secondary: also attempt Daily.co virtual mic injection if a bot is present.

The frontend is responsible for deduplicating if both paths produce
audible output (e.g. muting the WebSocket audio when Daily.co mic is active).
"""

import asyncio
import base64
import logging
import struct

logger = logging.getLogger(__name__)

AI_AUDIO_TRACK_TAG = "ai-source"


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw PCM bytes in a WAV header so browsers can decode it."""
    data_size = len(pcm)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate, byte_rate, block_align, bits,
        b"data", data_size,
    )
    return header + pcm


async def inject_audio(audio_bytes: bytes, meeting_id: str, bot=None) -> bool:
    """
    Deliver TTS audio to participants via WebSocket (primary) and
    Daily.co virtual mic (secondary, best-effort).

    Returns True if WebSocket broadcast succeeded.
    """
    if not audio_bytes:
        logger.warning("inject_audio: empty audio — skipping for meeting %s", meeting_id)
        return False

    # ── Primary: WebSocket broadcast ──────────────────────────────────
    ws_ok = False
    try:
        from app.routers.transcripts import manager

        wav = _pcm_to_wav(audio_bytes)
        b64 = base64.b64encode(wav).decode("ascii")
        await manager.broadcast(meeting_id, {
            "type": "arni_audio",
            "audio": b64,
            "format": "wav",
        })
        logger.info(
            "inject_audio: WebSocket broadcast OK, %d PCM bytes → %d WAV bytes, meeting=%s",
            len(audio_bytes), len(wav), meeting_id,
        )
        ws_ok = True
    except Exception as exc:
        logger.error("inject_audio: WebSocket broadcast FAILED for meeting=%s: %s", meeting_id, exc)

    # ── Secondary: Daily.co virtual mic (best-effort, disabled to
    #    prevent double-audio until frontend dedup is implemented) ──────
    # if bot is None:
    #     from app.bot.bot_manager import bot_manager
    #     bot = bot_manager.active_bots.get(meeting_id)
    #
    # if bot is not None:
    #     try:
    #         await bot.send_audio(audio_bytes)
    #         logger.info("inject_audio: Daily.co mic injection OK for meeting=%s", meeting_id)
    #     except Exception as exc:
    #         logger.warning("inject_audio: Daily.co mic injection failed for meeting=%s: %s", meeting_id, exc)

    return ws_ok
