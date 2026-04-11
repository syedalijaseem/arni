"""
DailyAudioInterface — bridges Daily.co audio with ElevenLabs Conversation.

Implements the ElevenLabs AudioInterface ABC:
  start(input_callback) — registers a callback; Daily.co audio frames are
                          forwarded to ElevenLabs via this callback
  output(audio)         — writes PCM to the Daily.co virtual microphone
  interrupt()           — clears any buffered output audio
  stop()                — cleanup

Audio format: 16-bit PCM mono at 16 kHz (both directions).
"""

import asyncio
import logging
import threading
from typing import Callable, Optional

from elevenlabs.conversational_ai.conversation import AudioInterface

logger = logging.getLogger(__name__)


class DailyAudioInterface(AudioInterface):
    def __init__(self, virtual_mic):
        self._virtual_mic = virtual_mic
        self._input_callback: Optional[Callable[[bytes], None]] = None
        self._running = False

    def start(self, input_callback: Callable[[bytes], None]):
        """Called by ElevenLabs Conversation when session starts."""
        self._input_callback = input_callback
        self._running = True
        logger.info("DailyAudioInterface started")

    def stop(self):
        """Called by ElevenLabs Conversation when session ends."""
        self._running = False
        self._input_callback = None
        logger.info("DailyAudioInterface stopped")

    def output(self, audio: bytes):
        """Called by ElevenLabs with agent speech PCM. Write to Daily.co mic."""
        if not self._running or not audio:
            return
        try:
            self._virtual_mic.write_frames(audio)
        except Exception as exc:
            logger.error("DailyAudioInterface.output error: %s", exc)

    def interrupt(self):
        """Called by ElevenLabs when user interrupts agent. Nothing to flush."""
        logger.debug("DailyAudioInterface interrupt signal")

    def feed_audio(self, pcm_bytes: bytes):
        """Called by ArniBot when Daily.co delivers participant audio frames.

        Forwards the audio to ElevenLabs for STT processing.
        """
        if self._running and self._input_callback and pcm_bytes:
            try:
                self._input_callback(pcm_bytes)
            except Exception as exc:
                logger.error("DailyAudioInterface.feed_audio error: %s", exc)
