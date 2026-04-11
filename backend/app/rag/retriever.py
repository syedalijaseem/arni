"""
Unified RAG Retriever — vector search across transcript and document chunks.

Queries both transcript_chunks and document_chunks collections simultaneously,
returning results with source attribution metadata.

SRS refs: FR-053–FR-056, §6 Unified RAG Pipeline, §8.3, §8.5.
"""

import logging
from typing import Any

from app.database import get_database
from app.rag.embedder import embed_texts

logger = logging.getLogger(__name__)

QA_RATE_LIMIT = 20  # RL-003: max 20 queries per meeting per user


async def retrieve(
    meeting_id: str,
    query_text: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Retrieve relevant chunks from both transcript and document collections.

    Args:
        meeting_id: The meeting to search within.
        query_text: The user's question text.
        top_k: Maximum number of results to return per collection.

    Returns:
        List of result dicts, each containing:
        - source: "transcript" or "document"
        - text: The chunk text
        - score: Cosine similarity score
        - attribution: Dict with speaker/timestamp (transcript) or filename/chunk_index (document)
    """
    db = get_database()

    # Generate query embedding
    query_embeddings = await embed_texts([query_text])
    query_vector = query_embeddings[0]

    results: list[dict[str, Any]] = []

    # Vector search pipeline for MongoDB Atlas Vector Search
    # Falls back to simple filter if Atlas Vector Search index not configured
    vector_pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": top_k * 10,
                "limit": top_k,
                "filter": {"meeting_id": meeting_id},
            }
        },
        {
            "$addFields": {
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    # Search transcript chunks
    try:
        async for doc in db.transcript_chunks.aggregate(vector_pipeline):
            results.append({
                "source": doc.get("source", "transcript"),
                "text": doc.get("text", ""),
                "score": doc.get("score", 0.0),
                "attribution": {
                    "speaker_name": doc.get("speaker_name"),
                    "timestamp": doc.get("timestamp"),
                },
            })
    except Exception as exc:
        logger.warning("Transcript chunk search failed: %s — falling back", exc)
        # Fallback: simple text scan (no vector search)
        async for doc in db.transcript_chunks.aggregate([
            {"$match": {"meeting_id": meeting_id}},
            {"$limit": top_k},
        ]):
            results.append({
                "source": doc.get("source", "transcript"),
                "text": doc.get("text", ""),
                "score": 0.5,
                "attribution": {
                    "speaker_name": doc.get("speaker_name"),
                    "timestamp": doc.get("timestamp"),
                },
            })

    # Search document chunks
    try:
        async for doc in db.document_chunks.aggregate(vector_pipeline):
            results.append({
                "source": doc.get("source", "document"),
                "text": doc.get("text", ""),
                "score": doc.get("score", 0.0),
                "attribution": {
                    "filename": doc.get("filename"),
                    "chunk_index": doc.get("chunk_index"),
                },
            })
    except Exception as exc:
        logger.warning("Document chunk search failed: %s — falling back", exc)
        async for doc in db.document_chunks.aggregate([
            {"$match": {"meeting_id": meeting_id}},
            {"$limit": top_k},
        ]):
            results.append({
                "source": doc.get("source", "document"),
                "text": doc.get("text", ""),
                "score": 0.5,
                "attribution": {
                    "filename": doc.get("filename"),
                    "chunk_index": doc.get("chunk_index"),
                },
            })

    # Sort combined results by score descending
    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return results[:top_k]
