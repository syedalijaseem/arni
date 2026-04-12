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

# Matches uppercase acronyms/model names (ARL, SLAKE, PathVQA) and numbers
_PROPER_RE = re.compile(r"[A-Z][A-Z0-9]{1,}(?:[a-z]+[A-Z0-9]*)*")
_NUMBER_RE = re.compile(r"\d+\.?\d*%?")

_METRIC_KEYWORDS = frozenset({
    "accuracy", "score", "performance", "result", "metric", "metrics",
    "percent", "f1", "precision", "recall", "dataset", "benchmark",
    "evaluate", "evaluation", "comparison", "compare", "table", "figure",
    "auc", "bleu", "rouge", "loss", "error", "rate",
})


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful search terms from a query, removing stop words.

    Preserves uppercase model names (ARL, SLAKE, PathVQA) and numbers
    as-is for exact matching, alongside lowercased content words.
    """
    # High-priority: uppercase acronyms and numbers (case-preserved)
    proper_names = _PROPER_RE.findall(query)
    numbers = _NUMBER_RE.findall(query)

    # Standard: lowercased content words
    tokens = _WORD_RE.findall(query.lower())
    content_words = [t for t in tokens if t not in _STOP_WORDS and len(t) > 2]

    # Merge without duplicates, proper names first
    seen: set[str] = set()
    keywords: list[str] = []
    for term in proper_names + numbers + content_words:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            keywords.append(term)

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
        "has_table": doc.get("has_table", False),
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

    # 4. Build normalized results — keyword results first for priority
    keyword_results: list[dict[str, Any]] = []
    vector_results: list[dict[str, Any]] = []

    for doc in kw_docs:
        r = _build_result(doc, "document")
        r["_search_type"] = "keyword"
        keyword_results.append(r)

    for doc in kw_transcript:
        r = _build_result(doc, "transcript")
        r["_search_type"] = "keyword"
        keyword_results.append(r)

    for doc in vector_docs:
        r = _build_result(doc, "document")
        r["_search_type"] = "vector"
        vector_results.append(r)

    for doc in vector_transcript:
        r = _build_result(doc, "transcript")
        r["_search_type"] = "vector"
        vector_results.append(r)

    # 5. Boost keyword results that match proper names from the query
    proper_names = {k.lower() for k in _PROPER_RE.findall(query_text)}
    for r in keyword_results:
        text_lower = r.get("text", "").lower()
        name_hits = sum(1 for name in proper_names if name in text_lower)
        if name_hits > 0:
            r["score"] = max(r.get("score", 0.0), 0.8) + (name_hits * 0.1)

    # Merge: keyword results first, then vector
    all_results = keyword_results + vector_results

    # 6. Deduplicate — keep highest score per unique text
    unique_results = _deduplicate(all_results)

    # 7. Boost table chunks when query mentions metrics/scores
    query_tokens = set(_WORD_RE.findall(query_text.lower()))
    is_metric_query = bool(query_tokens & _METRIC_KEYWORDS) or bool(proper_names)

    if is_metric_query:
        for r in unique_results:
            if r.get("has_table"):
                r["score"] = r.get("score", 0.0) * 1.2

    # 8. Sort by score descending
    unique_results.sort(key=lambda r: r.get("score", 0.0), reverse=True)

    # Remove internal fields before returning
    for r in unique_results:
        r.pop("_search_type", None)
        r.pop("has_table", None)

    final_k = top_k + 2 if is_metric_query else top_k

    logger.info(
        "Hybrid retrieval: meeting=%s query=%r metric=%s proper=%s → %d kw + %d vec → %d unique (top %d)",
        meeting_id,
        query_text[:60],
        is_metric_query,
        proper_names or "none",
        len(keyword_results),
        len(vector_results),
        len(unique_results),
        min(final_k, len(unique_results)),
    )

    return unique_results[:final_k]
