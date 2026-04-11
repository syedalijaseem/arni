"""
AI Router — exposes /ai/respond endpoint.

POST /ai/respond:
  Accepts a wake-word command, builds context, enqueues for AI processing,
  and returns the response text immediately (synchronous call for MVP).

Rate limit and cooldown enforcement happens inside MeetingQueue.
"""

import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from app.ai.context_manager import build_context
from app.ai.ai_service import ai_respond, ai_summarize
from app.ai.response_queue import get_or_create_queue, RATE_LIMIT_SENTINEL
from app.ai.fact_checker import fact_checker
from app.database import get_database
from app.tts.elevenlabs_client import text_to_speech
from app.tts.audio_injection import inject_audio

logger = logging.getLogger(__name__)

router = APIRouter()

QA_RATE_LIMIT = 20  # RL-003: max 20 queries per meeting per user
QA_RATE_LIMIT_MESSAGE = (
    "You have reached the maximum of 20 questions per meeting. "
    "No further questions can be answered for this meeting."
)

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


@router.post("/push-to-talk")
async def push_to_talk(
    meeting_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """Push-to-talk: transcribe audio clip, send to Claude, return TTS audio.

    Accepts a recorded audio blob from the frontend, transcribes it via
    Deepgram, builds meeting context, calls Claude, synthesises TTS,
    and injects the audio into the Daily.co meeting.
    """
    from app.config import get_settings
    from deepgram import DeepgramClient, PrerecordedOptions

    settings = get_settings()
    audio_bytes = await audio.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    # 1. Transcribe the audio clip via Deepgram
    try:
        dg = DeepgramClient(settings.DEEPGRAM_API_KEY)
        response = await dg.listen.asyncrest.v("1").transcribe_file(
            {"buffer": audio_bytes, "mimetype": audio.content_type or "audio/webm"},
            PrerecordedOptions(model="nova-2", smart_format=True, punctuate=True),
        )
        transcript = response.results.channels[0].alternatives[0].transcript
    except Exception as exc:
        logger.error("Push-to-talk transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcript or not transcript.strip():
        return {"response_text": "", "transcript": ""}

    # 2. Build context (with RAG document retrieval) and call Claude
    context = await build_context(meeting_id, command=transcript)
    result = await ai_respond(meeting_id, transcript, context)
    response_text = result.get("response_text", "")

    # 3. TTS and inject into meeting
    if response_text:
        tts_audio = await text_to_speech(response_text)
        if tts_audio:
            await inject_audio(tts_audio, meeting_id)

    return {"response_text": response_text, "transcript": transcript}


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
    context = await build_context(body.meeting_id, command=body.command)
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


class AITimelineRequest(BaseModel):
    meeting_id: str
    transcript_text: str


class AITimelineItem(BaseModel):
    timestamp: str
    topic: str


class AITimelineResponse(BaseModel):
    timeline: list[AITimelineItem]


@router.post("/timeline", response_model=AITimelineResponse)
async def generate_timeline(body: AITimelineRequest) -> AITimelineResponse:
    """
    Generate a timestamped topic segmentation timeline from a meeting transcript.

    Returns a JSON array of {timestamp, topic} objects sorted chronologically.
    SRS ref: FR-047.
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
        "Segment this meeting transcript into topics with timestamps. "
        "Return a JSON array of objects with keys: timestamp (string, e.g. '00:00'), topic (string). "
        "If no clear timestamps exist in the transcript, estimate based on transcript position. "
        "Return at least one segment."
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
        timeline = [
            AITimelineItem(
                timestamp=str(item.get("timestamp") or "00:00"),
                topic=str(item.get("topic") or ""),
            )
            for item in items
            if isinstance(item, dict)
        ]
    except Exception as exc:
        logger.error("timeline generation error: %s", exc)
        timeline = []

    return AITimelineResponse(timeline=timeline)


class AIQARequest(BaseModel):
    meeting_id: str
    question: str
    user_id: str


class AIQASource(BaseModel):
    source: str
    excerpt: str
    attribution: str


class AIQAResponse(BaseModel):
    answer: str
    sources: list[AIQASource]


@router.post("/qa", response_model=AIQAResponse)
async def qa(body: AIQARequest) -> AIQAResponse:
    """
    Post-meeting Q&A using unified RAG across transcript and document chunks.

    - Enforces RL-003: max 20 queries per meeting per user (429 on exceed)
    - Retrieves top-k chunks from both transcript_chunks and document_chunks
    - Generates an answer with full source attribution via Claude
    """
    from app.config import get_settings as _get_settings
    from app.rag.retriever import retrieve

    db = get_database()
    settings = _get_settings()

    # Check and increment rate limit counter (RL-003)
    rate_key = {"meeting_id": body.meeting_id, "user_id": body.user_id}
    rate_doc = await db.qa_rate_limits.find_one(rate_key)
    current_count = rate_doc["count"] if rate_doc else 0

    if current_count >= QA_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=QA_RATE_LIMIT_MESSAGE,
        )

    # Increment counter
    await db.qa_rate_limits.update_one(
        rate_key,
        {"$inc": {"count": 1}},
        upsert=True,
    )

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured",
        )

    # Retrieve relevant chunks
    chunks = await retrieve(body.meeting_id, body.question, top_k=5)

    # Build context from retrieved chunks with source labels
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
            chunk_idx = attr.get("chunk_index", 0)
            label = f"[Document — {filename}, chunk {chunk_idx}]"

        context_parts.append(f"{i}. {label}\n{text}")

    context_text = "\n\n".join(context_parts) if context_parts else "No relevant context found."

    system_prompt = (
        "You are a helpful meeting assistant. Answer the user's question based solely on "
        "the provided context from meeting transcripts and uploaded documents. "
        "When citing information, specify whether it came from the transcript or a document. "
        "If the context does not contain enough information to answer, say so clearly."
    )
    user_message = (
        f"Context:\n{context_text}\n\n"
        f"Question: {body.question}"
    )

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
        logger.error("QA Claude call failed: %s", exc)
        answer = "Sorry, I was unable to generate an answer at this time."

    # Build source attribution list
    sources: list[AIQASource] = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "")
        attr = chunk.get("attribution", {})

        if source == "transcript":
            speaker = attr.get("speaker_name") or "Participant"
            ts = attr.get("timestamp") or ""
            attribution_str = f"{speaker}{', ' + ts if ts else ''}"
        else:
            filename = attr.get("filename") or "document"
            chunk_idx = attr.get("chunk_index", 0)
            attribution_str = f"{filename} (chunk {chunk_idx})"

        excerpt = text[:200] + "..." if len(text) > 200 else text
        sources.append(AIQASource(
            source=source,
            excerpt=excerpt,
            attribution=attribution_str,
        ))

    return AIQAResponse(answer=answer, sources=sources)


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
