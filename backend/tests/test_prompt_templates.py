"""
TDD tests for Task 8: AI Teammate Reasoning — prompt_templates module.

Tests cover:
- STANDARD_PROMPT renders with all variables
- REASONING_PROMPT renders with all variables and contains mandatory directives
- Both templates accept document_context variable
- ai_respond routes to correct template based on reasoning_detector
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPromptTemplates:

    def test_standard_prompt_renders(self):
        """STANDARD_PROMPT renders without missing placeholders."""
        from app.ai.prompt_templates import STANDARD_PROMPT
        rendered = STANDARD_PROMPT.format(
            summary="Meeting summary here.",
            recent_turns="Speaker A: Hello\nSpeaker B: Hi",
            document_context="Doc context here.",
            command="Summarize what we discussed.",
        )
        assert "Meeting summary here." in rendered
        assert "Summarize what we discussed." in rendered

    def test_reasoning_prompt_renders(self):
        """REASONING_PROMPT renders without missing placeholders."""
        from app.ai.prompt_templates import REASONING_PROMPT
        rendered = REASONING_PROMPT.format(
            summary="Meeting summary.",
            recent_turns="A: Yes\nB: No",
            document_context="Q4 report excerpt.",
            command="Which option is better?",
        )
        assert "Meeting summary." in rendered
        assert "Which option is better?" in rendered

    def test_reasoning_prompt_requires_explicit_recommendation(self):
        """REASONING_PROMPT body instructs Claude to give an explicit recommendation."""
        from app.ai.prompt_templates import REASONING_PROMPT
        # Confirm the template body (before format substitution) contains directive
        assert "recommendation" in REASONING_PROMPT.lower() or "recommend" in REASONING_PROMPT.lower()

    def test_reasoning_prompt_forbids_neutral_answer(self):
        """REASONING_PROMPT instructs Claude not to give a neutral answer."""
        from app.ai.prompt_templates import REASONING_PROMPT
        # The template must have language that prevents hedging
        assert "position" in REASONING_PROMPT.lower() or "neutral" in REASONING_PROMPT.lower()

    def test_standard_prompt_has_document_context_placeholder(self):
        """STANDARD_PROMPT must accept document_context."""
        from app.ai.prompt_templates import STANDARD_PROMPT
        assert "{document_context}" in STANDARD_PROMPT

    def test_reasoning_prompt_has_all_placeholders(self):
        """REASONING_PROMPT must contain all four template variables."""
        from app.ai.prompt_templates import REASONING_PROMPT
        for var in ["{summary}", "{recent_turns}", "{document_context}", "{command}"]:
            assert var in REASONING_PROMPT


class TestAiRespondRouting:
    """Integration-style tests: ai_respond routes to correct prompt template."""

    @pytest.mark.asyncio
    async def test_reasoning_command_uses_reasoning_prompt(self):
        """ai_respond with comparison command calls build_reasoning_context."""
        reasoning_ctx = {
            "summary": "",
            "turns": [],
            "recent_turns": [],
            "document_context": "some doc",
            "system": "",
        }
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="I recommend Option B.")]
        mock_message.usage = MagicMock(output_tokens=20)

        with patch("app.ai.ai_service.build_reasoning_context", new_callable=AsyncMock, return_value=reasoning_ctx) as mock_rsn_ctx:
            with patch("app.ai.ai_service.text_to_speech", new_callable=AsyncMock, return_value=None):
                with patch("anthropic.AsyncAnthropic") as mock_anthropic_cls:
                    mock_client_inst = MagicMock()
                    mock_client_inst.messages.create = AsyncMock(return_value=mock_message)
                    mock_anthropic_cls.return_value = mock_client_inst

                    # Patch settings to provide API key
                    with patch("app.ai.ai_service.get_settings") as mock_settings:
                        mock_settings.return_value = MagicMock(
                            ANTHROPIC_API_KEY="test-key",
                            ELEVENLABS_API_KEY=None,
                        )

                        from app.ai.ai_service import ai_respond
                        result = await ai_respond(
                            meeting_id="meet-1",
                            command="which option is better for the backend?",
                            context={},
                        )

        mock_rsn_ctx.assert_called_once()

    @pytest.mark.asyncio
    async def test_standard_command_does_not_use_reasoning_context(self):
        """ai_respond with non-comparison command does not call build_reasoning_context."""
        standard_ctx = {
            "summary": "",
            "turns": [],
            "recent_turns": [],
            "document_context": "",
            "system": "",
        }
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="Here is the summary.")]
        mock_message.usage = MagicMock(output_tokens=10)

        with patch("app.ai.ai_service.build_reasoning_context", new_callable=AsyncMock) as mock_rsn_ctx:
            with patch("app.ai.ai_service.text_to_speech", new_callable=AsyncMock, return_value=None):
                with patch("anthropic.AsyncAnthropic") as mock_anthropic_cls:
                    mock_client_inst = MagicMock()
                    mock_client_inst.messages.create = AsyncMock(return_value=mock_message)
                    mock_anthropic_cls.return_value = mock_client_inst

                    with patch("app.ai.ai_service.get_settings") as mock_settings:
                        mock_settings.return_value = MagicMock(
                            ANTHROPIC_API_KEY="test-key",
                            ELEVENLABS_API_KEY=None,
                        )

                        from app.ai.ai_service import ai_respond
                        result = await ai_respond(
                            meeting_id="meet-1",
                            command="summarize the discussion",
                            context=standard_ctx,
                        )

        mock_rsn_ctx.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_reasoning_context_includes_document_context(self):
        """build_reasoning_context returns a dict with document_context key."""
        with patch("app.ai.context_manager.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            # Transcripts cursor
            transcript_cursor = MagicMock()
            transcript_cursor.sort.return_value = transcript_cursor
            transcript_cursor.to_list = AsyncMock(return_value=[
                {"speaker_id": "u1", "speaker_name": "Alice", "text": "Sales are up 20%"}
            ])

            # Summaries cursor
            mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)

            # Document chunks cursor (for RAG)
            rag_cursor = MagicMock()
            rag_cursor.to_list = AsyncMock(return_value=[
                {"text": "Sales grew 20% YoY", "document_name": "Q4 Report"}
            ])

            mock_db.transcripts.find.return_value = transcript_cursor
            mock_db.document_chunks.find.return_value = rag_cursor

            from app.ai.context_manager import build_reasoning_context
            ctx = await build_reasoning_context("meet-1", "what are the sales figures?")

        assert "document_context" in ctx
        assert "recent_turns" in ctx
        assert "summary" in ctx

    @pytest.mark.asyncio
    async def test_build_reasoning_context_empty_when_no_documents(self):
        """build_reasoning_context returns empty document_context when no chunks exist."""
        with patch("app.ai.context_manager.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            transcript_cursor = MagicMock()
            transcript_cursor.sort.return_value = transcript_cursor
            transcript_cursor.to_list = AsyncMock(return_value=[])

            mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)

            rag_cursor = MagicMock()
            rag_cursor.to_list = AsyncMock(return_value=[])
            mock_db.transcripts.find.return_value = transcript_cursor
            mock_db.document_chunks.find.return_value = rag_cursor

            from app.ai.context_manager import build_reasoning_context
            ctx = await build_reasoning_context("meet-1", "which is better?")

        assert ctx["document_context"] == "" or ctx["document_context"] is None
