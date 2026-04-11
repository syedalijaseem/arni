import asyncio
import logging
import time
from typing import Dict, Any

import daily
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from app.config import get_settings
from app.models.transcript import TranscriptCreate
from app.bot.wake_word import WakeWordDetector

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
        # 16-bit PCM at 16 kHz mono — matches the ElevenLabs pcm_16000 output.
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

        # Tag for Arni's audio track — used to prevent STT feedback loop
        self.AI_AUDIO_TRACK_TAG = AI_AUDIO_TRACK_TAG

        self.wake_word_detector = WakeWordDetector()

        # Conversation window: after Arni responds, the same speaker can
        # send follow-up commands without repeating the wake word.
        self._conv_window_seconds: float = float(self.settings.CONVERSATION_WINDOW_SECONDS)
        self._last_response_time: float = 0.0
        self._last_speaker_id: str = ""

        self.loop = asyncio.get_running_loop()

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
                logger.info(f"Deepgram transcript for {participant_id}: is_final={is_final} text={transcript!r}")

                # Retrieve speaker info (self here is ArniBot via closure)
                speaker_id = self.participant_id_to_user.get(participant_id, participant_id)
                speaker_name = self.participant_id_to_name.get(participant_id, speaker_id)

                payload = TranscriptCreate(
                    meeting_id=self.meeting_id,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                    text=transcript,
                    is_final=is_final
                )

                # Broadcast the transcript payload through the WebSocket manager
                await self.broadcast_callback(payload)

                # Never process Arni's own speech through wake detection (FR-034, FR-035)
                if speaker_id == "arni":
                    return

                if not is_final or not self.wake_word_callback:
                    return

                # 1. Try explicit wake word detection
                wake_result = self.wake_word_detector.detect(
                    text=transcript,
                    speaker_id=speaker_id,
                    speaker_name=speaker_name,
                )

                # 2. If no wake word, check conversation window for follow-ups
                if wake_result is None:
                    now = time.time()
                    in_window = (
                        self._last_speaker_id == speaker_id
                        and (now - self._last_response_time) < self._conv_window_seconds
                    )
                    if in_window:
                        from app.bot.wake_word import WakeWordResult
                        wake_result = WakeWordResult(
                            speaker_id=speaker_id,
                            speaker_name=speaker_name,
                            command=transcript,
                            timestamp=now,
                        )
                        logger.info(
                            "Conversation window follow-up from %s: %r",
                            speaker_name, transcript,
                        )

                if wake_result:
                    self._last_response_time = time.time()
                    self._last_speaker_id = speaker_id
                    await self.wake_word_callback(
                        meeting_id=self.meeting_id,
                        result=wake_result,
                    )

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
            )

            if await dg_connection.start(options) is False:
                logger.error("Failed to connect to Deepgram")
                return

            self.dg_connections[participant_id] = dg_connection

            # Callback for Daily.co audio frames
            # daily-python calls this with 3 args: (participant_id, audio_data, audio_source)
            def on_audio_data(participant_session_id, audio_data, audio_source=None):
                # audio_data.audio_frames is bytes (PCM 16-bit 16kHz mono)
                if dg_connection and audio_data.audio_frames:
                    asyncio.run_coroutine_threadsafe(
                        dg_connection.send(audio_data.audio_frames),
                        self.loop
                    )

            # Subscribe to the participant's audio
            self.client.set_audio_renderer(participant_id, on_audio_data)
            
        except Exception as e:
            logger.error(f"Error setting up Deepgram for {participant_id}: {e}")

    async def _stop_deepgram_for_participant(self, participant_id: str):
        self.client.set_audio_renderer(participant_id, None)
        dg_connection = self.dg_connections.get(participant_id)
        if dg_connection:
            await dg_connection.finish()
            del self.dg_connections[participant_id]

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Write raw PCM frames to the virtual microphone so other participants hear Arni."""
        if not audio_bytes:
            return
        logger.info("send_audio: writing %d bytes to virtual mic for meeting %s", len(audio_bytes), self.meeting_id)
        await self.loop.run_in_executor(None, self.virtual_mic.write_frames, audio_bytes)

    async def join(self):
        logger.info(f"Arni Bot joining meeting {self.meeting_id}")
        self.client.set_user_name("Arni Bot")
        self.client.join(self.room_url, self.token)

    async def leave(self):
        logger.info(f"Arni Bot leaving meeting {self.meeting_id}")
        self.client.leave()
        # Clean up all Deepgram connections
        for p_id in list(self.dg_connections.keys()):
            await self._stop_deepgram_for_participant(p_id)
        self.client.release()
