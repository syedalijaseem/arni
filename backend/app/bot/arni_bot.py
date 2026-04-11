"""
ArniBot — Passive/Active mode meeting assistant on Daily.co.

STT: ElevenLabs Scribe v2 Realtime (replaces Deepgram)
TTS: ElevenLabs Flash v2.5 (unchanged)
LLM: Claude Sonnet (unchanged)

Passive Mode (always on):
  - Scribe transcribes all speech
  - Final transcripts saved to MongoDB + broadcast to WebSocket
  - Arni stays completely silent

Active Mode (triggered by wake word or push-to-talk):
  - Claude generates response using meeting context + RAG docs
  - ElevenLabs Flash speaks the response
  - Returns to Passive Mode immediately after
"""

import asyncio
import base64
import logging
import re
import time
from typing import Dict, Any

import daily
from elevenlabs.realtime.scribe import ScribeRealtime, AudioFormat, CommitStrategy

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
        asyncio.run_coroutine_threadsafe(self.bot._start_stt(sid), self.bot.loop)

    def on_participant_left(self, participant, reason):
        sid = participant["id"]
        self.bot.participants.pop(sid, None)
        asyncio.run_coroutine_threadsafe(self.bot._stop_stt(sid), self.bot.loop)


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

        self.virtual_mic = daily.Daily.create_microphone_device(
            "arni-mic", sample_rate=16000, channels=1, non_blocking=True,
        )
        self.client.update_inputs({
            "camera": False,
            "microphone": {"isEnabled": True, "settings": {"deviceId": "arni-mic"}},
        })

        self.participants: Dict[str, dict] = {}
        self.stt_connections: Dict[str, Any] = {}
        self.AI_AUDIO_TRACK_TAG = AI_AUDIO_TRACK_TAG
        self.wake_word_detector = WakeWordDetector()

        # State
        self._busy = False
        self._cancel = asyncio.Event()
        self._tts_stop_time: float = 0.0

        # Utterance buffer per speaker
        self._buffers: Dict[str, dict] = {}
        self._silence_s: float = self.settings.UTTERANCE_SILENCE_MS / 1000.0

        self.loop = asyncio.get_running_loop()

    # ── ElevenLabs Scribe v2 Realtime STT ────────────────────────────

    async def _start_stt(self, participant_id: str):
        """Start ElevenLabs Scribe realtime STT for a participant."""
        try:
            scribe = ScribeRealtime(
                api_key=self.settings.ELEVENLABS_API_KEY,
            )
            conn = await scribe.connect({
                "model_id": "scribe_v2_realtime",
                "audio_format": AudioFormat.PCM_16000,
                "sample_rate": 16000,
                "commit_strategy": CommitStrategy.VAD,
                "language_code": "en",
            })

            p = self.participants.get(participant_id, {})
            speaker_id = p.get("user_id", participant_id)
            speaker_name = p.get("name", speaker_id)

            # Handle partial (interim) transcripts
            def on_partial(data):
                text = data.get("text", "")
                if not text:
                    return
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_callback(TranscriptCreate(
                        meeting_id=self.meeting_id,
                        speaker_id=speaker_id,
                        speaker_name=speaker_name,
                        text=text,
                        is_final=False,
                    )),
                    self.loop,
                )

            # Handle committed (final) transcripts
            def on_committed(data):
                text = data.get("text", "")
                if not text:
                    return
                asyncio.run_coroutine_threadsafe(
                    self._handle_final_transcript(
                        speaker_id, speaker_name, text,
                    ),
                    self.loop,
                )

            conn.on("partial_transcript", on_partial)
            conn.on("committed_transcript", on_committed)

            self.stt_connections[participant_id] = conn

            # Forward Daily.co audio frames to Scribe
            def on_audio(pid, audio_data, audio_source=None):
                if conn and audio_data.audio_frames:
                    b64 = base64.b64encode(audio_data.audio_frames).decode()
                    asyncio.run_coroutine_threadsafe(
                        conn.send({"audio_base_64": b64}),
                        self.loop,
                    )

            self.client.set_audio_renderer(participant_id, on_audio)
            logger.info("Scribe STT started for participant %s", participant_id)

        except Exception as e:
            logger.error("Scribe STT setup failed for %s: %s", participant_id, e)

    async def _stop_stt(self, participant_id: str):
        """Stop Scribe STT for a participant."""
        self.client.set_audio_renderer(participant_id, None)
        conn = self.stt_connections.pop(participant_id, None)
        if conn:
            await conn.close()

    async def _handle_final_transcript(self, speaker_id: str, speaker_name: str, text: str):
        """Process a final (committed) transcript from Scribe."""
        # PASSIVE MODE: always broadcast + save
        await self.broadcast_callback(TranscriptCreate(
            meeting_id=self.meeting_id,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            text=text,
            is_final=True,
        ))

        # Never process Arni's own speech
        if speaker_id == "arni":
            return
        if not self.wake_word_callback:
            return

        # Discard overlap speech after TTS stops
        if time.time() < self._tts_stop_time + 0.5:
            return

        # Stop phrase check
        if _STOP_RE.match(text.strip()):
            if self._busy:
                self._cancel.set()
            self._clear_buffer(speaker_id)
            return

        # Skip if busy
        if self._busy:
            return

        # Buffer the transcript
        self._append_buffer(speaker_id, speaker_name, text)

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

        # Wake word is the only gate
        result = self.wake_word_detector.detect(
            buf["text"], speaker_id, buf["name"],
        )
        if not result:
            return

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
        for pid in list(self.stt_connections):
            await self._stop_stt(pid)
        self.client.release()
