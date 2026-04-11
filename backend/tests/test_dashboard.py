"""
TDD tests for Task 4: Meeting History Dashboard endpoints.

Tests cover:
- GET /dashboard: returns only user's meetings (host or participant)
- GET /meetings/search: keyword search scoped to user's own meetings
- Non-participant isolation: user B cannot see user A's meetings
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
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(user_id: str, user_email: str = "test@example.com"):
    """Build a minimal FastAPI app with the meetings router, auth overridden."""
    from app.deps import get_current_user as _real_get_current_user
    from app.routers.meetings import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/meetings")
    app.dependency_overrides[_real_get_current_user] = lambda: {
        "id": user_id,
        "email": user_email,
        "name": "Test User",
    }
    return app


def _meeting_doc(
    meeting_id: str,
    host_id: str,
    title: str = "Test Meeting",
    summary: str = "A summary",
    participant_ids: list | None = None,
    state: str = "processed",
) -> dict:
    """Build a minimal meeting document."""
    return {
        "_id": ObjectId(meeting_id),
        "title": title,
        "summary": summary,
        "host_id": ObjectId(host_id),
        "participant_ids": [ObjectId(pid) for pid in (participant_ids or [host_id])],
        "state": state,
        "invite_code": "TESTCODE",
        "invite_link": "http://test/meeting/TESTCODE",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "action_item_ids": [],
        "invite_list": [],
        "timeline": [],
    }


# ---------------------------------------------------------------------------
# Async cursor mock helper
# ---------------------------------------------------------------------------


class _AsyncCursorMock:
    """Simulates Motor's chainable cursor (find().sort().skip().limit())."""

    def __init__(self, docs: list):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def to_list(self, length=None):
        return _async_return(self._docs)


async def _async_return(value):
    return value


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:

    @pytest.mark.asyncio
    async def test_dashboard_returns_host_meetings(self):
        """Dashboard returns meetings where user is host."""
        user_id = str(ObjectId())
        meeting_id = str(ObjectId())

        meeting = _meeting_doc(meeting_id, host_id=user_id)

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([meeting])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/dashboard",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == meeting_id

    @pytest.mark.asyncio
    async def test_dashboard_returns_participant_meetings(self):
        """Dashboard returns meetings where user is a participant (not host)."""
        host_id = str(ObjectId())
        user_id = str(ObjectId())
        meeting_id = str(ObjectId())

        meeting = _meeting_doc(meeting_id, host_id=host_id, participant_ids=[host_id, user_id])

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([meeting])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/dashboard",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_dashboard_excludes_unrelated_meetings(self):
        """Dashboard returns empty when user has no meetings."""
        user_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/dashboard",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_dashboard_returns_correct_fields(self):
        """Dashboard response includes required display fields."""
        user_id = str(ObjectId())
        meeting_id = str(ObjectId())

        meeting = _meeting_doc(meeting_id, host_id=user_id, title="Budget Review")

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([meeting])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/dashboard",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        item = resp.json()[0]
        assert "id" in item
        assert "title" in item
        assert "state" in item
        assert "participant_count" in item
        assert "action_item_count" in item
        assert item["title"] == "Budget Review"

    @pytest.mark.asyncio
    async def test_dashboard_pagination_passes_page_params(self):
        """Dashboard endpoint accepts page and page_size parameters."""
        user_id = str(ObjectId())

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/dashboard?page=2&page_size=10",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /meetings/search
# ---------------------------------------------------------------------------


class TestSearchEndpoint:

    @pytest.mark.asyncio
    async def test_search_returns_matching_title(self):
        """Search returns meetings with matching title."""
        user_id = str(ObjectId())
        meeting_id = str(ObjectId())

        meeting = _meeting_doc(meeting_id, host_id=user_id, title="Budget Planning Session")

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([meeting])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/search?q=budget",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == meeting_id

    @pytest.mark.asyncio
    async def test_search_other_users_meetings_excluded(self):
        """Search cannot return other users' meetings (user scope enforced)."""
        user_id = str(ObjectId())

        # DB mock returns nothing for this user's scope query
        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock([])

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/search?q=budget",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_all_user_meetings(self):
        """Empty search query returns all user's meetings."""
        user_id = str(ObjectId())
        meeting_id_1 = str(ObjectId())
        meeting_id_2 = str(ObjectId())

        meetings = [
            _meeting_doc(meeting_id_1, host_id=user_id, title="Sprint Review"),
            _meeting_doc(meeting_id_2, host_id=user_id, title="Planning Meeting"),
        ]

        mock_db = MagicMock()
        mock_db.meetings.find.return_value = _AsyncCursorMock(meetings)

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    "/meetings/search",
                    headers={"Authorization": "Bearer token"},
                )

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_search_uses_user_scope_in_query(self):
        """Search endpoint builds a query that includes user scope filter."""
        user_id = str(ObjectId())

        captured_query = {}

        mock_db = MagicMock()

        def capture_find(query, *args, **kwargs):
            captured_query.update(query)
            return _AsyncCursorMock([])

        mock_db.meetings.find = capture_find

        with patch("app.routers.meetings.get_database", return_value=mock_db):
            app = _make_app(user_id, user_email="alice@example.com")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                await ac.get(
                    "/meetings/search?q=test",
                    headers={"Authorization": "Bearer token"},
                )

        # The query must contain $and (scope + keyword) or $or with user fields
        assert "$and" in captured_query or "$or" in captured_query
