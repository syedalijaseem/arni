"""
ArniBot — ElevenLabs Conversational AI agent connected to Daily.co.

Architecture:
  Daily.co participant audio → DailyAudioInterface → ElevenLabs Conversation
  ElevenLabs agent speech    → DailyAudioInterface → Daily.co virtual mic

ElevenLabs handles STT, LLM reasoning, and TTS internally.
This bot just bridges the audio and broadcasts transcripts.
"""

import asyncio
import logging
from typing import Dict, Any

import daily
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation

from app.config import get_settings
from app.models.transcript import TranscriptCreate
from app.bot.daily_audio_interface import DailyAudioInterface
from app.bot.agent_setup import ensure_agent

logger = logging.getLogger(__name__)

AI_AUDIO_TRACK_TAG = "ai-source"


class ArniEventHandler(daily.EventHandler):
    def __init__(self, bot: "ArniBot"):
        self.bot = bot

    def on_participant_joined(self, participant):
        sid = participant["id"]
        name = participant["info"].get("userName", "")
        uid = participant["info"].get("userId") or participant.get("user_id", name)
        self.bot.participants[sid] = {"user_id": uid, "name": name or uid}
        logger.info("Participant joined: %s (%s)", sid, name)

        # Subscribe to this participant's audio and forward to ElevenLabs
        def on_audio(participant_session_id, audio_data, audio_source=None):
            if audio_data.audio_frames and self.bot.audio_interface:
                self.bot.audio_interface.feed_audio(audio_data.audio_frames)

        self.bot.client.set_audio_renderer(sid, on_audio)

    def on_participant_left(self, participant, reason):
        sid = participant["id"]
        self.bot.participants.pop(sid, None)
        self.bot.client.set_audio_renderer(sid, None)
        logger.info("Participant left: %s", sid)


class ArniBot:
    def __init__(self, meeting_id: str, room_url: str, token: str,
                 broadcast_callback, wake_word_callback=None):
        self.meeting_id = meeting_id
        self.room_url = room_url
        self.token = token
        self.broadcast_callback = broadcast_callback
        # wake_word_callback kept for API compatibility but unused —
        # ElevenLabs agent handles wake detection internally
        self.wake_word_callback = wake_word_callback

        self.settings = get_settings()
        self.event_handler = ArniEventHandler(self)
        self.client = daily.CallClient(event_handler=self.event_handler)

        # Virtual microphone for agent speech output
        self.virtual_mic = daily.Daily.create_microphone_device(
            "arni-mic", sample_rate=16000, channels=1, non_blocking=True,
        )
        self.client.update_inputs({
            "camera": False,
            "microphone": {"isEnabled": True, "settings": {"deviceId": "arni-mic"}},
        })

        self.participants: Dict[str, dict] = {}
        self.AI_AUDIO_TRACK_TAG = AI_AUDIO_TRACK_TAG

        # ElevenLabs Conversational AI
        self.audio_interface = DailyAudioInterface(self.virtual_mic)
        self.conversation: Conversation | None = None

        self.loop = asyncio.get_running_loop()

    async def join(self):
        logger.info("Arni Bot joining meeting %s", self.meeting_id)
        self.client.set_user_name("Arni Bot")
        self.client.join(self.room_url, self.token)

        # Start ElevenLabs Conversation in a background thread
        agent_id = ensure_agent()
        el_client = ElevenLabs(api_key=self.settings.ELEVENLABS_API_KEY)

        self.conversation = Conversation(
            client=el_client,
            agent_id=agent_id,
            requires_auth=True,
            audio_interface=self.audio_interface,
            callback_agent_response=self._on_agent_response,
            callback_user_transcript=self._on_user_transcript,
        )
        self.conversation.start_session()
        logger.info("ElevenLabs conversation started for meeting %s", self.meeting_id)

    def _on_agent_response(self, text: str):
        """Called by ElevenLabs when the agent produces a text response."""
        asyncio.run_coroutine_threadsafe(
            self.broadcast_callback(TranscriptCreate(
                meeting_id=self.meeting_id,
                speaker_id="arni",
                speaker_name="Arni Bot",
                text=text,
                is_final=True,
            )),
            self.loop,
        )

    def _on_user_transcript(self, text: str):
        """Called by ElevenLabs when user speech is transcribed."""
        asyncio.run_coroutine_threadsafe(
            self.broadcast_callback(TranscriptCreate(
                meeting_id=self.meeting_id,
                speaker_id="user",
                speaker_name="Participant",
                text=text,
                is_final=True,
            )),
            self.loop,
        )

    async def leave(self):
        logger.info("Arni Bot leaving meeting %s", self.meeting_id)
        if self.conversation:
            self.conversation.end_session()
            self.conversation.wait_for_session_end()
            self.conversation = None
        self.client.leave()
        self.client.release()
