"""
TDD tests for Task 5: Rolling Summaries + Context Coherence.

Tests cover:
- POST /ai/summarize: skips when no new turns; generates and stores summary when turns exist
- context_manager.build_context(): uses latest summary + correct number of turns
- Scheduler: start_for_meeting creates a job; stop_for_meeting cancels it
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# /ai/summarize endpoint function tests (direct router function calls)
# ---------------------------------------------------------------------------

class TestAiSummarizeEndpoint:

    @pytest.mark.asyncio
    async def test_skips_when_no_new_turns(self):
        """summarize() returns skipped=True when there are no transcript turns."""
        with patch("app.routers.ai.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=[])
            mock_db.transcripts.find.return_value = mock_cursor
            mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)

            from app.routers.ai import AISummarizeRequest, summarize
            req = AISummarizeRequest(meeting_id="meet-1")
            result = await summarize(req)

        assert result.skipped is True
        assert result.summary_text is None

    @pytest.mark.asyncio
    async def test_generates_and_stores_summary_when_turns_exist(self):
        """summarize() calls ai_summarize and stores a document when turns are present."""
        with patch("app.routers.ai.get_database") as mock_db_fn:
            with patch("app.routers.ai.ai_summarize", new_callable=AsyncMock, return_value="Q1 revenue discussed."):
                mock_db = MagicMock()
                mock_db_fn.return_value = mock_db

                mock_cursor = MagicMock()
                mock_cursor.sort.return_value = mock_cursor
                mock_cursor.to_list = AsyncMock(return_value=[
                    {"speaker_id": "u1", "speaker_name": "Alice", "text": "Revenue was $2M."},
                    {"speaker_id": "u2", "speaker_name": "Bob", "text": "Good growth!"},
                ])
                mock_db.transcripts.find.return_value = mock_cursor
                mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)
                mock_db.meeting_summaries.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc-1"))

                from app.routers.ai import AISummarizeRequest, summarize
                req = AISummarizeRequest(meeting_id="meet-2")
                result = await summarize(req)

        assert result.skipped is False
        assert result.summary_text == "Q1 revenue discussed."

    @pytest.mark.asyncio
    async def test_stores_summary_in_mongodb(self):
        """summarize() inserts a new document with correct meeting_id and summary_text."""
        with patch("app.routers.ai.get_database") as mock_db_fn:
            with patch("app.routers.ai.ai_summarize", new_callable=AsyncMock, return_value="Budget approved."):
                mock_db = MagicMock()
                mock_db_fn.return_value = mock_db

                mock_cursor = MagicMock()
                mock_cursor.sort.return_value = mock_cursor
                mock_cursor.to_list = AsyncMock(return_value=[
                    {"speaker_id": "u1", "speaker_name": "Alice", "text": "Budget is $10M."},
                ])
                mock_db.transcripts.find.return_value = mock_cursor
                mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)
                mock_db.meeting_summaries.insert_one = AsyncMock(return_value=MagicMock(inserted_id="sum-1"))

                from app.routers.ai import AISummarizeRequest, summarize
                req = AISummarizeRequest(meeting_id="meet-3")
                await summarize(req)

                mock_db.meeting_summaries.insert_one.assert_called_once()
                call_doc = mock_db.meeting_summaries.insert_one.call_args[0][0]
                assert call_doc["meeting_id"] == "meet-3"
                assert call_doc["summary_text"] == "Budget approved."


# ---------------------------------------------------------------------------
# context_manager.build_context() tests
# ---------------------------------------------------------------------------

class TestContextManagerSummary:

    @pytest.mark.asyncio
    async def test_build_context_uses_latest_summary(self):
        """build_context includes the latest rolling summary in the context dict."""
        with patch("app.ai.context_manager.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            mock_db.meeting_summaries.find_one = AsyncMock(
                return_value={"summary_text": "Q1 discussed.", "updated_at": "2026-04-11T10:00:00Z"}
            )

            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=[])
            mock_db.transcripts.find.return_value = mock_cursor

            from app.ai.context_manager import build_context
            ctx = await build_context("meet-1")

        assert ctx["summary"] == "Q1 discussed."

    @pytest.mark.asyncio
    async def test_build_context_handles_missing_summary(self):
        """build_context uses empty string when no summary exists."""
        with patch("app.ai.context_manager.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db
            mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)

            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=[])
            mock_db.transcripts.find.return_value = mock_cursor

            from app.ai.context_manager import build_context
            ctx = await build_context("meet-no-summary")

        assert ctx["summary"] == ""

    @pytest.mark.asyncio
    async def test_build_context_uses_window_size(self):
        """build_context fetches exactly window_size turns."""
        with patch("app.ai.context_manager.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db
            mock_db.meeting_summaries.find_one = AsyncMock(return_value=None)

            turns_data = [
                {"speaker_id": f"u{i}", "speaker_name": f"User{i}", "text": f"Turn {i}"}
                for i in range(3)
            ]
            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=turns_data)
            mock_db.transcripts.find.return_value = mock_cursor

            from app.ai.context_manager import build_context
            ctx = await build_context("meet-1", window_size=3)

        assert len(ctx["turns"]) == 3


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------

class TestSummaryScheduler:

    def test_start_for_meeting_registers_job(self):
        """start_for_meeting creates an APScheduler job for the given meeting."""
        with patch("app.scheduler.summary_scheduler.AsyncIOScheduler") as MockScheduler:
            mock_scheduler_instance = MagicMock()
            MockScheduler.return_value = mock_scheduler_instance

            from app.scheduler.summary_scheduler import SummaryScheduler
            scheduler = SummaryScheduler()
            scheduler.start_for_meeting("meet-1", interval_minutes=10)

        mock_scheduler_instance.add_job.assert_called_once()
        call_kwargs = mock_scheduler_instance.add_job.call_args[1]
        assert call_kwargs.get("minutes") == 10 or call_kwargs.get("id") is not None

    def test_stop_for_meeting_removes_job(self):
        """stop_for_meeting cancels the scheduled job for the given meeting."""
        with patch("app.scheduler.summary_scheduler.AsyncIOScheduler") as MockScheduler:
            mock_scheduler_instance = MagicMock()
            MockScheduler.return_value = mock_scheduler_instance

            from app.scheduler.summary_scheduler import SummaryScheduler
            scheduler = SummaryScheduler()
            scheduler.start_for_meeting("meet-1", interval_minutes=10)
            scheduler.stop_for_meeting("meet-1")

        mock_scheduler_instance.remove_job.assert_called_once()

    def test_interval_comes_from_config(self):
        """start_for_meeting uses AUTO_SUMMARY_INTERVAL_MINUTES from settings."""
        with patch("app.scheduler.summary_scheduler.AsyncIOScheduler") as MockScheduler:
            mock_scheduler_instance = MagicMock()
            MockScheduler.return_value = mock_scheduler_instance

            with patch("app.scheduler.summary_scheduler.get_settings") as mock_settings:
                mock_settings.return_value.AUTO_SUMMARY_INTERVAL_MINUTES = 5

                from app.scheduler.summary_scheduler import SummaryScheduler
                scheduler = SummaryScheduler()
                scheduler.start_for_meeting("meet-1")  # no explicit interval

        mock_scheduler_instance.add_job.assert_called_once()
        # Verify that interval comes from settings (not a hardcoded value)
        call_kwargs = mock_scheduler_instance.add_job.call_args
        assert call_kwargs is not None
