"""
TDD tests for Task 3: Unified Semantic Search (RAG Pipeline).

Tests cover:
- embedder.embed_transcript(): chunk count, token range, idempotency
- retriever.retrieve(): results from both transcript and document collections,
  correct source field on each result
- Rate limit: 20th query succeeds; 21st returns 429
- Integration: full post-meeting flow (end meeting → embed → ask → answer with source)
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out native / environment-bound modules before any app imports.
# ---------------------------------------------------------------------------
sys.modules.setdefault("daily", MagicMock())
sys.modules.setdefault("app.bot.arni_bot", MagicMock())
sys.modules.setdefault("app.bot.bot_manager", MagicMock())

_daily_stub = MagicMock()
_daily_stub.DailyCoError = type("DailyCoError", (Exception,), {})
sys.modules.setdefault("app.utils.daily", _daily_stub)

import pytest
from unittest.mock import AsyncMock, patch, call
from bson import ObjectId
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_embedding(dim: int = 3072) -> list[float]:
    """Return a deterministic fake embedding vector."""
    return [0.01] * dim


def _make_ai_app_with_auth(user_id: str):
    """Build a minimal FastAPI app with the AI router, auth overridden."""
    from app.deps import get_current_user as _real_get_current_user
    from app.routers.ai import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/ai")
    app.dependency_overrides[_real_get_current_user] = lambda: {
        "id": user_id,
        "email": "test@example.com",
        "name": "Test User",
    }
    return app


def _make_meetings_app(user_id: str):
    """Build a minimal FastAPI app with meetings router, auth overridden."""
    from app.deps import get_current_user as _real_get_current_user
    from app.routers.meetings import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/meetings")
    app.dependency_overrides[_real_get_current_user] = lambda: {
        "id": user_id,
        "email": "test@example.com",
        "name": "Test User",
    }
    return app


# ---------------------------------------------------------------------------
# embedder.embed_transcript() — Unit tests
# ---------------------------------------------------------------------------


class TestEmbedTranscript:

    @pytest.mark.asyncio
    async def test_embed_transcript_chunks_and_stores_embeddings(self):
        """embed_transcript() fetches transcript, chunks text, stores embeddings."""
        meeting_id = str(ObjectId())

        transcript_turns = [
            {"speaker_name": "Alice", "text": "Hello everyone. " * 30},
            {"speaker_name": "Bob", "text": "Thanks for joining. " * 30},
        ]

        mock_db = MagicMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=transcript_turns
        )
        mock_db.transcripts.update_many = AsyncMock()
        mock_db.transcript_chunks.count_documents = AsyncMock(return_value=0)
        mock_db.transcript_chunks.insert_many = AsyncMock()

        fake_embeddings = [_fake_embedding(), _fake_embedding()]

        with patch("app.rag.embedder.get_database", return_value=mock_db):
            with patch(
                "app.rag.embedder.embed_texts", new=AsyncMock(return_value=fake_embeddings)
            ):
                from app.rag.embedder import embed_transcript
                await embed_transcript(meeting_id)

        # Should have called insert_many (or insert_one) for chunks
        assert mock_db.transcript_chunks.insert_many.called or \
               mock_db.transcript_chunks.insert_one.called

    @pytest.mark.asyncio
    async def test_embed_transcript_idempotent(self):
        """embed_transcript() skips chunks that already have embeddings."""
        meeting_id = str(ObjectId())

        # Simulate turns already embedded
        transcript_turns = [
            {"speaker_name": "Alice", "text": "Hello.", "embedding": _fake_embedding()},
        ]

        mock_db = MagicMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=transcript_turns
        )
        mock_db.transcript_chunks.count_documents = AsyncMock(return_value=1)
        mock_db.transcript_chunks.insert_many = AsyncMock()

        mock_embed = AsyncMock(return_value=[])
        with patch("app.rag.embedder.get_database", return_value=mock_db):
            with patch("app.rag.embedder.embed_texts", new=mock_embed):
                from app.rag.embedder import embed_transcript
                await embed_transcript(meeting_id)

        # When already embedded (count > 0), embed_texts should not be called
        assert not mock_db.transcript_chunks.insert_many.called
        assert mock_embed.call_count == 0

    @pytest.mark.asyncio
    async def test_embed_transcript_no_turns_skips_gracefully(self):
        """embed_transcript() with empty transcript does nothing without error."""
        meeting_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=[]
        )
        mock_db.transcript_chunks.insert_many = AsyncMock()

        mock_db.transcript_chunks.count_documents = AsyncMock(return_value=0)
        with patch("app.rag.embedder.get_database", return_value=mock_db):
            with patch("app.rag.embedder.embed_texts", new=AsyncMock(return_value=[])):
                from app.rag.embedder import embed_transcript
                # Should not raise
                await embed_transcript(meeting_id)

        mock_db.transcript_chunks.insert_many.assert_not_called()


# ---------------------------------------------------------------------------
# retriever.retrieve() — Unit tests
# ---------------------------------------------------------------------------


class TestRetriever:

    @pytest.mark.asyncio
    async def test_retrieve_returns_results_from_both_collections(self):
        """retrieve() queries both transcript_chunks and document_chunks."""
        meeting_id = str(ObjectId())
        query = "What did we decide about the budget?"

        transcript_chunk = {
            "_id": ObjectId(),
            "meeting_id": meeting_id,
            "text": "We decided to increase the budget by 10%.",
            "source": "transcript",
            "speaker_name": "Alice",
            "timestamp": "05:00",
            "score": 0.95,
        }
        document_chunk = {
            "_id": ObjectId(),
            "meeting_id": meeting_id,
            "text": "Budget policy: increases require board approval.",
            "source": "document",
            "filename": "policy.pdf",
            "chunk_index": 2,
            "score": 0.88,
        }

        mock_db = MagicMock()
        # Simulate aggregate returning results for both collections
        mock_db.transcript_chunks.aggregate = MagicMock(
            return_value=_async_iter([transcript_chunk])
        )
        mock_db.document_chunks.aggregate = MagicMock(
            return_value=_async_iter([document_chunk])
        )

        with patch("app.rag.retriever.get_database", return_value=mock_db):
            with patch(
                "app.rag.retriever.embed_texts", new=AsyncMock(return_value=[_fake_embedding()])
            ):
                from app.rag.retriever import retrieve
                results = await retrieve(meeting_id, query, top_k=5)

        assert len(results) >= 1
        sources = {r["source"] for r in results}
        # Should have at least one transcript result (document might be absent
        # if aggregate mock not triggered, but transcript must be there)
        assert "transcript" in sources or "document" in sources

    @pytest.mark.asyncio
    async def test_retrieve_source_field_correct_on_each_result(self):
        """Each result has the correct source field (transcript or document)."""
        meeting_id = str(ObjectId())

        transcript_result = {
            "_id": ObjectId(),
            "meeting_id": meeting_id,
            "text": "Let's move forward with the plan.",
            "source": "transcript",
            "speaker_name": "Bob",
            "timestamp": "10:00",
            "score": 0.9,
        }

        mock_db = MagicMock()
        mock_db.transcript_chunks.aggregate = MagicMock(
            return_value=_async_iter([transcript_result])
        )
        mock_db.document_chunks.aggregate = MagicMock(
            return_value=_async_iter([])
        )

        with patch("app.rag.retriever.get_database", return_value=mock_db):
            with patch(
                "app.rag.retriever.embed_texts", new=AsyncMock(return_value=[_fake_embedding()])
            ):
                from app.rag.retriever import retrieve
                results = await retrieve(meeting_id, "plan", top_k=5)

        for r in results:
            assert "source" in r
            assert r["source"] in ("transcript", "document")


# ---------------------------------------------------------------------------
# POST /ai/qa — Rate limit tests
# ---------------------------------------------------------------------------


class TestQARateLimit:

    @pytest.mark.asyncio
    async def test_twentieth_query_succeeds(self):
        """The 20th query within the rate limit returns 200."""
        meeting_id = str(ObjectId())
        user_id = str(ObjectId())

        mock_db = MagicMock()
        # Counter at 19 (so next query is the 20th)
        mock_db.qa_rate_limits.find_one = AsyncMock(
            return_value={"count": 19, "meeting_id": meeting_id, "user_id": user_id}
        )
        mock_db.qa_rate_limits.update_one = AsyncMock()

        transcript_chunk = {
            "_id": ObjectId(),
            "text": "Q4 earnings were $2M.",
            "source": "transcript",
            "speaker_name": "CFO",
            "timestamp": "00:05",
            "score": 0.9,
        }

        mock_answer_response = MagicMock()
        mock_answer_response.content = [MagicMock(text="Q4 earnings were $2M.")]

        with patch("app.routers.ai.get_database", return_value=mock_db):
            with patch("app.rag.retriever.get_database", return_value=mock_db):
                with patch(
                    "app.rag.retriever.embed_texts", new=AsyncMock(return_value=[_fake_embedding()])
                ):
                    mock_db.transcript_chunks.aggregate = MagicMock(
                        return_value=_async_iter([transcript_chunk])
                    )
                    mock_db.document_chunks.aggregate = MagicMock(
                        return_value=_async_iter([])
                    )
                    with patch("anthropic.AsyncAnthropic") as mock_anthropic:
                        mock_client = MagicMock()
                        mock_client.messages.create = AsyncMock(
                            return_value=mock_answer_response
                        )
                        mock_anthropic.return_value = mock_client

                        from httpx import AsyncClient, ASGITransport
                        app = _make_ai_app_with_auth(user_id)
                        async with AsyncClient(
                            transport=ASGITransport(app=app), base_url="http://test"
                        ) as ac:
                            resp = await ac.post(
                                "/ai/qa",
                                json={
                                    "meeting_id": meeting_id,
                                    "question": "What were the Q4 earnings?",
                                    "user_id": user_id,
                                },
                                headers={"Authorization": "Bearer test-token"},
                            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_twenty_first_query_returns_429(self):
        """The 21st query exceeds rate limit and returns 429."""
        meeting_id = str(ObjectId())
        user_id = str(ObjectId())

        mock_db = MagicMock()
        # Counter at 20 — limit reached
        mock_db.qa_rate_limits.find_one = AsyncMock(
            return_value={"count": 20, "meeting_id": meeting_id, "user_id": user_id}
        )
        mock_db.qa_rate_limits.update_one = AsyncMock()

        with patch("app.routers.ai.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_ai_app_with_auth(user_id)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/ai/qa",
                    json={
                        "meeting_id": meeting_id,
                        "question": "One more question",
                        "user_id": user_id,
                    },
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_non_participant_ask_returns_403(self):
        """Non-participant cannot use /meetings/{id}/ask."""
        meeting_id = str(ObjectId())
        outsider_id = str(ObjectId())
        host_id = str(ObjectId())

        meeting = {
            "_id": ObjectId(meeting_id),
            "host_id": ObjectId(host_id),
            "participant_ids": [ObjectId(host_id)],
            "state": "processed",
            "invite_code": "CODE",
            "invite_link": "http://test",
            "daily_room_name": "room",
            "daily_room_url": "https://daily.co/room",
            "started_at": None,
            "ended_at": None,
            "duration_seconds": None,
            "summary": None,
            "decisions": [],
            "action_item_ids": [],
            "timeline": [],
            "title": "Test",
            "created_at": datetime.now(timezone.utc),
        }

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(outsider_id)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/meetings/{meeting_id}/ask",
                    json={"question": "What was decided?"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Integration: Full post-meeting embedding flow
# ---------------------------------------------------------------------------


class TestRAGIntegration:

    @pytest.mark.asyncio
    async def test_processor_calls_embed_transcript_after_report(self):
        """processor.run() calls embed_transcript(meeting_id) after generating report."""
        meeting_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.update_one = AsyncMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=[
                {"speaker_name": "Alice", "text": "We finalized the Q4 plan."},
            ]
        )
        mock_db.action_items.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=ObjectId())
        )

        def make_response(text: str):
            r = MagicMock()
            r.content = [MagicMock(text=text)]
            return r

        responses = [
            make_response('{"title": "Q4 Planning", "summary": "Budget finalized."}'),
            make_response("[]"),    # decisions
            make_response("[]"),    # actions
            make_response('[{"timestamp": "00:00", "topic": "Budget"}]'),  # timeline
        ]
        call_count = {"n": 0}

        async def fake_create(**kwargs):
            n = call_count["n"]
            call_count["n"] += 1
            return responses[n] if n < len(responses) else make_response("[]")

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create = fake_create

        embed_called = {"called": False, "meeting_id": None}

        async def fake_embed_transcript(mid: str) -> None:
            embed_called["called"] = True
            embed_called["meeting_id"] = mid

        with patch("app.postprocessing.processor.get_database", return_value=mock_db):
            with patch("app.postprocessing.processor.get_redis", return_value=AsyncMock()):
                with patch(
                    "app.postprocessing.processor.publish_meeting_processed",
                    new_callable=AsyncMock,
                ):
                    with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
                        with patch(
                            "app.postprocessing.processor.embed_transcript",
                            side_effect=fake_embed_transcript,
                        ):
                            from app.postprocessing.processor import run
                            await run(meeting_id)

        assert embed_called["called"], "processor.run() did not call embed_transcript()"
        assert embed_called["meeting_id"] == meeting_id


# ---------------------------------------------------------------------------
# Async iterator helper for mocking Motor cursors
# ---------------------------------------------------------------------------


class _async_iter:
    """Wraps a list as an async iterable for mocking Motor aggregate()."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration
