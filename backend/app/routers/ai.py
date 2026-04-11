"""
AI Router — exposes /ai/respond endpoint.

POST /ai/respond:
  Accepts a wake-word command, builds context, enqueues for AI processing,
  and returns the response text immediately (synchronous call for MVP).

Rate limit and cooldown enforcement happens inside MeetingQueue.
"""

import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.ai.context_manager import build_context
from app.ai.ai_service import ai_respond, ai_summarize
from app.ai.response_queue import get_or_create_queue, RATE_LIMIT_SENTINEL
from app.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter()

RATE_LIMIT_MESSAGE = (
    "Arni has reached the maximum number of responses for this meeting. "
    "Please continue the conversation manually."
)

COOLDOWN_MESSAGE = (
    "Arni is still processing the previous request. "
    "Please wait a moment before asking again."
)


class AIRespondRequest(BaseModel):
    meeting_id: str
    command: str
    speaker_id: str


class AIRespondResponse(BaseModel):
    response_text: str
    request_id: str | None = None


class AISummarizeRequest(BaseModel):
    meeting_id: str


class AISummarizeResponse(BaseModel):
    summary_text: str | None = None
    skipped: bool = False


@router.post("/respond", response_model=AIRespondResponse)
async def respond(body: AIRespondRequest) -> AIRespondResponse:
    """
    Process a wake-word command and return an AI response.

    Steps:
      1. Check rate limit and cooldown via MeetingQueue.enqueue().
      2. Build hybrid context (rolling summary + recent turns).
      3. Call Claude Sonnet via ai_respond().
      4. Return the response text.
    """
    queue = get_or_create_queue(body.meeting_id)

    request_id = await queue.enqueue(
        body.meeting_id,
        body.command,
        body.speaker_id,
    )

    if request_id == RATE_LIMIT_SENTINEL:
        return AIRespondResponse(
            response_text=RATE_LIMIT_MESSAGE,
            request_id=None,
        )

    if request_id is None:
        return AIRespondResponse(
            response_text=COOLDOWN_MESSAGE,
            request_id=None,
        )

    # Increment response count to keep queue state consistent.
    # For the REST endpoint we call ai_respond directly (no async drain needed).
    context = await build_context(body.meeting_id)
    result = await ai_respond(body.meeting_id, body.command, context)

    # Drain the enqueued placeholder so the queue stays clean
    if not queue._queue.empty():
        try:
            queue._queue.get_nowait()
            queue._queue.task_done()
        except Exception:
            pass

    queue._response_count += 1

    return AIRespondResponse(
        response_text=result["response_text"],
        request_id=request_id,
    )


@router.post("/summarize", response_model=AISummarizeResponse)
async def summarize(body: AISummarizeRequest) -> AISummarizeResponse:
    """
    Generate a rolling meeting summary.

    Steps:
      1. Fetch all final transcript turns for the meeting.
      2. If none exist: return skipped=True (no work to do).
      3. Fetch the most recent stored summary (may be empty).
      4. Call ai_summarize() to produce an updated summary.
      5. Store the new MeetingSummary document in MongoDB.
      6. Return the new summary text.
    """
    import datetime

    db = get_database()

    # Fetch all final transcripts for the meeting
    cursor = db.transcripts.find(
        {"meeting_id": body.meeting_id, "is_final": True}
    ).sort("timestamp", 1)
    turns = await cursor.to_list(length=None)

    if not turns:
        return AISummarizeResponse(skipped=True)

    # Fetch the latest existing summary
    summary_doc = await db.meeting_summaries.find_one(
        {"meeting_id": body.meeting_id},
        sort=[("updated_at", -1)],
    )
    previous_summary = summary_doc["summary_text"] if summary_doc else ""

    # Build turns list for summarisation
    turn_dicts = [
        {
            "speaker_name": t.get("speaker_name") or t.get("speaker_id", "Participant"),
            "text": t["text"],
        }
        for t in turns
    ]

    summary_text = await ai_summarize(body.meeting_id, previous_summary, turn_dicts)

    # Persist new summary
    now = datetime.datetime.now(datetime.timezone.utc)
    await db.meeting_summaries.insert_one({
        "meeting_id": body.meeting_id,
        "summary_text": summary_text,
        "updated_at": now,
    })

    logger.info("Rolling summary stored for meeting=%s", body.meeting_id)

    return AISummarizeResponse(summary_text=summary_text, skipped=False)
