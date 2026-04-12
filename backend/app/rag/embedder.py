"""
Transcript Embedder — post-meeting transcript chunk embedding.

After a meeting ends, embed all final transcript turns into vector chunks
stored in the `transcript_chunks` collection for unified RAG retrieval.

SRS refs: FR-045, §8.3 Transcript Chunk model, §4.4 RAG Chunking Spec.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.database import get_database

logger = logging.getLogger(__name__)

# Re-export embed_texts so tests and retriever can patch it from this module
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of text strings via OpenAI text-embedding-3-large.

    Returns one embedding vector per input text.
    """
    from openai import AsyncOpenAI
    from app.config import get_settings

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
    )
    return [item.embedding for item in response.data]


def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 100) -> list[str]:
    """Split text into overlapping token windows (200-400 tokens, 100-token overlap)."""
    from app.documents.chunker import chunk as _chunk
    return _chunk(text, chunk_size_tokens=chunk_size, overlap_tokens=overlap)


async def embed_transcript(meeting_id: str) -> None:
    """
    Embed all final transcript turns for a meeting into the transcript_chunks collection.

    Idempotent: if chunks already exist for this meeting, skip without re-embedding.

    Steps:
    1. Check if transcript_chunks already exist for this meeting (idempotency guard)
    2. Fetch all final transcript turns
    3. Concatenate turns into a single text block preserving speaker attribution
    4. Chunk into 300-token windows with 50-token overlap
    5. Embed all chunks in a single batch call
    6. Store TranscriptChunk documents in MongoDB
    """
    db = get_database()

    # Idempotency guard: skip if already embedded
    existing_count = await db.transcript_chunks.count_documents(
        {"meeting_id": meeting_id}
    )
    if existing_count > 0:
        logger.info(
            "Transcript already embedded for meeting=%s (%d chunks), skipping",
            meeting_id,
            existing_count,
        )
        return

    # Fetch all final transcript turns sorted by timestamp
    cursor = db.transcripts.find(
        {"meeting_id": meeting_id, "is_final": True}
    ).sort("timestamp", 1)
    turns: list[dict] = await cursor.to_list(length=None)

    if not turns:
        logger.warning("No final transcript turns found for meeting=%s", meeting_id)
        return

    # Build full transcript text with speaker labels
    full_text = "\n".join(
        f"{t.get('speaker_name') or t.get('speaker_id', 'Participant')}: {t['text']}"
        for t in turns
    )

    # Chunk the transcript
    chunks = _chunk_text(full_text)
    if not chunks:
        logger.warning("No chunks produced for meeting=%s", meeting_id)
        return

    # Embed all chunks in one batch
    embeddings = await embed_texts(chunks)

    # Store transcript chunks
    now = datetime.now(timezone.utc)
    chunk_docs: list[dict[str, Any]] = [
        {
            "meeting_id": meeting_id,
            "chunk_index": i,
            "text": chunk,
            "embedding": embedding,
            "source": "transcript",
            # Attribution metadata: store the speaker context for the chunk
            "speaker_name": None,   # Chunk may span multiple speakers
            "timestamp": None,      # Could be enhanced to track start time
            "created_at": now,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    if chunk_docs:
        await db.transcript_chunks.insert_many(chunk_docs)
        logger.info(
            "Embedded %d transcript chunks for meeting=%s",
            len(chunk_docs),
            meeting_id,
        )
