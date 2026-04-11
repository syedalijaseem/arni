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
from app.ai.fact_checker import fact_checker
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


class AIFactCheckRequest(BaseModel):
    meeting_id: str
    transcript_text: str
    speaker_id: str


class AIFactCheckResponse(BaseModel):
    contradicts: bool
    confidence: float | None = None
    correction_text: str | None = None
    source_document: str | None = None
    source_excerpt: str | None = None


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


class AIExtractDecisionsRequest(BaseModel):
    meeting_id: str
    transcript_text: str


class AIExtractDecisionsResponse(BaseModel):
    decisions: list[str]


class AIExtractActionsRequest(BaseModel):
    meeting_id: str
    transcript_text: str


class AIExtractActionsItem(BaseModel):
    description: str
    assignee: str | None = None
    deadline: str | None = None


class AIExtractActionsResponse(BaseModel):
    action_items: list[AIExtractActionsItem]


@router.post("/extract-decisions", response_model=AIExtractDecisionsResponse)
async def extract_decisions(body: AIExtractDecisionsRequest) -> AIExtractDecisionsResponse:
    """
    Extract decisions from a meeting transcript.

    Only explicitly stated decisions are returned — no inference (FR-042).
    Returns an empty list when no explicit decisions exist.
    """
    import json
    from app.config import get_settings as _get_settings
    import anthropic as _anthropic

    settings = _get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )

    system_prompt = (
        "Extract decisions ONLY if explicitly stated in the transcript. "
        "Do not infer. Return a JSON array of strings. "
        "If there are no explicit decisions, return an empty array []."
    )

    try:
        client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Transcript:\n{body.transcript_text}"}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```"))
        decisions = json.loads(raw)
        if not isinstance(decisions, list):
            decisions = []
        decisions = [str(d) for d in decisions if d]
    except Exception as exc:
        logger.error("extract-decisions error: %s", exc)
        decisions = []

    return AIExtractDecisionsResponse(decisions=decisions)


@router.post("/extract-actions", response_model=AIExtractActionsResponse)
async def extract_actions(body: AIExtractActionsRequest) -> AIExtractActionsResponse:
    """
    Extract action items from a meeting transcript.

    Only items from explicit commitments or assignments are returned (FR-043).
    Returns an empty list when no explicit action items exist.
    """
    import json
    from app.config import get_settings as _get_settings
    import anthropic as _anthropic

    settings = _get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )

    system_prompt = (
        "Extract action items ONLY from explicit commitments or assignments stated in the transcript. "
        "Do not infer tasks. "
        "Return a JSON array of objects with keys: description, assignee, deadline. "
        "Use null for assignee/deadline when not stated. "
        "If there are no explicit action items, return an empty array []."
    )

    try:
        client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Transcript:\n{body.transcript_text}"}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```"))
        items = json.loads(raw)
        if not isinstance(items, list):
            items = []
        action_items = [
            AIExtractActionsItem(
                description=str(item.get("description") or ""),
                assignee=item.get("assignee"),
                deadline=item.get("deadline"),
            )
            for item in items
            if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.error("extract-actions error: %s", exc)
        action_items = []

    return AIExtractActionsResponse(action_items=action_items)


@router.post("/fact-check", response_model=AIFactCheckResponse)
async def fact_check(body: AIFactCheckRequest) -> AIFactCheckResponse:
    """
    Run a proactive fact-check pass for a single transcript turn.

    Steps:
      1. Call FactChecker.check() with the transcript text.
      2. If a contradiction above confidence threshold is found, return it.
      3. If no contradiction (or check skipped), return contradicts=False.
    """
    result = await fact_checker.check(
        meeting_id=body.meeting_id,
        speaker_id=body.speaker_id,
        transcript_text=body.transcript_text,
    )

    if result is None:
        return AIFactCheckResponse(contradicts=False)

    return AIFactCheckResponse(
        contradicts=result.get("contradicts", False),
        confidence=result.get("confidence"),
        correction_text=result.get("correction_text"),
        source_document=result.get("source_document"),
        source_excerpt=result.get("source_excerpt"),
    )
