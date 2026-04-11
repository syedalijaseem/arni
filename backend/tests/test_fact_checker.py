"""
TDD tests for Task 7: Proactive Fact-Checking Pipeline.

Tests cover:
- No documents → check returns immediately, no embedding call
- Cooldown active → check skipped
- Confidence below threshold → no correction enqueued
- Confidence above threshold → correction enqueued + fact.checked event
- Cooldown resets correctly after interval
- enqueue_correction() tags response_type as "fact_check"
- POST /ai/fact-check endpoint returns correct response shape
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# fact_checker.check() unit tests
# ---------------------------------------------------------------------------

class TestFactCheckerCheck:

    @pytest.mark.asyncio
    async def test_no_documents_skips_immediately(self):
        """check() returns None without calling embedder when no docs exist."""
        with patch("app.ai.fact_checker.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            mock_db.document_chunks.find.return_value = mock_cursor

            with patch("app.ai.fact_checker.get_embedding", new_callable=AsyncMock) as mock_embed:
                from app.ai.fact_checker import FactChecker
                fc = FactChecker()
                result = await fc.check("meet-1", "user-1", "churn was 12%")

        assert result is None
        mock_embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_cooldown_active_skips(self):
        """check() skips vector search if called within cooldown window."""
        with patch("app.ai.fact_checker.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            # Documents exist
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[{"_id": "chunk-1"}])
            mock_db.document_chunks.find.return_value = mock_cursor

            with patch("app.ai.fact_checker.get_embedding", new_callable=AsyncMock) as mock_embed:
                from app.ai.fact_checker import FactChecker
                fc = FactChecker(cooldown_seconds=30)

                # Simulate prior trigger within cooldown
                import time
                fc._last_triggered["meet-1"] = time.monotonic()  # just triggered

                result = await fc.check("meet-1", "user-1", "churn was 12%")

        assert result is None
        mock_embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_below_threshold_no_correction(self):
        """check() does not enqueue correction when confidence < threshold."""
        with patch("app.ai.fact_checker.get_database") as mock_db_fn:
            with patch("app.ai.fact_checker.get_embedding", new_callable=AsyncMock, return_value=[0.1] * 10):
                with patch("app.ai.fact_checker.vector_search", new_callable=AsyncMock) as mock_vs:
                    with patch("app.ai.fact_checker.claude_contradiction_check", new_callable=AsyncMock) as mock_check:
                        mock_db = MagicMock()
                        mock_db_fn.return_value = mock_db

                        mock_cursor = MagicMock()
                        mock_cursor.to_list = AsyncMock(return_value=[{"_id": "chunk-1"}])
                        mock_db.document_chunks.find.return_value = mock_cursor

                        mock_vs.return_value = [{"text": "churn = 7%", "document_name": "Q4 Report"}]
                        mock_check.return_value = {
                            "contradicts": True,
                            "confidence": 0.40,  # Below threshold
                            "correction": "churn was 7%",
                            "excerpt": "churn = 7%",
                        }

                        with patch("app.ai.fact_checker.get_or_create_queue") as mock_queue_fn:
                            mock_queue = MagicMock()
                            mock_queue_fn.return_value = mock_queue

                            from app.ai.fact_checker import FactChecker
                            fc = FactChecker(confidence_threshold=0.85)
                            result = await fc.check("meet-1", "user-1", "churn was 12%")

        assert result is None
        mock_queue.enqueue_correction.assert_not_called()

    @pytest.mark.asyncio
    async def test_above_threshold_enqueues_correction(self):
        """check() enqueues correction when confidence >= threshold."""
        with patch("app.ai.fact_checker.get_database") as mock_db_fn:
            with patch("app.ai.fact_checker.get_embedding", new_callable=AsyncMock, return_value=[0.1] * 10):
                with patch("app.ai.fact_checker.vector_search", new_callable=AsyncMock) as mock_vs:
                    with patch("app.ai.fact_checker.claude_contradiction_check", new_callable=AsyncMock) as mock_check:
                        mock_db = MagicMock()
                        mock_db_fn.return_value = mock_db

                        mock_cursor = MagicMock()
                        mock_cursor.to_list = AsyncMock(return_value=[{"_id": "chunk-1"}])
                        mock_db.document_chunks.find.return_value = mock_cursor

                        mock_vs.return_value = [{"text": "churn = 7%", "document_name": "Q4 Report"}]
                        mock_check.return_value = {
                            "contradicts": True,
                            "confidence": 0.92,  # Above threshold
                            "correction": "According to Q4 Report, churn was 7%.",
                            "excerpt": "churn = 7%",
                        }

                        with patch("app.ai.fact_checker.get_or_create_queue") as mock_queue_fn:
                            mock_queue = MagicMock()
                            mock_queue.enqueue_correction = AsyncMock()
                            mock_queue_fn.return_value = mock_queue

                            from app.ai.fact_checker import FactChecker
                            fc = FactChecker(confidence_threshold=0.85)
                            result = await fc.check("meet-1", "user-1", "churn was 12%")

        mock_queue.enqueue_correction.assert_called_once()
        call_kwargs = mock_queue.enqueue_correction.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_cooldown_resets_after_interval(self):
        """check() proceeds after cooldown has elapsed."""
        with patch("app.ai.fact_checker.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[{"_id": "chunk-1"}])
            mock_db.document_chunks.find.return_value = mock_cursor

            with patch("app.ai.fact_checker.get_embedding", new_callable=AsyncMock, return_value=[0.1] * 10) as mock_embed:
                with patch("app.ai.fact_checker.vector_search", new_callable=AsyncMock, return_value=[]):
                    from app.ai.fact_checker import FactChecker
                    import time
                    fc = FactChecker(cooldown_seconds=0)  # 0s cooldown for test
                    # Set last trigger to past (should not block)
                    fc._last_triggered["meet-1"] = time.monotonic() - 100

                    await fc.check("meet-1", "user-1", "some claim")

        mock_embed.assert_called_once()


# ---------------------------------------------------------------------------
# MeetingQueue.enqueue_correction() tests
# ---------------------------------------------------------------------------

class TestEnqueueCorrection:

    @pytest.mark.asyncio
    async def test_enqueue_correction_tagged_as_fact_check(self):
        """enqueue_correction adds item with response_type='fact_check'."""
        from app.ai.response_queue import MeetingQueue
        queue = MeetingQueue("meet-1")
        await queue.enqueue_correction(
            meeting_id="meet-1",
            correction_text="Churn was 7%, not 12%.",
            source_document="Q4 Report",
            source_excerpt="churn = 7%",
        )

        assert not queue._queue.empty()
        item = await queue._queue.get()
        assert item.get("response_type") == "fact_check"
        assert item.get("correction_text") == "Churn was 7%, not 12%."


# ---------------------------------------------------------------------------
# POST /ai/fact-check endpoint tests
# ---------------------------------------------------------------------------

class TestFactCheckEndpoint:

    @pytest.mark.asyncio
    async def test_returns_contradicts_true_when_found(self):
        """POST /ai/fact-check returns contradicts=True and correction when above threshold."""
        with patch("app.routers.ai.fact_checker") as mock_fc:
            mock_fc.check = AsyncMock(return_value={
                "contradicts": True,
                "confidence": 0.92,
                "correction_text": "Churn was 7%, not 12%.",
                "source_document": "Q4 Report",
                "source_excerpt": "churn = 7%",
            })

            from app.routers.ai import AIFactCheckRequest, fact_check
            req = AIFactCheckRequest(meeting_id="meet-1", transcript_text="churn was 12%", speaker_id="u1")
            result = await fact_check(req)

        assert result.contradicts is True
        assert result.correction_text == "Churn was 7%, not 12%."

    @pytest.mark.asyncio
    async def test_returns_contradicts_false_when_not_found(self):
        """POST /ai/fact-check returns contradicts=False when no contradiction found."""
        with patch("app.routers.ai.fact_checker") as mock_fc:
            mock_fc.check = AsyncMock(return_value=None)

            from app.routers.ai import AIFactCheckRequest, fact_check
            req = AIFactCheckRequest(meeting_id="meet-1", transcript_text="all good data", speaker_id="u1")
            result = await fact_check(req)

        assert result.contradicts is False
        assert result.correction_text is None
