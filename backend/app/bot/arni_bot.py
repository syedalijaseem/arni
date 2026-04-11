import asyncio
import logging
import re
import time
from typing import Dict, Any, Optional

import daily
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from app.config import get_settings
from app.models.transcript import TranscriptCreate
from app.bot.wake_word import WakeWordDetector, WakeWordResult

logger = logging.getLogger(__name__)

# Arni's Daily.co audio track tag — prevents Deepgram STT from processing
# Arni's own synthesised speech (FR-034, §3 Audio Feedback Loop Prevention).
AI_AUDIO_TRACK_TAG = "ai-source"


class ArniEventHandler(daily.EventHandler):
    def __init__(self, bot: "ArniBot"):
        self.bot = bot

    def on_participant_joined(self, participant):
        session_id = participant["id"]
        user_name = participant["info"].get("userName", "")
        user_id = participant["info"].get("userId") or participant.get("user_id", user_name)

        self.bot.participant_id_to_user[session_id] = user_id
        self.bot.participant_id_to_name[session_id] = user_name or user_id
        logger.info(f"Bot saw participant join: {session_id} ({user_name} -> {user_id})")

        asyncio.run_coroutine_threadsafe(
            self.bot._start_deepgram_for_participant(session_id),
            self.bot.loop
        )

    def on_participant_left(self, participant, reason):
        session_id = participant["id"]
        logger.info(f"Bot saw participant leave: {session_id}")

        if session_id in self.bot.participant_id_to_user:
            del self.bot.participant_id_to_user[session_id]
        if session_id in self.bot.participant_id_to_name:
            del self.bot.participant_id_to_name[session_id]

        asyncio.run_coroutine_threadsafe(
            self.bot._stop_deepgram_for_participant(session_id),
            self.bot.loop
        )


