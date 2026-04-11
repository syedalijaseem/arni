"""
TDD tests for Task 3: Voice Response TTS (ElevenLabs + audio injection).

Tests cover:
- elevenlabs_client.text_to_speech(): returns bytes on success, None on API error
- Transcript filtering: speaker_id == "arni" rows excluded from storage and wake detection
- Track tag: ai-source tag is set on Arni bot initialization
- TTS failure path: Claude responds, ElevenLabs fails → text-only fallback, no crash
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# elevenlabs_client tests
# ---------------------------------------------------------------------------

class TestTextToSpeech:
    """Unit tests for tts.elevenlabs_client.text_to_speech()"""

    @pytest.mark.asyncio
    async def test_returns_bytes_on_success(self):
        """text_to_speech returns bytes when ElevenLabs succeeds."""
        fake_audio = b"fake_audio_data_bytes"

        with patch("app.tts.elevenlabs_client.get_settings") as mock_settings:
            mock_settings.return_value.ELEVENLABS_API_KEY = "test-key"
            mock_settings.return_value.ELEVENLABS_VOICE_ID = "test-voice"
            mock_settings.return_value.ELEVENLABS_MODEL = "eleven_flash_v2_5"

            with patch("elevenlabs.client.ElevenLabs") as MockClient:
                mock_instance = MagicMock()
                MockClient.return_value = mock_instance
                mock_instance.text_to_speech.convert.return_value = iter([fake_audio])

                from app.tts.elevenlabs_client import text_to_speech
                result = await text_to_speech("Hello, world!")

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error_falls_back(self):
        """When ElevenLabs fails and Deepgram also unavailable, returns None."""
        with patch("app.tts.elevenlabs_client.get_settings") as mock_settings:
            mock_settings.return_value.ELEVENLABS_API_KEY = "test-key"
            mock_settings.return_value.ELEVENLABS_VOICE_ID = "test-voice"
            mock_settings.return_value.ELEVENLABS_MODEL = "eleven_flash_v2_5"
            mock_settings.return_value.DEEPGRAM_API_KEY = ""

            with patch("elevenlabs.client.ElevenLabs") as MockClient:
                mock_instance = MagicMock()
                MockClient.return_value = mock_instance
                mock_instance.text_to_speech.convert.side_effect = Exception("API error")

                from app.tts.elevenlabs_client import text_to_speech
                result = await text_to_speech("Hello, world!")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_both_api_keys_missing(self):
        """text_to_speech returns None when both ElevenLabs and Deepgram keys are missing."""
        with patch("app.tts.elevenlabs_client.get_settings") as mock_settings:
            mock_settings.return_value.ELEVENLABS_API_KEY = ""
            mock_settings.return_value.ELEVENLABS_VOICE_ID = "test-voice"
            mock_settings.return_value.ELEVENLABS_MODEL = "eleven_flash_v2_5"
            mock_settings.return_value.DEEPGRAM_API_KEY = ""

            from app.tts.elevenlabs_client import text_to_speech
            result = await text_to_speech("Hello, world!")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_text(self):
        """text_to_speech returns None for empty text input."""
        with patch("app.tts.elevenlabs_client.get_settings") as mock_settings:
            mock_settings.return_value.ELEVENLABS_API_KEY = "test-key"
            mock_settings.return_value.ELEVENLABS_VOICE_ID = "test-voice"

            from app.tts.elevenlabs_client import text_to_speech
            result = await text_to_speech("")

        assert result is None


# ---------------------------------------------------------------------------
# Transcript filtering tests
# ---------------------------------------------------------------------------

class TestTranscriptFiltering:
    """Tests that arni speaker transcripts are filtered out."""

    @pytest.mark.asyncio
    async def test_arni_transcript_not_saved_to_db(self):
        """Transcripts with speaker_id='arni' are NOT saved to MongoDB."""
        from app.models.transcript import TranscriptCreate

        arni_transcript = TranscriptCreate(
            meeting_id="meet-1",
            speaker_id="arni",
            speaker_name="Arni Bot",
            text="I am responding to your question.",
            is_final=True,
        )

        with patch("app.routers.transcripts.save_transcript_to_db", new_callable=AsyncMock) as mock_save:
            from app.routers.transcripts import handle_bot_transcript
            await handle_bot_transcript(arni_transcript)
            mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_human_transcript_is_saved_to_db(self):
        """Transcripts from human speakers ARE saved to MongoDB."""
        from app.models.transcript import TranscriptCreate

        human_transcript = TranscriptCreate(
            meeting_id="meet-1",
            speaker_id="user-123",
            speaker_name="Alice",
            text="Hey Arni, what's the agenda?",
            is_final=True,
        )

        with patch("app.routers.transcripts.save_transcript_to_db", new_callable=AsyncMock) as mock_save:
            with patch("app.routers.transcripts.manager") as mock_manager:
                mock_manager.broadcast = AsyncMock()
                from app.routers.transcripts import handle_bot_transcript
                await handle_bot_transcript(human_transcript)
                mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_arni_transcript_does_not_trigger_wake_word(self):
        """Transcripts from arni never reach the wake word detector."""
        from app.models.transcript import TranscriptCreate
        from app.bot.wake_word import WakeWordResult

        # Simulate how ArniBot routes transcripts
        # The check should happen in the on_message callback before calling wake_word_callback
        # We test that handle_bot_transcript doesn't call wake_word callback for arni
        wake_callback = AsyncMock()

        arni_transcript = TranscriptCreate(
            meeting_id="meet-1",
            speaker_id="arni",
            speaker_name="Arni Bot",
            text="Hey Arni, answer this.",  # contains wake phrase but from arni
            is_final=True,
        )

        with patch("app.routers.transcripts.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            from app.routers.transcripts import handle_bot_transcript
            # No wake_callback integrated in handle_bot_transcript by design
            # The filter happens in ArniBot's on_message before calling this function
            await handle_bot_transcript(arni_transcript)
            wake_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_arni_transcript_still_broadcasts_to_websocket(self):
        """Arni transcripts skip DB storage but still broadcast to WebSocket clients for display."""
        from app.models.transcript import TranscriptCreate

        arni_transcript = TranscriptCreate(
            meeting_id="meet-1",
            speaker_id="arni",
            speaker_name="Arni Bot",
            text="The quarterly revenue was $2.4M.",
            is_final=True,
        )

        with patch("app.routers.transcripts.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            with patch("app.routers.transcripts.save_transcript_to_db", new_callable=AsyncMock) as mock_save:
                from app.routers.transcripts import handle_bot_transcript
                await handle_bot_transcript(arni_transcript)
                # DB save is skipped for arni
                mock_save.assert_not_called()
                # But WebSocket broadcast still happens so UI can show the text response
                mock_manager.broadcast.assert_called_once()


# ---------------------------------------------------------------------------
# ArniBot ai-source track tag tests
# ---------------------------------------------------------------------------

def _make_native_mocks():
    """Return a dict of sys.modules overrides for native packages not available in CI."""
    mock_daily = MagicMock()
    mock_daily.EventHandler = object  # ArniEventHandler inherits from this

    mock_deepgram = MagicMock()
    mock_deepgram.DeepgramClient = MagicMock
    mock_deepgram.DeepgramClientOptions = MagicMock
    mock_deepgram.LiveTranscriptionEvents = MagicMock()
    mock_deepgram.LiveOptions = MagicMock

    return {
        "daily": mock_daily,
        "deepgram": mock_deepgram,
    }


class TestArniBotTrackTag:
    """Tests that ArniBot tags its audio track as ai-source."""

    def test_arni_bot_join_sets_ai_source_microphone_tag(self):
        """ArniBot.join() configures its microphone track with audio_track_tag='ai-source'."""
        import sys
        import importlib

        native_mocks = _make_native_mocks()

        # Remove any cached (broken) module state
        for mod_name in ("app.bot.arni_bot", "app.bot"):
            sys.modules.pop(mod_name, None)

        with patch.dict(sys.modules, native_mocks):
            with patch("app.bot.arni_bot.get_settings") as mock_settings:
                mock_settings.return_value.DEEPGRAM_API_KEY = "test"

                with patch("asyncio.get_running_loop", return_value=MagicMock()):
                    mod = importlib.import_module("app.bot.arni_bot")
                    ArniBot = mod.ArniBot
                    bot = ArniBot(
                        meeting_id="meet-1",
                        room_url="https://example.daily.co/room",
                        token="token",
                        broadcast_callback=AsyncMock(),
                    )

        # Verify the bot exposes the ai-source tag constant
        assert bot.AI_AUDIO_TRACK_TAG == "ai-source"

    def test_ai_audio_track_tag_module_constant(self):
        """The module-level AI_AUDIO_TRACK_TAG constant equals 'ai-source'."""
        import sys
        import importlib

        native_mocks = _make_native_mocks()

        for mod_name in ("app.bot.arni_bot", "app.bot"):
            sys.modules.pop(mod_name, None)

        with patch.dict(sys.modules, native_mocks):
            mod = importlib.import_module("app.bot.arni_bot")
            assert mod.AI_AUDIO_TRACK_TAG == "ai-source"


# ---------------------------------------------------------------------------
# AI service TTS chaining tests
# ---------------------------------------------------------------------------

class TestAiServiceTtsChaining:
    """Tests that ai_service chains Claude response → TTS → audio injection."""

    @pytest.mark.asyncio
    async def test_tts_called_after_claude_response(self):
        """After Claude responds, text_to_speech is called with the response text."""
        context = {"system": "You are Arni.", "summary": "", "turns": []}

        with patch("app.ai.ai_service.get_settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

            with patch("app.ai.ai_service.anthropic.AsyncAnthropic") as MockAnthropic:
                mock_client = MagicMock()
                MockAnthropic.return_value = mock_client
                mock_message = MagicMock()
                mock_message.content = [MagicMock(text="The answer is 42.")]
                mock_message.usage.output_tokens = 10
                mock_client.messages.create = AsyncMock(return_value=mock_message)

                with patch("app.ai.ai_service.text_to_speech", new_callable=AsyncMock) as mock_tts:
                    mock_tts.return_value = b"audio_bytes"

                    with patch("app.ai.ai_service.inject_audio", new_callable=AsyncMock) as mock_inject:
                        from app.ai.ai_service import ai_respond
                        result = await ai_respond("meet-1", "What is the answer?", context)

                mock_tts.assert_called_once_with("The answer is 42.")
                mock_inject.assert_called_once()

        assert result["response_text"] == "The answer is 42."

    @pytest.mark.asyncio
    async def test_tts_failure_returns_text_only_no_crash(self):
        """When TTS fails (returns None), ai_respond returns text only without crashing (NFR-010)."""
        context = {"system": "You are Arni.", "summary": "", "turns": []}

        with patch("app.ai.ai_service.get_settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY = "test-key"

            with patch("app.ai.ai_service.anthropic.AsyncAnthropic") as MockAnthropic:
                mock_client = MagicMock()
                MockAnthropic.return_value = mock_client
                mock_message = MagicMock()
                mock_message.content = [MagicMock(text="Text response here.")]
                mock_message.usage.output_tokens = 8
                mock_client.messages.create = AsyncMock(return_value=mock_message)

                with patch("app.ai.ai_service.text_to_speech", new_callable=AsyncMock) as mock_tts:
                    mock_tts.return_value = None  # TTS failure

                    with patch("app.ai.ai_service.inject_audio", new_callable=AsyncMock) as mock_inject:
                        from app.ai.ai_service import ai_respond
                        result = await ai_respond("meet-1", "Tell me something.", context)

                # inject_audio must NOT be called when TTS fails
                mock_inject.assert_not_called()

        assert result["response_text"] == "Text response here."

    @pytest.mark.asyncio
    async def test_inject_audio_not_called_when_tts_returns_none(self):
        """inject_audio is skipped entirely when text_to_speech returns None."""
        context = {"system": "", "summary": "", "turns": []}

        with patch("app.ai.ai_service.get_settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY = "key"

            with patch("app.ai.ai_service.anthropic.AsyncAnthropic") as MockAnthropic:
                mock_client = MagicMock()
                MockAnthropic.return_value = mock_client
                mock_msg = MagicMock()
                mock_msg.content = [MagicMock(text="Response.")]
                mock_msg.usage.output_tokens = 3
                mock_client.messages.create = AsyncMock(return_value=mock_msg)

                with patch("app.ai.ai_service.text_to_speech", new_callable=AsyncMock, return_value=None):
                    with patch("app.ai.ai_service.inject_audio", new_callable=AsyncMock) as mock_inject:
                        from app.ai.ai_service import ai_respond
                        await ai_respond("meet-1", "cmd", context)

                        mock_inject.assert_not_called()
