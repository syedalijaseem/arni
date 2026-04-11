"""
Context Manager for AI Response Generation.

Builds the hybrid context payload for Claude: Arni's system persona,
the latest rolling summary, and the last N transcript turns.

Design:
- Rolling summary is fetched from MongoDB (meeting_summaries collection).
- Transcript turns are the most recent `window_size` final transcripts.
- All fields are returned as a plain dict to avoid coupling to Pydantic.
"""

import logging
from typing import Any

from app.config import get_settings
from app.database import get_database

logger = logging.getLogger(__name__)

ARNI_SYSTEM_PROMPT = (
    "You are Arni, an AI meeting assistant. "
    "You are participating in a live meeting as a helpful, knowledgeable colleague. "
    "Answer questions concisely and conversationally. "
    "Prioritise accuracy. If you are uncertain, say so. "
    "Never fabricate facts or make up numbers. "
    "Keep responses under 100 words unless the question specifically requires detail."
)


async def build_context(
    meeting_id: str,
    window_size: int | None = None,
) -> dict[str, Any]:
    """
    Build the context payload for a single AI request.

    Args:
        meeting_id: The meeting identifier.
        window_size: How many recent transcript turns to include.
                     Defaults to AI_CONTEXT_WINDOW from settings.

    Returns:
        {
            "system":  str   — Arni system persona,
            "summary": str   — latest rolling summary (empty string if none),
            "turns":   list  — recent transcript turns [{speaker_name, text}],
        }
    """
    settings = get_settings()
    if window_size is None:
        window_size = settings.AI_CONTEXT_WINDOW

    db = get_database()

    # Fetch latest rolling summary
    summary_doc = await db.meeting_summaries.find_one(
        {"meeting_id": meeting_id},
        sort=[("updated_at", -1)],
    )
    summary_text: str = ""
    if summary_doc and summary_doc.get("summary_text"):
        summary_text = summary_doc["summary_text"]

    # Fetch last `window_size` final transcript turns
    cursor = db.transcripts.find(
        {"meeting_id": meeting_id, "is_final": True}
    ).sort("timestamp", -1)
    raw_turns = await cursor.to_list(length=window_size)

    # Enforce window size defensively (mock/driver may not honour length param)
    raw_turns = raw_turns[:window_size]

    # Reverse so they are chronological (oldest first)
    raw_turns.reverse()

    turns = [
        {
            "speaker_name": t.get("speaker_name") or t.get("speaker_id", "Unknown"),
            "text": t["text"],
        }
        for t in raw_turns
    ]

    logger.debug(
        "Context built for meeting=%s: summary_len=%d, turns=%d",
        meeting_id,
        len(summary_text),
        len(turns),
    )

    return {
        "system": ARNI_SYSTEM_PROMPT,
        "summary": summary_text,
        "turns": turns,
    }
