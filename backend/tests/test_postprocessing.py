"""
TDD tests for Task 1: Post-Meeting Processing Pipeline.

Tests cover:
- extract-decisions: explicit decision extracted; implied decision → empty list
- extract-actions: explicit assignment extracted; vague discussion → empty list
- State transitions: Active → Ended → Processed
- processor.run() sets state, stores fields, publishes event
- POST /meetings/{id}/end triggers async processing without blocking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


# ---------------------------------------------------------------------------
# POST /ai/extract-decisions
# ---------------------------------------------------------------------------

class TestExtractDecisionsEndpoint:

    @pytest.mark.asyncio
    async def test_explicit_decision_extracted(self):
        """Explicit decision in transcript is returned."""
        with patch("app.ai.llm_client.is_configured", return_value=True):
            with patch(
                "app.ai.llm_client.chat",
                new_callable=AsyncMock,
                return_value='["We decided to use PostgreSQL for the database."]',
            ):
                from app.routers.ai import router
                from fastapi import FastAPI

                app = FastAPI()
                app.include_router(router, prefix="/ai")

                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/extract-decisions", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "Alice: We decided to use PostgreSQL for the database.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert "decisions" in data
        assert len(data["decisions"]) == 1
        assert "PostgreSQL" in data["decisions"][0]

    @pytest.mark.asyncio
    async def test_implied_decision_returns_empty(self):
        """No explicit decisions → empty list returned (FR-042)."""
        with patch("app.ai.llm_client.is_configured", return_value=True):
            with patch(
                "app.ai.llm_client.chat",
                new_callable=AsyncMock,
                return_value="[]",
            ):
                from app.routers.ai import router
                from fastapi import FastAPI

                app = FastAPI()
                app.include_router(router, prefix="/ai")

                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/extract-decisions", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "Alice: Maybe we should consider PostgreSQL.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert data["decisions"] == []

    @pytest.mark.asyncio
    async def test_no_api_key_returns_503(self):
        """Missing API key returns 503."""
        with patch("app.ai.llm_client.is_configured", return_value=False):
            from app.routers.ai import router
            from fastapi import FastAPI

            app = FastAPI()
            app.include_router(router, prefix="/ai")

            from httpx import AsyncClient, ASGITransport
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/ai/extract-decisions", json={
                    "meeting_id": "meet-1",
                    "transcript_text": "Some text",
                })

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /ai/extract-actions
# ---------------------------------------------------------------------------

class TestExtractActionsEndpoint:

    @pytest.mark.asyncio
    async def test_explicit_assignment_extracted(self):
        """Explicit assignment → action item returned (FR-043)."""
        with patch("app.ai.llm_client.is_configured", return_value=True):
            with patch(
                "app.ai.llm_client.chat",
                new_callable=AsyncMock,
                return_value='[{"description": "Write the report", "assignee": "Bob", "deadline": "Friday"}]',
            ):
                from app.routers.ai import router
                from fastapi import FastAPI

                app = FastAPI()
                app.include_router(router, prefix="/ai")

                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/extract-actions", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "Bob: I will write the report by Friday.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert "action_items" in data
        assert len(data["action_items"]) == 1
        item = data["action_items"][0]
        assert item["description"] == "Write the report"
        assert item["assignee"] == "Bob"
        assert item["deadline"] == "Friday"

    @pytest.mark.asyncio
    async def test_vague_discussion_returns_empty(self):
        """No explicit commitment → empty action item list (FR-043)."""
        with patch("app.ai.llm_client.is_configured", return_value=True):
            with patch(
                "app.ai.llm_client.chat",
                new_callable=AsyncMock,
                return_value="[]",
            ):
                from app.routers.ai import router
                from fastapi import FastAPI

                app = FastAPI()
                app.include_router(router, prefix="/ai")

                from httpx import AsyncClient, ASGITransport
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/extract-actions", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "Alice: We talked about maybe doing a report.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert data["action_items"] == []


# ---------------------------------------------------------------------------
# processor.run() state transitions
# ---------------------------------------------------------------------------

class TestProcessorRun:

    @pytest.mark.asyncio
    async def test_state_transitions_active_ended_processed(self):
        """processor.run() transitions meeting: sets Ended then Processed."""
        meeting_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.update_one = AsyncMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        mock_db.action_items.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        with patch("app.postprocessing.processor.get_database", return_value=mock_db):
            with patch("app.postprocessing.processor.get_redis", return_value=AsyncMock()):
                with patch("app.postprocessing.processor.publish_meeting_processed", new_callable=AsyncMock):
                    from app.postprocessing.processor import run
                    await run(meeting_id)

        calls = mock_db.meetings.update_one.call_args_list
        states = []
        for call in calls:
            args, _ = call
            if len(args) > 1 and "$set" in args[1]:
                if "state" in args[1]["$set"]:
                    states.append(args[1]["$set"]["state"])

        assert "ended" in states
        assert "processed" in states

    @pytest.mark.asyncio
    async def test_meeting_processed_event_published(self):
        """processor.run() publishes meeting.processed event on completion."""
        meeting_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.update_one = AsyncMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        mock_db.action_items.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        mock_publish = AsyncMock()
        with patch("app.postprocessing.processor.get_database", return_value=mock_db):
            with patch("app.postprocessing.processor.get_redis", return_value=AsyncMock()):
                with patch("app.postprocessing.processor.publish_meeting_processed", mock_publish):
                    from app.postprocessing.processor import run
                    await run(meeting_id)

        mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_transcript_stores_defaults(self):
        """When no transcripts exist, pipeline stores empty decisions and action items."""
        meeting_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.update_one = AsyncMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        mock_db.action_items.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))

        with patch("app.postprocessing.processor.get_database", return_value=mock_db):
            with patch("app.postprocessing.processor.get_redis", return_value=AsyncMock()):
                with patch("app.postprocessing.processor.publish_meeting_processed", new_callable=AsyncMock):
                    from app.postprocessing.processor import run
                    await run(meeting_id)

        calls = mock_db.meetings.update_one.call_args_list
        stored_data = {}
        for call in calls:
            args, _ = call
            if len(args) > 1 and "$set" in args[1]:
                update_fields = args[1]["$set"]
                if "title" in update_fields:
                    stored_data = update_fields
                    break

        assert stored_data.get("decisions") == []
        assert stored_data.get("action_item_ids") == []
