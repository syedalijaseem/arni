"""
ArniBot — Passive/Active mode meeting assistant on Daily.co.

Passive Mode (always on):
  - Deepgram transcribes all speech
  - Final transcripts saved to MongoDB + broadcast to WebSocket
  - Arni stays completely silent

Active Mode (triggered by wake word or push-to-talk):
  - Claude generates response using meeting context
  - ElevenLabs Flash speaks the response
  - Returns to Passive Mode immediately after
"""

import asyncio
import logging
import re
import time
from typing import Dict, Any

import daily
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
)

from app.config import get_settings
from app.models.transcript import TranscriptCreate
from app.bot.wake_word import WakeWordDetector

logger = logging.getLogger(__name__)

AI_AUDIO_TRACK_TAG = "ai-source"

_STOP_RE = re.compile(
    r"^(?:stop|wait|cancel|quiet|enough)[\s.!?]*$",
    re.IGNORECASE,
)


class ArniEventHandler(daily.EventHandler):
    def __init__(self, bot: "ArniBot"):
        self.bot = bot

    def on_participant_joined(self, participant):
        sid = participant["id"]
        name = participant["info"].get("userName", "")
        uid = participant["info"].get("userId") or participant.get("user_id", name)
        self.bot.participants[sid] = {"user_id": uid, "name": name or uid}
        asyncio.run_coroutine_threadsafe(self.bot._start_deepgram(sid), self.bot.loop)

    def on_participant_left(self, participant, reason):
        sid = participant["id"]
        self.bot.participants.pop(sid, None)
        asyncio.run_coroutine_threadsafe(self.bot._stop_deepgram(sid), self.bot.loop)