class ArniBot:
    def __init__(self, meeting_id: str, room_url: str, token: str, broadcast_callback, wake_word_callback=None):
        self.meeting_id = meeting_id
        self.room_url = room_url
        self.token = token
        self.broadcast_callback = broadcast_callback
        self.wake_word_callback = wake_word_callback

        self.settings = get_settings()
        self.event_handler = ArniEventHandler(self)
        self.client = daily.CallClient(event_handler=self.event_handler)
        self.deepgram = DeepgramClient(self.settings.DEEPGRAM_API_KEY)

        # Virtual microphone for sending TTS audio into the meeting.
        self.virtual_mic = daily.Daily.create_microphone_device(
            "arni-mic",
            sample_rate=16000,
            channels=1,
            non_blocking=True,
        )

        self.client.update_inputs({
            "camera": False,
            "microphone": {
                "isEnabled": True,
                "settings": {"deviceId": "arni-mic"},
            },
        })

        self.participant_id_to_user: Dict[str, str] = {}
        self.participant_id_to_name: Dict[str, str] = {}
        self.dg_connections: Dict[str, Any] = {}

        self.AI_AUDIO_TRACK_TAG = AI_AUDIO_TRACK_TAG
        self.wake_word_detector = WakeWordDetector()

        # Speaking state
        self._speaking = False
        self._cancel_event = asyncio.Event()
        self._tts_stop_time: float = 0.0  # timestamp when TTS was cancelled/finished

        # Stop phrases — checked BEFORE anything else on final transcripts.
        self._stop_re = re.compile(
            r"^(?:stop|stop arni|stop arnie|hey stop|cancel|nevermind|never mind"
            r"|wait|hold on|pause)[\s.!?]*$",
            re.IGNORECASE,
        )

        # Utterance buffer: groups fragmented final transcripts into one utterance.
        # speaker_id -> {"text": str, "speaker_name": str, "timer": asyncio.TimerHandle}
        self._utterance_buffers: Dict[str, dict] = {}
        self._utterance_silence_s: float = self.settings.UTTERANCE_SILENCE_MS / 1000.0

        self.loop = asyncio.get_running_loop()

    # ------------------------------------------------------------------
    # Deepgram per-participant setup
    # ------------------------------------------------------------------

    async def _start_deepgram_for_participant(self, participant_id: str):
        try:
            dg_connection = self.deepgram.listen.asyncwebsocket.v("1")

            async def on_message(_conn, result, **kwargs):
                if not result.channel.alternatives:
                    return
                transcript = result.channel.alternatives[0].transcript
                if not transcript:
                    return

                is_final = result.is_final

                speaker_id = self.participant_id_to_user.get(participant_id, participant_id)
                speaker_name = self.participant_id_to_name.get(participant_id, speaker_id)

                # Always broadcast to WebSocket for live display (interim + final)
                payload = TranscriptCreate(
                    meeting_id=self.meeting_id,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    text=transcript,
                    is_final=is_final,
                )
                await self.broadcast_callback(payload)

                # --- Everything below is FINAL-only processing ---
                if not is_final:
                    return

                # Fix 4: Never process Arni's own speech (FR-034, FR-035)
                if speaker_id == "arni":
                    return

                if not self.wake_word_callback:
                    return

                # Fix 3: Discard overlap speech right after TTS stops
                now = time.time()
                if now < self._tts_stop_time + 0.5:
                    logger.debug("Discarding overlap transcript (%.0fms after TTS stop): %r",
                                 (now - self._tts_stop_time) * 1000, transcript)
                    return

                # Stop phrase check — highest priority, even while speaking
                if self._stop_re.match(transcript.strip()):
                    if self._speaking:
                        logger.info("Stop phrase detected from %s — cancelling speech", speaker_name)
                        self._cancel_event.set()
                    # Clear utterance buffer for this speaker
                    self._clear_utterance_buffer(speaker_id)
                    return

                # Transcript lockout: discard everything while speaking
                if self._speaking:
                    logger.debug("Discarding transcript while speaking: %r", transcript)
                    return

                # Fix 2: Buffer final transcripts into utterances
                self._append_to_utterance_buffer(speaker_id, speaker_name, transcript)

            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

            options = LiveOptions(
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
            )

            if await dg_connection.start(options) is False:
                logger.error("Failed to connect to Deepgram")
                return

            self.dg_connections[participant_id] = dg_connection

            def on_audio_data(participant_session_id, audio_data, audio_source=None):
                if dg_connection and audio_data.audio_frames:
                    asyncio.run_coroutine_threadsafe(
                        dg_connection.send(audio_data.audio_frames),
                        self.loop
                    )

            self.client.set_audio_renderer(participant_id, on_audio_data)

        except Exception as e:
            logger.error(f"Error setting up Deepgram for {participant_id}: {e}")

    async def _stop_deepgram_for_participant(self, participant_id: str):
        self.client.set_audio_renderer(participant_id, None)
        dg_connection = self.dg_connections.get(participant_id)
        if dg_connection:
            await dg_connection.finish()
            del self.dg_connections[participant_id]

    # ------------------------------------------------------------------
    # Utterance buffering
    # ------------------------------------------------------------------

    def _append_to_utterance_buffer(self, speaker_id: str, speaker_name: str, text: str):
        """Add a final transcript fragment to the speaker's buffer and (re)start the silence timer."""
        buf = self._utterance_buffers.get(speaker_id)
        if buf:
            # Cancel existing timer, append text
            if buf["timer"] is not None:
                buf["timer"].cancel()
            buf["text"] = (buf["text"] + " " + text).strip()
        else:
            buf = {"text": text, "speaker_name": speaker_name, "timer": None}
            self._utterance_buffers[speaker_id] = buf

        # Start silence timer — when it fires, the buffered text is treated as one utterance
        buf["timer"] = self.loop.call_later(
            self._utterance_silence_s,
            lambda sid=speaker_id: asyncio.run_coroutine_threadsafe(
                self._flush_utterance_buffer(sid), self.loop
            ),
        )

    def _clear_utterance_buffer(self, speaker_id: str):
        """Discard a speaker's buffered utterance and cancel its timer."""
        buf = self._utterance_buffers.pop(speaker_id, None)
        if buf and buf["timer"] is not None:
            buf["timer"].cancel()

    async def _flush_utterance_buffer(self, speaker_id: str):
        """Timer fired — treat the buffered text as one complete utterance."""
        buf = self._utterance_buffers.pop(speaker_id, None)
        if not buf or not buf["text"].strip():
            return

        full_text = buf["text"]
        speaker_name = buf["speaker_name"]

        # If still speaking when the buffer flushes (edge case), discard
        if self._speaking:
            return

        # Wake word is the ONLY gate — no wake word means silent discard.
        wake_result = self.wake_word_detector.detect(
            text=full_text,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
        )
        if not wake_result:
            return

        logger.info("Wake word triggered from %s: %r", speaker_name, wake_result.command)
        await self.wake_word_callback(
            meeting_id=self.meeting_id,
            result=wake_result,
        )

    # ------------------------------------------------------------------
    # Audio output
    # ------------------------------------------------------------------

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Write raw PCM frames to the virtual microphone.

        Splits audio into ~100ms chunks so that a stop command can interrupt
        playback between chunks rather than waiting for the entire clip.
        """
        if not audio_bytes:
            return

        self._speaking = True
        self._cancel_event.clear()

        # 16 kHz * 2 bytes/sample * 1 channel * 0.1 s = 3200 bytes per 100ms chunk
        chunk_size = 3200
        total = len(audio_bytes)
        offset = 0

        logger.info("send_audio: streaming %d bytes to virtual mic for meeting %s", total, self.meeting_id)
        try:
            while offset < total:
                if self._cancel_event.is_set():
                    logger.info("send_audio: cancelled at byte %d/%d", offset, total)
                    break
                chunk = audio_bytes[offset:offset + chunk_size]
                await self.loop.run_in_executor(None, self.virtual_mic.write_frames, chunk)
                offset += chunk_size
        finally:
            self._speaking = False
            self._tts_stop_time = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def join(self):
        logger.info(f"Arni Bot joining meeting {self.meeting_id}")
        self.client.set_user_name("Arni Bot")
        self.client.join(self.room_url, self.token)

    async def leave(self):
        logger.info(f"Arni Bot leaving meeting {self.meeting_id}")
        self.client.leave()
        for p_id in list(self.dg_connections.keys()):
            await self._stop_deepgram_for_participant(p_id)
        self.client.release()
