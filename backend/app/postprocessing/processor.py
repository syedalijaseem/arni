"""
Post-meeting processing pipeline.

Orchestrates async post-processing after a meeting ends:
  1. Set meeting state → Ended
  2. Fetch full transcript
  3. Generate title + summary
  4. Extract decisions (explicit only)
  5. Extract action items (explicit only)
  6. Set meeting state → Processed
  7. Publish meeting.processed event

Architecture ref: §4 Post-Meeting Processing Pipeline, §10 Sequence Diagram.
SRS ref: FR-041–FR-045, NFR-003 (60-second SLA).
"""

import asyncio
import datetime
import logging
import time
from typing import Any

from bson import ObjectId

from app.config import get_settings
from app.database import get_database, get_redis
from app.events.publisher import publish_meeting_processed, publish_meeting_ended
from app.models.meeting import MeetingState

logger = logging.getLogger(__name__)

settings = get_settings()

EXTRACT_DECISIONS_SYSTEM_PROMPT = (
    "Extract decisions ONLY if explicitly stated in the transcript. "
    "Do not infer. Return a JSON array of strings. "
    "If there are no explicit decisions, return an empty array []."
)

EXTRACT_ACTIONS_SYSTEM_PROMPT = (
    "Extract action items ONLY from explicit commitments or assignments stated in the transcript. "
    "Do not infer tasks. "
    "Return a JSON array of objects with keys: description, assignee, deadline. "
    "Use null for assignee/deadline when not stated. "
    "If there are no explicit action items, return an empty array []."
)

GENERATE_TITLE_SYSTEM_PROMPT = (
    "You are a meeting assistant. Given a meeting transcript, generate a concise, "
    "descriptive title (max 10 words) and a 2-3 sentence summary. "
    "Return JSON with keys: title, summary."
)


def _build_transcript_text(turns: list[dict]) -> str:
    """Format transcript turns as plain text for LLM prompts."""
    return "\n".join(
        f"{t.get('speaker_name') or t.get('speaker_id', 'Participant')}: {t['text']}"
        for t in turns
    )


async def _call_claude(system_prompt: str, user_message: str) -> str | None:
    """
    Make a single Claude API call and return response text.
    Returns None on any error.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — cannot run post-processing")
        return None

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text
    except Exception as exc:
        logger.error("Claude API error in post-processing: %s", exc)
        return None


def _parse_json_list(raw: str | None, default: list) -> list:
    """Parse a JSON array from LLM output, returning default on failure."""
    if not raw:
        return default
    import json
    try:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
    except Exception as exc:
        logger.warning("Failed to parse JSON from LLM output: %s — raw: %.200s", exc, raw)
        return default


def _parse_json_object(raw: str | None, default: dict) -> dict:
    """Parse a JSON object from LLM output, returning default on failure."""
    if not raw:
        return default
    import json
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)
    except Exception as exc:
        logger.warning("Failed to parse JSON object from LLM output: %s — raw: %.200s", exc, raw)
        return default


async def run(meeting_id: str) -> None:
    """
    Run the full post-meeting processing pipeline asynchronously.

    Must complete within 60 seconds (NFR-003).
    Updates meeting state in MongoDB and publishes meeting.processed event.
    """
    start_time = time.monotonic()
    db = get_database()

    logger.info("Post-processing started for meeting=%s", meeting_id)

    try:
        # Step 1: Set meeting state to Ended
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {"$set": {"state": MeetingState.ENDED, "ended_at": datetime.datetime.now(datetime.timezone.utc)}},
        )

        # Step 2: Fetch full transcript
        cursor = db.transcripts.find(
            {"meeting_id": meeting_id, "is_final": True}
        ).sort("timestamp", 1)
        turns = await cursor.to_list(length=None)

        if not turns:
            logger.warning("No transcript turns found for meeting=%s — skipping AI extraction", meeting_id)
            transcript_text = ""
        else:
            transcript_text = _build_transcript_text(turns)

        # Step 3: Generate title + summary
        title = "Meeting Summary"
        summary = ""
        if transcript_text:
            raw_title_summary = await _call_claude(
                GENERATE_TITLE_SYSTEM_PROMPT,
                f"Transcript:\n{transcript_text}",
            )
            title_summary = _parse_json_object(raw_title_summary, {})
            title = title_summary.get("title") or "Meeting Summary"
            summary = title_summary.get("summary") or ""

        # Step 4: Extract decisions (explicit only, FR-042)
        decisions: list[str] = []
        if transcript_text:
            raw_decisions = await _call_claude(
                EXTRACT_DECISIONS_SYSTEM_PROMPT,
                f"Transcript:\n{transcript_text}",
            )
            decisions = _parse_json_list(raw_decisions, [])
            if not isinstance(decisions, list):
                decisions = []
            # Ensure all items are strings
            decisions = [str(d) for d in decisions if d]

        # Step 5: Extract action items (explicit only, FR-043)
        action_item_ids: list[Any] = []
        if transcript_text:
            raw_actions = await _call_claude(
                EXTRACT_ACTIONS_SYSTEM_PROMPT,
                f"Transcript:\n{transcript_text}",
            )
            action_dicts = _parse_json_list(raw_actions, [])
            if not isinstance(action_dicts, list):
                action_dicts = []

            now = datetime.datetime.now(datetime.timezone.utc)
            for item in action_dicts:
                if not isinstance(item, dict):
                    continue
                doc = {
                    "meeting_id": meeting_id,
                    "description": str(item.get("description") or ""),
                    "assignee": item.get("assignee"),
                    "deadline": item.get("deadline"),
                    "is_edited": False,
                    "created_at": now,
                }
                result = await db.action_items.insert_one(doc)
                action_item_ids.append(result.inserted_id)

        # Store summary, title, decisions, action item IDs on Meeting
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {
                "$set": {
                    "title": title,
                    "summary": summary,
                    "decisions": decisions,
                    "action_item_ids": action_item_ids,
                }
            },
        )

        # Step 6: Set meeting state to Processed
        await db.meetings.update_one(
            {"_id": ObjectId(meeting_id)},
            {"$set": {"state": MeetingState.PROCESSED}},
        )

        elapsed = time.monotonic() - start_time
        logger.info(
            "Post-processing complete for meeting=%s in %.1fs — title=%r decisions=%d actions=%d",
            meeting_id,
            elapsed,
            title,
            len(decisions),
            len(action_item_ids),
        )

        if elapsed > 60:
            logger.warning(
                "NFR-003 SLA exceeded for meeting=%s: %.1fs > 60s",
                meeting_id,
                elapsed,
            )

        # Step 7: Publish meeting.processed event
        import time as _time
        redis = get_redis()
        await publish_meeting_processed(
            redis,
            meeting_id=meeting_id,
            timestamp=_time.time(),
        )

    except Exception as exc:
        logger.error("Post-processing failed for meeting=%s: %s", meeting_id, exc)
        # Attempt to mark meeting as Ended even on failure so it doesn't stay Active
        try:
            await db.meetings.update_one(
                {"_id": ObjectId(meeting_id)},
                {"$set": {"state": MeetingState.ENDED}},
            )
        except Exception:
            pass
