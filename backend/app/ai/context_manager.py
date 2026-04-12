"""
Context Manager for AI Response Generation.

Builds the hybrid context payload for Claude: Arni's system persona,
the latest rolling summary, recent transcript turns, and relevant
document chunks via RAG with reranking.
"""

import logging
from typing import Any

import anthropic

from app.config import get_settings
from app.database import get_database

logger = logging.getLogger(__name__)

ARNI_SYSTEM_PROMPT = (
    "You are Arni, a voice AI assistant in a live meeting. "
    "Keep every response to 1-2 sentences maximum. Be direct. "
    "No filler phrases. No introductions. Answer immediately."
)

RERANK_MODEL = "claude-haiku-4-5-20251001"


async def build_context(
    meeting_id: str,
    command: str = "",
    window_size: int | None = None,
    top_k_docs: int = 8,
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

    # Fetch relevant document chunks via hybrid RAG retriever + reranking
    document_context = ""
    rag_scores: list[float] = []
    if command:
        document_context, rag_scores = await _retrieve_document_context(meeting_id, command, top_k_docs)

    return {
        "system": ARNI_SYSTEM_PROMPT,
        "summary": summary_text,
        "turns": turns,
        "recent_turns": turns,
        "document_context": document_context,
        "rag_scores": rag_scores,
    }


async def build_reasoning_context(
    meeting_id: str,
    command: str,
    window_size: int | None = None,
    top_k_docs: int = 8,
) -> dict[str, Any]:
    """Build enriched context for reasoning/recommendation requests."""
    return await build_context(
        meeting_id, command=command,
        window_size=window_size, top_k_docs=top_k_docs,
    )


async def _rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use Claude to rerank retrieved chunks by relevance to the query.

    Sends the query and chunk texts to a fast model, asks it to rank
    them by relevance, and returns chunks in the reranked order.
    Falls back to original order on any failure.
    """
    if len(chunks) <= 1:
        return chunks

    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return chunks

    # Build numbered chunk list for the reranker
    chunk_descriptions = []
    for i, c in enumerate(chunks):
        text = c.get("text", "")[:400]
        chunk_descriptions.append(f"[{i}] {text}")
    numbered_chunks = "\n\n".join(chunk_descriptions)

    rerank_prompt = (
        f"Given this question: \"{query}\"\n\n"
        f"Rank these {len(chunks)} text passages by relevance to the question. "
        "Return ONLY a comma-separated list of passage numbers, most relevant first. "
        "Example: 3,0,2,1\n\n"
        f"{numbered_chunks}"
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=RERANK_MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": rerank_prompt}],
        )
        raw_response = msg.content[0].text.strip()

        # Parse comma-separated indices
        indices = []
        for part in raw_response.replace(" ", "").split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(chunks) and idx not in indices:
                    indices.append(idx)

        # Fill in any missing indices at the end (in case reranker omitted some)
        for i in range(len(chunks)):
            if i not in indices:
                indices.append(i)

        reranked = [chunks[i] for i in indices]
        logger.info("Reranked %d chunks for query=%r → order: %s",
                     len(chunks), query[:60], indices[:8])
        return reranked

    except Exception as exc:
        logger.warning("Reranking failed, using original order: %s", exc)
        return chunks


async def _retrieve_document_context(
    meeting_id: str, query: str, top_k: int = 8,
) -> tuple[str, list[float]]:
    """Retrieve relevant document chunks, rerank, and format for prompt injection.

    Pipeline:
    1. Hybrid retrieval (vector + keyword) via retriever
    2. Claude reranking by relevance
    3. Format with source attribution labels

    Returns:
        Tuple of (formatted context string, list of similarity scores).
        Scores indicate retrieval confidence.
    """
    db = get_database()

    # Try hybrid retriever first
    try:
        from app.rag.retriever import retrieve
        results = await retrieve(meeting_id, query, top_k=top_k)
        if results:
            scores = [r.get("score", 0.0) for r in results]

            # Rerank by relevance to the specific question
            results = await _rerank_chunks(query, results)

            parts = []
            for r in results:
                attr = r.get("attribution", {})
                label = attr.get("filename") or attr.get("speaker_name") or r.get("source", "document")
                chunk_idx = attr.get("chunk_index")
                if chunk_idx is not None:
                    label = f"{label} (section {chunk_idx + 1})"
                text = r.get("text", "")
                if text:
                    parts.append(f"[{label}]: {text}")
            if parts:
                logger.info("RAG retrieved+reranked %d chunks for meeting=%s query=%r",
                            len(parts), meeting_id, query[:80])
                return "\n\n".join(parts), scores
    except Exception as exc:
        logger.warning("RAG hybrid search failed: %s", exc)

    # Fallback: simple scan of all document chunks for this meeting
    try:
        chunk_count = await db.document_chunks.count_documents({"meeting_id": meeting_id})
        if chunk_count == 0:
            logger.info("No document chunks found for meeting=%s", meeting_id)
            return "", []

        doc_cursor = db.document_chunks.find(
            {"meeting_id": meeting_id},
        ).limit(top_k)
        doc_chunks = await doc_cursor.to_list(length=top_k)

        parts = []
        for chunk in doc_chunks:
            name = chunk.get("filename", "Document")
            chunk_idx = chunk.get("chunk_index")
            if chunk_idx is not None:
                name = f"{name} (section {chunk_idx + 1})"
            text = chunk.get("text", "")
            if text:
                parts.append(f"[{name}]: {text}")

        logger.info("Fallback scan retrieved %d chunks (of %d total) for meeting=%s",
                     len(parts), chunk_count, meeting_id)
        # Fallback has no real scores — return 0.5 as a placeholder
        fallback_scores = [0.5] * len(parts) if parts else []
        return "\n\n".join(parts), fallback_scores
    except Exception as exc:
        logger.error("Document chunk fallback failed: %s", exc)

    return "", []
