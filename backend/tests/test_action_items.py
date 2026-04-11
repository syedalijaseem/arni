"""
TDD tests for Task 2: Editable Action Items + Meeting Timeline.

Tests cover:
- PATCH /meetings/{id}/action-items/{item_id}: valid edit persists, is_edited becomes true
- PATCH with partial body: only provided fields updated; others unchanged
- Non-participant gets 403
- POST /ai/timeline: returns valid array of {timestamp, topic} objects
- Integration: edit action item → assert updated fields returned
- Integration: timeline stored on Meeting document during post-processing
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out native / environment-bound modules before any app imports.
# 'daily' is a native Daily.co SDK not installed in the test environment.
# ---------------------------------------------------------------------------
sys.modules.setdefault("daily", MagicMock())
sys.modules.setdefault("app.bot.arni_bot", MagicMock())
sys.modules.setdefault("app.bot.bot_manager", MagicMock())

_daily_stub = MagicMock()
_daily_stub.create_room = MagicMock()
_daily_stub.create_meeting_token = MagicMock()
_daily_stub.delete_room = MagicMock()
_daily_stub.DailyCoError = type("DailyCoError", (Exception,), {})
sys.modules.setdefault("app.utils.daily", _daily_stub)

import pytest
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime, timezone

from app.deps import get_current_user as _real_get_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_meeting(meeting_id, host_id, participant_ids, action_item_ids=None):
    return {
        "_id": ObjectId(meeting_id),
        "host_id": ObjectId(host_id),
        "participant_ids": [ObjectId(pid) for pid in participant_ids],
        "state": "active",
        "invite_code": "TESTCODE",
        "invite_link": "http://test/meeting/TESTCODE",
        "daily_room_name": "test-room",
        "daily_room_url": "https://daily.co/test-room",
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "summary": None,
        "decisions": [],
        "action_item_ids": [ObjectId(aid) for aid in (action_item_ids or [])],
        "timeline": [],
        "title": "Test Meeting",
        "created_at": datetime.now(timezone.utc),
    }


def _build_action_item(
    item_id,
    meeting_id,
    description="Do the thing",
    assignee=None,
    deadline=None,
    is_edited=False,
):
    return {
        "_id": ObjectId(item_id),
        "meeting_id": meeting_id,
        "description": description,
        "assignee": assignee,
        "deadline": deadline,
        "is_edited": is_edited,
        "created_at": datetime.now(timezone.utc),
    }


def _fake_user(user_id: str):
    return {"id": user_id, "email": "test@example.com", "name": "Test User"}


def _make_meetings_app(user_id: str):
    """Build a minimal FastAPI app with the meetings router, auth dependency overridden."""
    from app.routers.meetings import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/meetings")
    # Override the JWT dependency so tests don't need a real token
    app.dependency_overrides[_real_get_current_user] = lambda: _fake_user(user_id)
    return app


def _make_ai_app():
    """Build a minimal FastAPI app with the AI router."""
    from app.routers.ai import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/ai")
    return app


# ---------------------------------------------------------------------------
# PATCH /meetings/{id}/action-items/{item_id} — Unit tests
# ---------------------------------------------------------------------------


class TestPatchActionItemEndpoint:

    @pytest.mark.asyncio
    async def test_valid_edit_persists_and_is_edited_set(self):
        """Valid edit persists all fields and sets is_edited=True (FR-046)."""
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        user_id = str(ObjectId())

        meeting = _build_meeting(meeting_id, host_id=user_id, participant_ids=[user_id], action_item_ids=[item_id])
        item = _build_action_item(item_id, meeting_id)
        updated_item = {**item, "description": "Updated task", "is_edited": True}

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)
        mock_db.action_items.find_one = AsyncMock(side_effect=[item, updated_item])
        mock_db.action_items.update_one = AsyncMock()

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={"description": "Updated task"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated task"
        assert data["is_edited"] is True

    @pytest.mark.asyncio
    async def test_partial_body_only_updates_provided_fields(self):
        """Only provided fields are updated; others remain unchanged."""
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        user_id = str(ObjectId())

        original = _build_action_item(
            item_id, meeting_id, description="Original", assignee="Alice", deadline="Friday"
        )
        meeting = _build_meeting(
            meeting_id, host_id=user_id, participant_ids=[user_id], action_item_ids=[item_id]
        )
        after_update = {**original, "assignee": "Bob", "is_edited": True}

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)
        mock_db.action_items.find_one = AsyncMock(side_effect=[original, after_update])
        mock_db.action_items.update_one = AsyncMock()

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={"assignee": "Bob"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assignee"] == "Bob"
        assert data["description"] == "Original"
        assert data["deadline"] == "Friday"
        assert data["is_edited"] is True

        # Verify update_one was called with ONLY the provided field + is_edited
        update_call = mock_db.action_items.update_one.call_args
        update_doc = update_call[0][1]
        assert "assignee" in update_doc["$set"]
        assert "description" not in update_doc["$set"]
        assert "deadline" not in update_doc["$set"]
        assert update_doc["$set"]["is_edited"] is True

    @pytest.mark.asyncio
    async def test_non_participant_gets_403(self):
        """A user who is not a meeting participant receives 403 Forbidden."""
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        host_id = str(ObjectId())
        outsider_id = str(ObjectId())

        # Meeting has only host as participant; outsider is not included
        meeting = _build_meeting(meeting_id, host_id=host_id, participant_ids=[host_id])

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            # outsider makes the request
            app = _make_meetings_app(outsider_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={"description": "Hacker update"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_host_can_also_edit_action_items(self):
        """Host editing works the same as participant editing (FR-046)."""
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        host_id = str(ObjectId())

        meeting = _build_meeting(
            meeting_id, host_id=host_id, participant_ids=[host_id], action_item_ids=[item_id]
        )
        item = _build_action_item(item_id, meeting_id, description="Host task")
        updated = {**item, "deadline": "Next Monday", "is_edited": True}

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)
        mock_db.action_items.find_one = AsyncMock(side_effect=[item, updated])
        mock_db.action_items.update_one = AsyncMock()

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(host_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={"deadline": "Next Monday"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deadline"] == "Next Monday"
        assert data["is_edited"] is True

    @pytest.mark.asyncio
    async def test_action_item_not_found_returns_404(self):
        """Returns 404 when action item does not exist."""
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        user_id = str(ObjectId())

        meeting = _build_meeting(meeting_id, host_id=user_id, participant_ids=[user_id])

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)
        mock_db.action_items.find_one = AsyncMock(return_value=None)

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={"description": "Ghost update"},
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /ai/timeline — Unit tests
# ---------------------------------------------------------------------------


class TestTimelineEndpoint:

    @pytest.mark.asyncio
    async def test_timeline_returns_valid_array(self):
        """Timeline endpoint returns array of {timestamp, topic} objects."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='[{"timestamp": "00:00", "topic": "Introductions"}, {"timestamp": "05:30", "topic": "Budget Review"}]'
        )]

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "test-key"

        with patch("app.config.get_settings", return_value=mock_settings):
            with patch("anthropic.AsyncAnthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_anthropic.return_value = mock_client

                from httpx import AsyncClient, ASGITransport
                app = _make_ai_app()
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/timeline", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "00:00 Alice: Hi everyone. 05:30 Bob: Let's review the budget.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert "timeline" in data
        assert len(data["timeline"]) == 2
        assert data["timeline"][0]["timestamp"] == "00:00"
        assert data["timeline"][0]["topic"] == "Introductions"
        assert data["timeline"][1]["timestamp"] == "05:30"
        assert data["timeline"][1]["topic"] == "Budget Review"

    @pytest.mark.asyncio
    async def test_timeline_no_api_key_returns_503(self):
        """Missing API key returns 503."""
        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = ""

        with patch("app.config.get_settings", return_value=mock_settings):
            from httpx import AsyncClient, ASGITransport
            app = _make_ai_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post("/ai/timeline", json={
                    "meeting_id": "meet-1",
                    "transcript_text": "Some text",
                })

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_timeline_handles_markdown_fenced_response(self):
        """Timeline strips markdown code fences from LLM response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='```json\n[{"timestamp": "00:00", "topic": "Kickoff"}]\n```'
        )]

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_API_KEY = "test-key"

        with patch("app.config.get_settings", return_value=mock_settings):
            with patch("anthropic.AsyncAnthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_anthropic.return_value = mock_client

                from httpx import AsyncClient, ASGITransport
                app = _make_ai_app()
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    resp = await ac.post("/ai/timeline", json={
                        "meeting_id": "meet-1",
                        "transcript_text": "Alice: Let's kick off the meeting.",
                    })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["timeline"]) == 1
        assert data["timeline"][0]["topic"] == "Kickoff"


# ---------------------------------------------------------------------------
# Integration: Edit action item then assert fields updated
# ---------------------------------------------------------------------------


class TestActionItemIntegration:

    @pytest.mark.asyncio
    async def test_edit_action_item_fields_persisted(self):
        """
        Integration: edit action item → response reflects all updated fields
        including is_edited=True.
        """
        meeting_id = str(ObjectId())
        item_id = str(ObjectId())
        user_id = str(ObjectId())

        meeting = _build_meeting(
            meeting_id, host_id=user_id, participant_ids=[user_id], action_item_ids=[item_id]
        )
        item = _build_action_item(
            item_id, meeting_id, description="Buy coffee", assignee=None, deadline=None
        )
        after_update = {
            **item,
            "description": "Buy coffee and tea",
            "assignee": "Carol",
            "deadline": "Tomorrow",
            "is_edited": True,
        }

        mock_db = MagicMock()
        mock_db.meetings.find_one = AsyncMock(return_value=meeting)
        mock_db.action_items.find_one = AsyncMock(side_effect=[item, after_update])
        mock_db.action_items.update_one = AsyncMock()

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            from httpx import AsyncClient, ASGITransport
            app = _make_meetings_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/meetings/{meeting_id}/action-items/{item_id}",
                    json={
                        "description": "Buy coffee and tea",
                        "assignee": "Carol",
                        "deadline": "Tomorrow",
                    },
                    headers={"Authorization": "Bearer test-token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Buy coffee and tea"
        assert data["assignee"] == "Carol"
        assert data["deadline"] == "Tomorrow"
        assert data["is_edited"] is True
        assert data["meeting_id"] == meeting_id


# ---------------------------------------------------------------------------
# Integration: Timeline stored on Meeting document during post-processing
# ---------------------------------------------------------------------------


class TestTimelinePostProcessingIntegration:

    @pytest.mark.asyncio
    async def test_processor_stores_timeline_on_meeting(self):
        """
        Integration: processor.run() stores the AI-generated timeline on the
        Meeting document under timeline[].
        """
        meeting_id = str(ObjectId())
        timeline_json = (
            '[{"timestamp": "00:00", "topic": "Opening"}, '
            '{"timestamp": "10:00", "topic": "Closing"}]'
        )

        mock_db = MagicMock()
        mock_db.meetings.update_one = AsyncMock()
        mock_db.transcripts.find.return_value.sort.return_value.to_list = AsyncMock(
            return_value=[
                {"speaker": "Alice", "text": "Let's open the meeting."},
                {"speaker": "Bob", "text": "Thanks everyone, closing now."},
            ]
        )
        mock_db.action_items.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=ObjectId())
        )

        def make_response(text: str):
            r = MagicMock()
            r.content = [MagicMock(text=text)]
            return r

        # Responses in the order processor.run() calls Claude:
        # 1. title+summary (single combined call returning JSON object)
        # 2. decisions
        # 3. actions
        # 4. timeline
        responses = [
            make_response('{"title": "Test Meeting", "summary": "A short summary."}'),  # title+summary
            make_response("[]"),                 # decisions
            make_response("[]"),                 # actions
            make_response(timeline_json),        # timeline
        ]
        call_count = {"n": 0}

        async def fake_create(**kwargs):
            n = call_count["n"]
            call_count["n"] += 1
            return responses[n] if n < len(responses) else make_response("[]")

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create = fake_create

        # Patch at the source where processor.py resolves its references
        with patch("app.postprocessing.processor.get_database", return_value=mock_db):
            with patch("app.postprocessing.processor.get_redis", return_value=AsyncMock()):
                with patch(
                    "app.postprocessing.processor.publish_meeting_processed",
                    new_callable=AsyncMock,
                ):
                    with patch(
                        "anthropic.AsyncAnthropic",
                        return_value=mock_anthropic_client,
                    ):
                        from app.postprocessing.processor import run
                        await run(meeting_id)

        # Verify timeline was stored in an update_one call
        timeline_stored = False
        for c in mock_db.meetings.update_one.call_args_list:
            args, _ = c
            if len(args) > 1 and "$set" in args[1]:
                if "timeline" in args[1]["$set"]:
                    stored = args[1]["$set"]["timeline"]
                    if len(stored) >= 2:
                        assert stored[0]["timestamp"] == "00:00"
                        assert stored[0]["topic"] == "Opening"
                        timeline_stored = True
                    break

        assert timeline_stored, "processor.run() did not store timeline[] on the Meeting document"
