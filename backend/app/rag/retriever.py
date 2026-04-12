"""
Unified RAG Retriever — hybrid search across transcript and document chunks.

Combines vector similarity search with keyword search for high-precision
retrieval. Results are merged, deduplicated, and ranked by combined score.

SRS refs: FR-053–FR-056, §6 Unified RAG Pipeline, §8.3, §8.5.
"""

import logging
import re
from typing import Any

from app.database import get_database
from app.rag.embedder import embed_texts

logger = logging.getLogger(__name__)

QA_RATE_LIMIT = 20  # RL-003: max 20 queries per meeting per user

# Stop words excluded from keyword extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "am", "i", "me",
    "my", "we", "our", "you", "your", "he", "she", "it", "they", "them",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "how", "when", "where", "why", "if", "then", "than", "but", "and",
    "or", "not", "no", "so", "too", "very", "just", "about", "above",
    "after", "again", "all", "also", "any", "as", "at", "because",
    "before", "between", "both", "by", "each", "for", "from", "get",
    "got", "in", "into", "of", "off", "on", "only", "other", "out",
    "over", "own", "same", "some", "such", "to", "up", "with",
    "arni", "tell", "please", "know", "think", "say", "said",
})

_WORD_RE = re.compile(r"[a-zA-Z0-9]+(?:\.[0-9]+)?")


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful search terms from a query, removing stop words."""
    tokens = _WORD_RE.findall(query.lower())
    keywords = [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]
    return keywords


async def _vector_search(
    collection,
    meeting_id: str,
    query_vector: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """Run MongoDB Atlas Vector Search on a single collection."""
    pipeline = [
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
    results = []
    try:
        async for doc in collection.aggregate(pipeline):
            results.append(doc)
    except Exception as exc:
        logger.warning("Vector search failed on %s: %s", collection.name, exc)
    return results


async def _keyword_search(
    collection,
    meeting_id: str,
    keywords: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    """Search for chunks containing query keywords via regex matching.

    Scores each chunk by the fraction of keywords it contains.
    This catches exact terms (model names, numbers, proper nouns)
    that embedding similarity may miss.
    """
    if not keywords:
        return []

    # Build case-insensitive regex matching any keyword
    pattern = "|".join(re.escape(k) for k in keywords)

    results = []
    try:
        cursor = collection.find(
            {
                "meeting_id": meeting_id,
                "text": {"$regex": pattern, "$options": "i"},
            },
            {"embedding": 0},  # exclude large vector from result
        ).limit(top_k * 2)

        async for doc in cursor:
            text_lower = (doc.get("text") or "").lower()
            matched = sum(1 for k in keywords if k in text_lower)
            doc["score"] = matched / len(keywords)
            results.append(doc)
    except Exception as exc:
        logger.warning("Keyword search failed on %s: %s", collection.name, exc)

    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results[:top_k]


def _build_result(doc: dict, source_type: str) -> dict[str, Any]:
    """Normalize a raw MongoDB doc into a standard result dict."""
    source = doc.get("source", source_type)
    text = doc.get("text", "")

    if source_type == "transcript":
        attribution = {
            "speaker_name": doc.get("speaker_name"),
            "timestamp": doc.get("timestamp"),
        }
    else:
        attribution = {
            "filename": doc.get("filename"),
            "chunk_index": doc.get("chunk_index"),
        }

    return {
        "source": source,
        "text": text,
        "score": doc.get("score", 0.0),
        "attribution": attribution,
    }


def _deduplicate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate results by text content, keeping the highest-scored entry."""
    seen: dict[str, dict] = {}
    for r in results:
        text = r.get("text", "").strip()
        if not text:
            continue
        # Use first 200 chars as dedup key (chunks may have minor differences)
        key = text[:200]
        existing = seen.get(key)
        if existing is None or r.get("score", 0) > existing.get("score", 0):
            seen[key] = r
    return list(seen.values())


async def retrieve(
    meeting_id: str,
    query_text: str,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """
    Hybrid retrieval: vector similarity + keyword search.

    1. Generate query embedding
    2. Run vector search on both collections (semantic similarity)
    3. Run keyword search on both collections (exact term matching)
    4. Merge, deduplicate, and rank by combined score
    5. Return top-k results

    Args:
        meeting_id: The meeting to search within.
        query_text: The user's question text.
        top_k: Maximum number of results to return (default 8).

    Returns:
        List of result dicts with source, text, score, attribution.
    """
    db = get_database()

    # 1. Generate query embedding
    query_embeddings = await embed_texts([query_text])
    query_vector = query_embeddings[0]

    # 2. Extract keywords for keyword search
    keywords = _extract_keywords(query_text)

    # 3. Run all four searches in parallel (vector+keyword × 2 collections)
    import asyncio

    vector_transcript, vector_docs, kw_transcript, kw_docs = await asyncio.gather(
        _vector_search(db.transcript_chunks, meeting_id, query_vector, top_k),
        _vector_search(db.document_chunks, meeting_id, query_vector, top_k),
        _keyword_search(db.transcript_chunks, meeting_id, keywords, top_k),
        _keyword_search(db.document_chunks, meeting_id, keywords, top_k),
    )

    # 4. Build normalized results
    all_results: list[dict[str, Any]] = []

    for doc in vector_transcript:
        r = _build_result(doc, "transcript")
        r["_search_type"] = "vector"
        all_results.append(r)

    for doc in vector_docs:
        r = _build_result(doc, "document")
        r["_search_type"] = "vector"
        all_results.append(r)

    for doc in kw_transcript:
        r = _build_result(doc, "transcript")
        r["_search_type"] = "keyword"
        all_results.append(r)

    for doc in kw_docs:
        r = _build_result(doc, "document")
        r["_search_type"] = "keyword"
        all_results.append(r)

    # 5. Deduplicate — keep highest score per unique text
    unique_results = _deduplicate(all_results)

    # 6. Sort by score descending and return top_k
    unique_results.sort(key=lambda r: r.get("score", 0.0), reverse=True)

    # Remove internal field before returning
    for r in unique_results:
        r.pop("_search_type", None)

    logger.info(
        "Hybrid retrieval: meeting=%s query=%r → %d vector + %d keyword → %d unique (returning top %d)",
        meeting_id,
        query_text[:60],
        len(vector_transcript) + len(vector_docs),
        len(kw_transcript) + len(kw_docs),
        len(unique_results),
        min(top_k, len(unique_results)),
    )

    return unique_results[:top_k]
