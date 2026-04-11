"""
Tests for context_manager.build_context()

RED phase: tests are written first and will fail until implementation exists.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_db():
    """Return a mock MongoDB database."""
    db = MagicMock()
    db.meeting_summaries = MagicMock()
    db.transcripts = MagicMock()
    return db


@pytest.fixture
def sample_transcripts():
    return [
        {
            "meeting_id": "meet_001",
            "speaker_id": "user_1",
            "speaker_name": "Alice",
            "text": "Let us discuss the budget.",
            "is_final": True,
            "timestamp": datetime(2026, 4, 11, 10, 0, i),
        }
        for i in range(25)
    ]


@pytest.fixture
def sample_summary():
    return {
        "meeting_id": "meet_001",
        "summary_text": "The team is discussing Q2 budget allocation.",
        "updated_at": datetime(2026, 4, 11, 10, 0, 0),
    }


class TestBuildContext:
    @pytest.mark.asyncio
    async def test_returns_dict_with_required_keys(self, mock_db, sample_transcripts, sample_summary):
        """build_context must return a dict with system, summary, and turns keys."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=sample_transcripts[:5])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            result = await build_context("meet_001")

        assert "system" in result
        assert "summary" in result
        assert "turns" in result

    @pytest.mark.asyncio
    async def test_turns_count_respects_window_size(self, mock_db, sample_transcripts, sample_summary):
        """build_context must return at most AI_CONTEXT_WINDOW turns."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=sample_transcripts[:20])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            with patch("app.ai.context_manager.get_settings") as mock_settings:
                mock_settings.return_value.AI_CONTEXT_WINDOW = 20
                result = await build_context("meet_001", window_size=20)

        assert len(result["turns"]) <= 20

    @pytest.mark.asyncio
    async def test_summary_populated_from_db(self, mock_db, sample_transcripts, sample_summary):
        """build_context must include rolling summary from MongoDB."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=sample_transcripts[:5])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            result = await build_context("meet_001")

        assert result["summary"] == sample_summary["summary_text"]

    @pytest.mark.asyncio
    async def test_empty_summary_when_no_summary_exists(self, mock_db, sample_transcripts):
        """build_context returns empty summary string when no summary in DB."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=sample_transcripts[:3])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            result = await build_context("meet_001")

        assert result["summary"] == ""

    @pytest.mark.asyncio
    async def test_turns_contain_speaker_and_text(self, mock_db, sample_transcripts, sample_summary):
        """Each turn dict must contain speaker_name and text."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=sample_transcripts[:3])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            result = await build_context("meet_001")

        for turn in result["turns"]:
            assert "speaker_name" in turn
            assert "text" in turn

    @pytest.mark.asyncio
    async def test_system_prompt_is_non_empty_string(self, mock_db, sample_transcripts, sample_summary):
        """System prompt must be a non-empty string describing Arni's persona."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[])
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            result = await build_context("meet_001")

        assert isinstance(result["system"], str)
        assert len(result["system"]) > 20

    @pytest.mark.asyncio
    async def test_window_size_default_is_20(self, mock_db, sample_transcripts, sample_summary):
        """Default window size must be 20 turns unless overridden."""
        from app.ai.context_manager import build_context

        mock_db.meeting_summaries.find_one = AsyncMock(return_value=sample_summary)
        cursor = AsyncMock()
        cursor.sort = MagicMock(return_value=cursor)
        # Return 25 transcripts — only 20 should make it in
        cursor.to_list = AsyncMock(return_value=sample_transcripts)
        mock_db.transcripts.find = MagicMock(return_value=cursor)

        with patch("app.ai.context_manager.get_database", return_value=mock_db):
            with patch("app.ai.context_manager.get_settings") as mock_settings:
                mock_settings.return_value.AI_CONTEXT_WINDOW = 20
                result = await build_context("meet_001")

        assert len(result["turns"]) <= 20
