import logging
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import secrets

logger = logging.getLogger(__name__)

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
from app.routers.transcripts import handle_bot_transcript, handle_wake_word
from app.lobby.lobby_manager import lobby_manager

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


@router.get("/dashboard", response_model=list[MeetingListResponse])
async def dashboard(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """
    Return paginated meetings for the authenticated user's dashboard (FR-049, FR-073).

    Scoped to meetings where the user is host OR listed as a participant.
    Default page size: 20.
    """
    db = get_database()

    user_oid = ObjectId(current_user["id"])
    user_email = current_user.get("email", "")

    query = {
        "$or": [
            {"host_id": user_oid},
            {"participant_ids": user_oid},
            {"invite_list": {"$regex": f"^{user_email}$", "$options": "i"}},
        ]
    }

    skip = (page - 1) * page_size
    cursor = db.meetings.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    meetings = await cursor.to_list(length=page_size)

    return [
        MeetingListResponse(
            id=str(m["_id"]),
            title=m.get("title"),
            state=m["state"],
            invite_code=m["invite_code"],
            created_at=m["created_at"],
            started_at=m.get("started_at"),
            ended_at=m.get("ended_at"),
            duration_seconds=m.get("duration_seconds"),
            participant_count=len(m.get("participant_ids", [])),
            action_item_count=len(m.get("action_item_ids", [])),
        )
        for m in meetings
    ]


@router.get("/search", response_model=list[MeetingListResponse])
async def search_meetings(
    q: str = "",
    current_user: dict = Depends(get_current_user),
):
    """
    Keyword search across title and summary, scoped to the user's own meetings (FR-073).

    Returns meetings matching the query where the user is host or participant.
    Cannot return other users' meetings.
    """
    db = get_database()

    user_oid = ObjectId(current_user["id"])
    user_email = current_user.get("email", "")

    user_scope = {
        "$or": [
            {"host_id": user_oid},
            {"participant_ids": user_oid},
            {"invite_list": {"$regex": f"^{user_email}$", "$options": "i"}},
        ]
    }

    if q.strip():
        keyword_filter = {
            "$or": [
                {"title": {"$regex": q.strip(), "$options": "i"}},
                {"summary": {"$regex": q.strip(), "$options": "i"}},
            ]
        }
        query = {"$and": [user_scope, keyword_filter]}
    else:
        query = user_scope

    cursor = db.meetings.find(query).sort("created_at", -1).limit(50)
    meetings = await cursor.to_list(length=50)

    return [
        MeetingListResponse(
            id=str(m["_id"]),
            title=m.get("title"),
            state=m["state"],
            invite_code=m["invite_code"],
            created_at=m["created_at"],
            started_at=m.get("started_at"),
            ended_at=m.get("ended_at"),
            duration_seconds=m.get("duration_seconds"),
            participant_count=len(m.get("participant_ids", [])),
            action_item_count=len(m.get("action_item_ids", [])),
        )
        for m in meetings
    ]


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
            broadcast_callback=handle_bot_transcript,
            wake_word_callback=handle_wake_word,
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
    """List meetings where the user is host or in invite_list (FR-068)."""
    db = get_database()

    user_oid = ObjectId(current_user["id"])
    user_email = current_user.get("email", "")

    # Scope to meetings where user is host OR their email is in invite_list
    cursor = db.meetings.find(
        {
            "$or": [
                {"host_id": user_oid},
                {"invite_list": {"$regex": f"^{user_email}$", "$options": "i"}},
            ]
        }
    ).sort("created_at", -1)

    meetings = await cursor.to_list(length=100)

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


# ---------------------------------------------------------------------------
# Access control endpoints (FR-058–FR-074)
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    email: str


@router.post("/{meeting_id}/invite")
async def invite_participant(
    meeting_id: str,
    body: InviteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add an email address to the meeting's invite_list (host only)."""
    db = get_database()
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if str(meeting["host_id"]) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the host can invite participants")

    await db.meetings.update_one(
        {"_id": meeting["_id"]},
        {"$addToSet": {"invite_list": body.email.lower()}},
    )
    return {"invited": True, "email": body.email.lower()}


class ParticipantInfo(BaseModel):
    id: str
    name: str
    email: str
    is_host: bool


@router.get("/{meeting_id}/participants", response_model=list[ParticipantInfo])
async def list_participants(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all participants in a meeting with their names."""
    db = get_database()
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    user_oid = ObjectId(current_user["id"])
    if user_oid not in meeting.get("participant_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")

    host_id = str(meeting["host_id"])
    participants: list[ParticipantInfo] = []
    for pid in meeting.get("participant_ids", []):
        user = await db.users.find_one({"_id": pid})
        if user:
            participants.append(ParticipantInfo(
                id=str(user["_id"]),
                name=user.get("name", "Unknown"),
                email=user.get("email", ""),
                is_host=str(user["_id"]) == host_id,
            ))
    return participants


@router.delete("/{meeting_id}/participants/{user_id}")
async def remove_participant(
    meeting_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a participant from the meeting (host only)."""
    db = get_database()
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if str(meeting["host_id"]) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the host can remove participants")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    await db.meetings.update_one(
        {"_id": meeting["_id"]},
        {"$pull": {"participant_ids": ObjectId(user_id)}},
    )
    return {"removed": True, "user_id": user_id}


async def admit_participant(
    meeting_id: str,
    user_id: str,
    meeting: dict,
    current_user: dict,
) -> dict:
    """Move a user from the waiting room into participant_ids (host only)."""
    db = get_database()
    meeting_oid = meeting["_id"] if not isinstance(meeting["_id"], str) else ObjectId(meeting["_id"])
    await lobby_manager.remove_from_waiting_room(meeting_id, user_id)
    await db.meetings.update_one(
        {"_id": meeting_oid},
        {"$addToSet": {"participant_ids": user_id}},
    )
    return {"admitted": True, "user_id": user_id, "admitted_by": current_user.get("id")}


async def reject_participant(
    meeting_id: str,
    user_id: str,
    meeting: dict,
) -> dict:
    """Remove a user from the waiting room without admitting them (host only)."""
    await lobby_manager.remove_from_waiting_room(meeting_id, user_id)
    return {"rejected": True, "user_id": user_id}


async def transfer_host(
    meeting_id: str,
    new_host_id: str,
    meeting: dict,
) -> dict:
    """Transfer host role to another participant (host only)."""
    db = get_database()
    meeting_oid = meeting["_id"] if not isinstance(meeting["_id"], str) else ObjectId(meeting["_id"])
    await db.meetings.update_one(
        {"_id": meeting_oid},
        {"$set": {"host_id": new_host_id}},
    )
    return {"transferred": True, "new_host_id": new_host_id}


# ---------------------------------------------------------------------------
# End meeting — triggers async post-processing pipeline
# ---------------------------------------------------------------------------

class EndMeetingResponse(BaseModel):
    meeting_id: str
    state: str
    message: str


@router.post("/{meeting_id}/end", response_model=EndMeetingResponse)
async def end_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    End a meeting and trigger async post-processing.

    Only the host may end the meeting. Returns immediately while
    postprocessing-service runs asynchronously (non-blocking).
    Frontend should listen for meeting.processed WebSocket event.
    """
    import asyncio
    from app.postprocessing import processor

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

    # Only host may end the meeting
    if str(meeting["host_id"]) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting host can end this meeting",
        )

    if meeting["state"] in [MeetingState.ENDED, MeetingState.PROCESSED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting has already ended",
        )

    # Calculate duration if meeting was active
    if meeting.get("started_at"):
        duration = int((datetime.now(timezone.utc) - meeting["started_at"]).total_seconds())
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {"$set": {"duration_seconds": duration}},
        )

    # Trigger async post-processing pipeline — non-blocking (architecture §10)
    asyncio.create_task(processor.run(meeting_id))

    return EndMeetingResponse(
        meeting_id=meeting_id,
        state=MeetingState.ENDED,
        message="Meeting ended. Processing your meeting report...",
    )


# ---------------------------------------------------------------------------
# Action item editing (FR-046)
# ---------------------------------------------------------------------------

class ActionItemResponse(BaseModel):
    id: str
    meeting_id: str
    description: str
    assignee: str | None = None
    deadline: str | None = None
    is_edited: bool
    created_at: datetime


class ActionItemPatch(BaseModel):
    description: str | None = None
    assignee: str | None = None
    deadline: str | None = None


@router.patch("/{meeting_id}/action-items/{item_id}", response_model=ActionItemResponse)
async def patch_action_item(
    meeting_id: str,
    item_id: str,
    body: ActionItemPatch,
    current_user: dict = Depends(get_current_user),
):
    """
    Edit an action item.

    Any authenticated meeting participant (not host-only) may edit (FR-046).
    Only provided fields are updated; others remain unchanged.
    Sets is_edited=True on first manual edit.
    """
    db = get_database()

    try:
        meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid meeting ID")

    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    user_oid = ObjectId(current_user["id"])
    if user_oid not in meeting.get("participant_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only meeting participants can edit action items",
        )

    try:
        action_item = await db.action_items.find_one(
            {"_id": ObjectId(item_id), "meeting_id": meeting_id}
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action item ID")

    if not action_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found")

    # Build update with only provided fields
    update_fields: dict = {"is_edited": True}
    if body.description is not None:
        update_fields["description"] = body.description
    if body.assignee is not None:
        update_fields["assignee"] = body.assignee
    if body.deadline is not None:
        update_fields["deadline"] = body.deadline

    await db.action_items.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": update_fields},
    )

    updated = await db.action_items.find_one({"_id": ObjectId(item_id)})
    return ActionItemResponse(
        id=str(updated["_id"]),
        meeting_id=updated["meeting_id"],
        description=updated["description"],
        assignee=updated.get("assignee"),
        deadline=updated.get("deadline"),
        is_edited=updated.get("is_edited", False),
        created_at=updated["created_at"],
    )


# ---------------------------------------------------------------------------
# POST /meetings/{meeting_id}/ask — Post-meeting Q&A (RAG, FR-053–FR-056)
# ---------------------------------------------------------------------------


class MeetingAskRequest(BaseModel):
    question: str


@router.post("/{meeting_id}/ask")
async def ask_meeting(
    meeting_id: str,
    body: MeetingAskRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Post-meeting Q&A endpoint backed by the unified RAG pipeline.

    - Auth: participant-only (403 for non-participants)
    - Delegates to /ai/qa with rate limiting (RL-003)
    - Returns answer + source attribution
    """
    db = get_database()
    user_id = current_user["id"]

    # Fetch meeting and verify participant access
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    participant_ids = [str(pid) for pid in meeting.get("participant_ids", [])]
    host_id = str(meeting.get("host_id", ""))
    if user_id not in participant_ids and user_id != host_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # Delegate to the /ai/qa handler
    import httpx
    from app.config import get_settings

    settings = get_settings()
    # Internal call to the QA service — reuse the RAG pipeline directly
    from app.rag.retriever import retrieve
    from app.rag.retriever import QA_RATE_LIMIT

    rate_key = {"meeting_id": meeting_id, "user_id": user_id}
    rate_doc = await db.qa_rate_limits.find_one(rate_key)
    current_count = rate_doc["count"] if rate_doc else 0

    if current_count >= QA_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="You have reached the maximum of 20 questions per meeting.",
        )

    await db.qa_rate_limits.update_one(
        rate_key,
        {"$inc": {"count": 1}},
        upsert=True,
    )

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured.")

    chunks = await retrieve(meeting_id, body.question, top_k=5)

    context_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        attr = chunk.get("attribution", {})
        if source == "transcript":
            speaker = attr.get("speaker_name") or "Participant"
            ts = attr.get("timestamp") or ""
            label = f"[Transcript — {speaker}{', ' + ts if ts else ''}]"
        else:
            filename = attr.get("filename") or "document"
            label = f"[Document — {filename}]"
        context_parts.append(f"{i}. {label}\n{text}")

    context_text = "\n\n".join(context_parts) if context_parts else "No relevant context found."
    system_prompt = (
        "You are a helpful meeting assistant. Answer the user's question based solely on "
        "the provided context from meeting transcripts and uploaded documents. "
        "If the context does not contain enough information, say so clearly."
    )
    user_message = f"Context:\n{context_text}\n\nQuestion: {body.question}"

    try:
        import anthropic as _anthropic
        client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        answer = message.content[0].text
    except Exception as exc:
        logger.error("Meeting ask Claude call failed: %s", exc)
        answer = "Sorry, I was unable to generate an answer at this time."

    sources = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        attr = chunk.get("attribution", {})
        if source == "transcript":
            attribution_str = attr.get("speaker_name") or "Participant"
        else:
            attribution_str = attr.get("filename") or "document"
        excerpt = text[:200] + "..." if len(text) > 200 else text
        sources.append({"source": source, "excerpt": excerpt, "attribution": attribution_str})

    return {"answer": answer, "sources": sources}
