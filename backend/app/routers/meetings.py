from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
import secrets

from app.config import get_settings
from app.database import get_database
from app.deps import get_current_user
from app.models.meeting import (
    MeetingCreate,
    MeetingResponse,
    MeetingListResponse,
    MeetingState,
)

router = APIRouter()
settings = get_settings()


def _generate_invite_code() -> str:
    """Generate a random 8-character invite code."""
    return secrets.token_urlsafe(6)[:8]


def _meeting_response(meeting: dict) -> MeetingResponse:
    """Convert a MongoDB meeting document to a MeetingResponse."""
    return MeetingResponse(
        id=str(meeting["_id"]),
        title=meeting.get("title"),
        host_id=str(meeting["host_id"]),
        participant_ids=[str(pid) for pid in meeting.get("participant_ids", [])],
        state=meeting["state"],
        invite_link=meeting["invite_link"],
        started_at=meeting.get("started_at"),
        ended_at=meeting.get("ended_at"),
        duration_seconds=meeting.get("duration_seconds"),
        created_at=meeting["created_at"],
        summary=meeting.get("summary"),
        decisions=meeting.get("decisions", []),
        action_item_ids=[str(aid) for aid in meeting.get("action_item_ids", [])],
        timeline=meeting.get("timeline", []),
    )


@router.post("/create", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    data: MeetingCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new meeting room."""
    db = get_database()

    # Generate unique invite code
    invite_code = _generate_invite_code()
    # In production, use your actual domain
    invite_link = f"{settings.FRONTEND_URL}/meeting/{invite_code}"

    # Create meeting document
    meeting_doc = {
        "title": data.title or "Untitled Meeting",
        "host_id": ObjectId(current_user["id"]),
        "participant_ids": [ObjectId(current_user["id"])],  # Host is first participant
        "state": MeetingState.CREATED,
        "invite_code": invite_code,
        "invite_link": invite_link,
        "started_at": None,
        "ended_at": None,
        "duration_seconds": None,
        "summary": None,
        "decisions": [],
        "action_item_ids": [],
        "timeline": [],
        "created_at": datetime.now(timezone.utc),
    }

    result = await db.meetings.insert_one(meeting_doc)
    meeting_doc["_id"] = result.inserted_id

    return _meeting_response(meeting_doc)


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get meeting details by ID."""
    db = get_database()

    try:
        meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid meeting ID",
        )

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    # Check if user is a participant
    user_oid = ObjectId(current_user["id"])
    if user_oid not in meeting.get("participant_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you are not a participant in this meeting",
        )

    return _meeting_response(meeting)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a meeting. Only the host can delete."""
    db = get_database()

    try:
        meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid meeting ID",
        )

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    # Only host can delete
    if str(meeting["host_id"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting host can delete this meeting",
        )

    # Delete the meeting
    await db.meetings.delete_one({"_id": ObjectId(meeting_id)})

    # In a production system, we would also delete:
    # - Transcript chunks
    # - Action items
    # - Vector embeddings
    # This will be implemented in later phases

    return None


@router.get("", response_model=list[MeetingListResponse])
async def list_meetings(
    current_user: dict = Depends(get_current_user),
):
    """List all meetings where the user is a participant."""
    db = get_database()

    user_oid = ObjectId(current_user["id"])

    # Find all meetings where user is a participant
    cursor = db.meetings.find(
        {"participant_ids": user_oid}
    ).sort("created_at", -1)  # Most recent first

    meetings = await cursor.to_list(length=100)  # Limit to 100 for now

    # Convert to response format
    meeting_list = []
    for meeting in meetings:
        meeting_list.append(
            MeetingListResponse(
                id=str(meeting["_id"]),
                title=meeting.get("title"),
                state=meeting["state"],
                created_at=meeting["created_at"],
                started_at=meeting.get("started_at"),
                ended_at=meeting.get("ended_at"),
                duration_seconds=meeting.get("duration_seconds"),
                participant_count=len(meeting.get("participant_ids", [])),
                action_item_count=len(meeting.get("action_item_ids", [])),
            )
        )

    return meeting_list
