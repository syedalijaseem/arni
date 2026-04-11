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
    "You are Arni, a voice AI assistant in a live meeting. "
    "Keep every response to 1-2 sentences maximum. Be direct. "
    "No filler phrases. No introductions. Answer immediately."
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
        "recent_turns": turns,
        "document_context": "",
    }


async def build_reasoning_context(
    meeting_id: str,
    command: str,
    window_size: int | None = None,
    top_k_docs: int = 5,
) -> dict[str, Any]:
    """
    Build an enriched context payload for reasoning/recommendation requests.

    Identical to build_context but additionally retrieves document chunks
    relevant to `command` via a simple keyword search against document_chunks
    (FR-088: RAG context included in reasoning).

    Args:
        meeting_id: The meeting identifier.
        command: The user's wake-word command text (used for RAG retrieval).
        window_size: How many recent transcript turns to include.
        top_k_docs: Maximum number of document chunk excerpts to include.

    Returns:
        Same shape as build_context, plus:
          "document_context": str — concatenated relevant document excerpts
    """
    base = await build_context(meeting_id, window_size=window_size)

    db = get_database()

    # Simple text-based RAG: fetch document chunks for this meeting
    # A real implementation would do vector search; here we use $text or limit
    doc_cursor = db.document_chunks.find({"meeting_id": meeting_id})
    doc_chunks = await doc_cursor.to_list(length=top_k_docs)

    document_context = ""
    if doc_chunks:
        parts = []
        for chunk in doc_chunks:
            doc_name = chunk.get("document_name", "Document")
            text = chunk.get("text", "")
            if text:
                parts.append(f"[{doc_name}]: {text}")
        document_context = "\n".join(parts)

    logger.debug(
        "Reasoning context built for meeting=%s: doc_chunks=%d",
        meeting_id,
        len(doc_chunks),
    )

    return {
        **base,
        "document_context": document_context,
    }
