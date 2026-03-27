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
    JoinMeetingResponse,
    MeetingState,
)
from app.utils.daily import (
    create_room,
    create_meeting_token,
    delete_room,
    DailyCoError,
)
from app.bot.bot_manager import bot_manager
from app.routers.transcripts import handle_bot_transcript

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
        daily_room_name=meeting.get("daily_room_name"),
        daily_room_url=meeting.get("daily_room_url"),
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
    """Create a new meeting room with Daily.co integration."""
    db = get_database()

    # Generate unique invite code
    invite_code = _generate_invite_code()
    invite_link = f"{settings.FRONTEND_URL}/meeting/{invite_code}"

    # Create Daily.co room
    daily_room_name = None
    daily_room_url = None

    if settings.DAILY_API_KEY:
        try:
            # Use invite code as room name for uniqueness
            daily_room_data = await create_room(name=f"arni-{invite_code}")
            daily_room_name = daily_room_data["name"]
            daily_room_url = daily_room_data["url"]
        except DailyCoError as e:
            print(f"Warning: Failed to create Daily.co room: {e}")
            # Continue without Daily.co - meeting can still be created
    else:
        print("Warning: DAILY_API_KEY not configured - meeting created without video room")

    # Create meeting document
    meeting_doc = {
        "title": data.title or "Untitled Meeting",
        "host_id": ObjectId(current_user["id"]),
        "participant_ids": [ObjectId(current_user["id"])],  # Host is first participant
        "state": MeetingState.CREATED,
        "invite_code": invite_code,
        "invite_link": invite_link,
        "daily_room_name": daily_room_name,
        "daily_room_url": daily_room_url,
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

    # Delete Daily.co room if it exists
    if meeting.get("daily_room_name") and settings.DAILY_API_KEY:
        try:
            await delete_room(meeting["daily_room_name"])
        except DailyCoError as e:
            print(f"Warning: Failed to delete Daily.co room: {e}")
            # Continue with meeting deletion

    # Delete the meeting
    await db.meetings.delete_one({"_id": ObjectId(meeting_id)})

    # In a production system, we would also delete:
    # - Transcript chunks
    # - Action items
    # - Vector embeddings
    # This will be implemented in later phases

    return None


@router.post("/{meeting_id}/join", response_model=JoinMeetingResponse)
async def join_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Join a meeting and get Daily.co token.

    This endpoint:
    - Adds the user to the participant list if not already there
    - Generates a Daily.co meeting token for the user
    - Transitions the meeting to Active state if this is the first join
    """
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

    # Check if meeting has ended
    if meeting["state"] in [MeetingState.ENDED, MeetingState.PROCESSED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This meeting has ended",
        )

    # Add user to participants if not already there
    user_oid = ObjectId(current_user["id"])
    if user_oid not in meeting.get("participant_ids", []):
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {"$push": {"participant_ids": user_oid}}
        )
        meeting["participant_ids"].append(user_oid)

    # Transition to Active if this is the first join and state is Created
    if meeting["state"] == MeetingState.CREATED:
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {
                "$set": {
                    "state": MeetingState.ACTIVE,
                    "started_at": datetime.now(timezone.utc),
                }
            }
        )
        meeting["state"] = MeetingState.ACTIVE
        meeting["started_at"] = datetime.now(timezone.utc)
        
        # Spin up Arni bot
        import asyncio
        asyncio.create_task(bot_manager.start_bot_for_meeting(
            meeting_id=meeting_id,
            room_url=meeting["daily_room_url"],
            broadcast_callback=handle_bot_transcript
        ))

    # Generate Daily.co token
    if not meeting.get("daily_room_name"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Meeting room not configured (Daily.co room missing)",
        )

    try:
        is_owner = str(meeting["host_id"]) == current_user["id"]
        daily_token = await create_meeting_token(
            room_name=meeting["daily_room_name"],
            user_name=current_user["name"],
            user_id=current_user["id"],
            is_owner=is_owner,
        )
    except DailyCoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate meeting token: {str(e)}",
        )

    return JoinMeetingResponse(
        meeting=_meeting_response(meeting),
        daily_token=daily_token,
        daily_room_url=meeting["daily_room_url"],
    )


@router.get("/code/{invite_code}", response_model=MeetingResponse)
async def get_meeting_by_code(
    invite_code: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get meeting details by invite code.
    Used to resolve an invite link to a meeting ID before joining.
    """
    db = get_database()

    meeting = await db.meetings.find_one({"invite_code": invite_code})

    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )

    return _meeting_response(meeting)


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
                invite_code=meeting["invite_code"],
                created_at=meeting["created_at"],
                started_at=meeting.get("started_at"),
                ended_at=meeting.get("ended_at"),
                duration_seconds=meeting.get("duration_seconds"),
                participant_count=len(meeting.get("participant_ids", [])),
                action_item_count=len(meeting.get("action_item_ids", [])),
            )
        )

    return meeting_list
