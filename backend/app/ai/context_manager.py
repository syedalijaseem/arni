"""
Context Manager for AI Response Generation.

Builds the hybrid context payload for Claude: Arni's system persona,
the latest rolling summary, recent transcript turns, and relevant
document chunks via RAG.
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
    command: str = "",
    window_size: int | None = None,
    top_k_docs: int = 5,
) -> dict[str, Any]:
    """
    Build the full context payload for a single AI request.

    Always includes document context via RAG retrieval when a command
    is provided. This ensures Arni can reference uploaded documents
    regardless of whether the question is classified as "reasoning".
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

    # Fetch last N final transcript turns
    cursor = db.transcripts.find(
        {"meeting_id": meeting_id, "is_final": True}
    ).sort("timestamp", -1)
    raw_turns = await cursor.to_list(length=window_size)
    raw_turns = raw_turns[:window_size]
    raw_turns.reverse()

    turns = [
        {
            "speaker_name": t.get("speaker_name") or t.get("speaker_id", "Unknown"),
            "text": t["text"],
        }
        for t in raw_turns
    ]

    # Fetch relevant document chunks via RAG retriever
    document_context = ""
    if command:
        document_context = await _retrieve_document_context(meeting_id, command, top_k_docs)

    return {
        "system": ARNI_SYSTEM_PROMPT,
        "summary": summary_text,
        "turns": turns,
        "recent_turns": turns,
        "document_context": document_context,
    }


async def build_reasoning_context(
    meeting_id: str,
    command: str,
    window_size: int | None = None,
    top_k_docs: int = 5,
) -> dict[str, Any]:
    """Build enriched context for reasoning/recommendation requests."""
    return await build_context(
        meeting_id, command=command,
        window_size=window_size, top_k_docs=top_k_docs,
    )


async def _retrieve_document_context(
    meeting_id: str, query: str, top_k: int = 5,
) -> str:
    """Use the RAG retriever to fetch relevant document chunks.

    Falls back to a simple MongoDB scan if the retriever fails
    (e.g. embeddings API unavailable or vector index not configured).
    """
    # Try the proper vector-search retriever first
    try:
        from app.rag.retriever import retrieve
        results = await retrieve(meeting_id, query, top_k=top_k)
        if results:
            parts = []
            for r in results:
                source = r.get("source", "document")
                attr = r.get("attribution", {})
                label = attr.get("filename") or attr.get("speaker_name") or source
                text = r.get("text", "")
                if text:
                    parts.append(f"[{label}]: {text}")
            if parts:
                return "\n".join(parts)
    except Exception as exc:
        logger.warning("RAG retriever failed, falling back to simple scan: %s", exc)

    # Fallback: grab first N chunks for this meeting from document_chunks
    try:
        db = get_database()
        doc_cursor = db.document_chunks.find({"meeting_id": meeting_id})
        doc_chunks = await doc_cursor.to_list(length=top_k)
        if doc_chunks:
            parts = []
            for chunk in doc_chunks:
                name = chunk.get("filename", "Document")
                text = chunk.get("text", "")
                if text:
                    parts.append(f"[{name}]: {text}")
            return "\n".join(parts)
    except Exception as exc:
        logger.error("Document chunk fallback also failed: %s", exc)

    return ""