class ArniBot:
    def __init__(self, meeting_id: str, room_url: str, token: str,
                 broadcast_callback, wake_word_callback=None):
        self.meeting_id = meeting_id
        self.room_url = room_url
        self.token = token
        self.broadcast_callback = broadcast_callback
        self.wake_word_callback = wake_word_callback

        self.settings = get_settings()
        self.event_handler = ArniEventHandler(self)
        self.client = daily.CallClient(event_handler=self.event_handler)
        self.deepgram = DeepgramClient(self.settings.DEEPGRAM_API_KEY)

        self.virtual_mic = daily.Daily.create_microphone_device(
            "arni-mic", sample_rate=16000, channels=1, non_blocking=True,
        )
        self.client.update_inputs({
            "camera": False,
            "microphone": {"isEnabled": True, "settings": {"deviceId": "arni-mic"}},
        })

        self.participants: Dict[str, dict] = {}
        self.dg_connections: Dict[str, Any] = {}
        self.AI_AUDIO_TRACK_TAG = AI_AUDIO_TRACK_TAG
        self.wake_word_detector = WakeWordDetector()

        # State: busy = processing Claude or speaking TTS
        self._busy = False
        self._cancel = asyncio.Event()
        self._tts_stop_time: float = 0.0

        # Utterance buffer per speaker (groups fragmented speech)
        self._buffers: Dict[str, dict] = {}
        self._silence_s: float = self.settings.UTTERANCE_SILENCE_MS / 1000.0

        self.loop = asyncio.get_running_loop()

    # ── Deepgram STT ─────────────────────────────────────────────────

    async def _start_deepgram(self, participant_id: str):
        try:
            dg = self.deepgram.listen.asyncwebsocket.v("1")

            async def on_message(_conn, result, **kwargs):
                if not result.channel.alternatives:
                    return
                text = result.channel.alternatives[0].transcript
                if not text:
                    return

                is_final = result.is_final
                p = self.participants.get(participant_id, {})
                speaker_id = p.get("user_id", participant_id)
                speaker_name = p.get("name", speaker_id)

                # PASSIVE MODE: always broadcast + save final transcripts
                await self.broadcast_callback(TranscriptCreate(
                    meeting_id=self.meeting_id,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    text=text,
                    is_final=is_final,
                ))

                # Only process FINAL transcripts for active mode
                if not is_final:
                    return
                if speaker_id == "arni":
                    return
                if not self.wake_word_callback:
                    return

                # Discard overlap speech after TTS stops (500ms window)
                if time.time() < self._tts_stop_time + 0.5:
                    return

                # Stop phrase — always checked, even when busy
                if _STOP_RE.match(text.strip()):
                    if self._busy:
                        self._cancel.set()
                    self._clear_buffer(speaker_id)
                    return

                # Skip if busy (no queue)
                if self._busy:
                    return

                # Buffer the transcript, wait for silence
                self._append_buffer(speaker_id, speaker_name, text)

            dg.on(LiveTranscriptionEvents.Transcript, on_message)

            ok = await dg.start(LiveOptions(
                model="nova-2",
                language="en-US",
                encoding="linear16",
                channels=1,
                sample_rate=16000,
                interim_results=True,
                punctuate=True,
                smart_format=True,
                filler_words=False,
                endpointing=300,
                utterance_end_ms=1000,
                vad_events=True,
            ))
            if not ok:
                logger.error("Failed to connect to Deepgram")
                return

            self.dg_connections[participant_id] = dg

            def on_audio(pid, audio_data, audio_source=None):
                if dg and audio_data.audio_frames:
                    asyncio.run_coroutine_threadsafe(
                        dg.send(audio_data.audio_frames), self.loop
                    )

            self.client.set_audio_renderer(participant_id, on_audio)
        except Exception as e:
            logger.error("Deepgram setup failed for %s: %s", participant_id, e)

    async def _stop_deepgram(self, participant_id: str):
        self.client.set_audio_renderer(participant_id, None)
        dg = self.dg_connections.pop(participant_id, None)
        if dg:
            await dg.finish()

    # ── Utterance buffer ─────────────────────────────────────────────

    def _append_buffer(self, speaker_id: str, speaker_name: str, text: str):
        buf = self._buffers.get(speaker_id)
        if buf:
            if buf["timer"] is not None:
                buf["timer"].cancel()
            buf["text"] = (buf["text"] + " " + text).strip()
        else:
            buf = {"text": text, "name": speaker_name, "timer": None}
            self._buffers[speaker_id] = buf

        buf["timer"] = self.loop.call_later(
            self._silence_s,
            lambda sid=speaker_id: asyncio.run_coroutine_threadsafe(
                self._flush_buffer(sid), self.loop
            ),
        )

    def _clear_buffer(self, speaker_id: str):
        buf = self._buffers.pop(speaker_id, None)
        if buf and buf["timer"] is not None:
            buf["timer"].cancel()

    async def _flush_buffer(self, speaker_id: str):
        buf = self._buffers.pop(speaker_id, None)
        if not buf or not buf["text"].strip():
            return
        if self._busy:
            return

        # WAKE WORD IS THE ONLY GATE
        result = self.wake_word_detector.detect(
            buf["text"], speaker_id, buf["name"],
        )
        if not result:
            return

        # ACTIVE MODE: trigger AI response
        logger.info("Wake: %s said %r", buf["name"], result.command)
        self._busy = True
        try:
            await self.wake_word_callback(
                meeting_id=self.meeting_id, result=result,
            )
        finally:
            self._busy = False

    # ── Audio output (TTS playback) ──────────────────────────────────

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Stream PCM in 100ms chunks. Cancellable between chunks."""
        if not audio_bytes:
            return
        self._cancel.clear()
        chunk_size = 3200  # 100ms at 16kHz 16-bit mono
        offset = 0
        try:
            while offset < len(audio_bytes):
                if self._cancel.is_set():
                    break
                await self.loop.run_in_executor(
                    None, self.virtual_mic.write_frames,
                    audio_bytes[offset:offset + chunk_size],
                )
                offset += chunk_size
        finally:
            self._tts_stop_time = time.time()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def join(self):
        logger.info("Arni Bot joining meeting %s", self.meeting_id)
        self.client.set_user_name("Arni Bot")
        self.client.join(self.room_url, self.token)

    async def leave(self):
        logger.info("Arni Bot leaving meeting %s", self.meeting_id)
        self.client.leave()
        for pid in list(self.dg_connections):
            await self._stop_deepgram(pid)
        self.client.release()
