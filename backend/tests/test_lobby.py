"""
TDD tests for Task 6: Lobby/waiting room invite flow.

Tests cover:
- invite_participant: adds email to invite_list
- admit_participant: moves user from waiting room to participant_ids
- reject_participant: removes user from waiting room
- transfer_host: updates host_id
- dashboard scoping: meetings not visible to users not in invite_list or host
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _patch_native_modules():
    """Prevent native modules from being imported during test collection."""
    for mod in ("daily", "deepgram"):
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()


_patch_native_modules()


class TestInviteEndpoint:

    @pytest.mark.asyncio
    async def test_invite_adds_email_to_invite_list(self):
        """invite_participant adds email to invite_list and returns invited=True."""
        from bson import ObjectId
        meet_oid = ObjectId()

        with patch("app.routers.meetings.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db
            mock_db.meetings.update_one = AsyncMock()

            from app.routers.meetings import invite_participant
            result = await invite_participant(
                meeting_id=str(meet_oid),
                email="alice@example.com",
                meeting={"_id": meet_oid, "host_id": "user-1", "invite_list": []},
            )

        assert result["invited"] is True
        assert result["email"] == "alice@example.com"
        mock_db.meetings.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_admit_moves_user_to_participants(self):
        """admit_participant removes user from waiting room and adds to participants."""
        from bson import ObjectId
        meet_oid = ObjectId()

        with patch("app.routers.meetings.get_database") as mock_db_fn:
            with patch("app.routers.meetings.lobby_manager") as mock_lobby:
                mock_db = MagicMock()
                mock_db_fn.return_value = mock_db
                mock_db.meetings.update_one = AsyncMock()
                mock_lobby.remove_from_waiting_room = AsyncMock()

                from app.routers.meetings import admit_participant
                result = await admit_participant(
                    meeting_id=str(meet_oid),
                    user_id="user-2",
                    meeting={"_id": meet_oid, "host_id": "user-1", "participant_ids": []},
                    current_user={"id": "user-1"},
                )

        assert result["admitted"] is True
        mock_lobby.remove_from_waiting_room.assert_called_once()
        mock_db.meetings.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_removes_user_from_waiting_room(self):
        """reject_participant removes user from waiting room and returns rejected=True."""
        from bson import ObjectId
        meet_oid = ObjectId()

        with patch("app.routers.meetings.lobby_manager") as mock_lobby:
            mock_lobby.remove_from_waiting_room = AsyncMock()

            from app.routers.meetings import reject_participant
            result = await reject_participant(
                meeting_id=str(meet_oid),
                user_id="user-2",
                meeting={"_id": meet_oid, "host_id": "user-1"},
            )

        assert result["rejected"] is True
        mock_lobby.remove_from_waiting_room.assert_called_once()

    @pytest.mark.asyncio
    async def test_transfer_host_updates_host_id(self):
        """transfer_host updates host_id in MongoDB and returns transferred=True."""
        from bson import ObjectId
        meet_oid = ObjectId()

        with patch("app.routers.meetings.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db
            mock_db.meetings.update_one = AsyncMock()

            from app.routers.meetings import transfer_host
            result = await transfer_host(
                meeting_id=str(meet_oid),
                new_host_id="user-2",
                meeting={"_id": meet_oid, "host_id": "user-1"},
            )

        assert result["transferred"] is True
        mock_db.meetings.update_one.assert_called_once()


class TestDashboardScoping:

    @pytest.mark.asyncio
    async def test_list_meetings_only_returns_own_meetings(self):
        """list_meetings queries with $or on host_id and invite_list (FR-068)."""
        with patch("app.routers.meetings.get_database") as mock_db_fn:
            mock_db = MagicMock()
            mock_db_fn.return_value = mock_db

            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=[
                {
                    "_id": "meet-1",
                    "host_id": "user-1-oid",
                    "invite_list": [],
                    "state": "created",
                    "title": "My Meeting",
                    "invite_code": "abc12345",
                    "created_at": "2026-01-01T00:00:00Z",
                    "started_at": None,
                    "ended_at": None,
                    "duration_seconds": None,
                    "participant_ids": [],
                    "action_item_ids": [],
                }
            ])
            mock_db.meetings.find.return_value = mock_cursor

            from app.routers.meetings import list_meetings
            result = await list_meetings(current_user={"id": "507f1f77bcf86cd799439011", "email": "host@example.com"})

        # Verify the query uses $or to scope to host or invited
        call_args = mock_db.meetings.find.call_args[0][0]
        assert "$or" in call_args, "list_meetings must use $or to scope to host or invite_list"
