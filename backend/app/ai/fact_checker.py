"""
Proactive Fact-Checking Pipeline (FR-078–FR-084).

FactChecker.check() is called after every transcript turn. It:
  1. Skips immediately if no document chunks exist for the meeting.
  2. Skips if the meeting is within the cooldown window.
  3. Embeds the transcript text and runs a vector search against document chunks.
  4. Calls Claude to determine whether the claim contradicts the retrieved excerpt.
  5. If confidence >= threshold, enqueues a fact_check correction.
"""

import logging
import time
from typing import Optional

from app.config import get_settings
from app.database import get_database
from app.ai.response_queue import get_or_create_queue

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper stubs — real implementations delegate to embedding/Claude services
# ---------------------------------------------------------------------------

async def get_embedding(text: str) -> list[float]:
    """Return a vector embedding for text (delegates to embedding service)."""
    from app.ai.ai_service import get_text_embedding  # type: ignore[attr-defined]
    return await get_text_embedding(text)


async def vector_search(
    meeting_id: str,
    query_vector: list[float],
    top_k: int = 3,
) -> list[dict]:
    """
    Search document_chunks for the meeting using cosine similarity.

    Returns a list of dicts with at least 'text' and 'document_name' keys.
    """
    db = get_database()
    pipeline = [
        {
            "$search": {
                "index": "vector_index",
                "knnBeta": {
                    "vector": query_vector,
                    "path": "embedding",
                    "k": top_k,
                    "filter": {"meeting_id": meeting_id},
                },
            }
        },
        {"$limit": top_k},
        {"$project": {"text": 1, "document_name": 1, "_id": 0}},
    ]
    cursor = db.document_chunks.aggregate(pipeline)
    return await cursor.to_list(length=top_k)


async def claude_contradiction_check(
    claim: str,
    excerpt: str,
    document_name: str,
) -> dict:
    """
    Ask Claude whether `claim` contradicts `excerpt`.

    Returns a dict with keys:
      contradicts: bool
      confidence: float   (0.0–1.0)
      correction: str     (suggested correction text)
      excerpt: str        (the source excerpt)
    """
    from app.ai.ai_service import check_contradiction  # type: ignore[attr-defined]
    return await check_contradiction(claim, excerpt, document_name)


# ---------------------------------------------------------------------------
# FactChecker
# ---------------------------------------------------------------------------

class FactChecker:
    """
    Proactive fact-checking for live meeting transcripts.

    Args:
        confidence_threshold: Minimum confidence to enqueue a correction.
        cooldown_seconds: Minimum seconds between checks for the same meeting.
    """

    def __init__(
        self,
        confidence_threshold: Optional[float] = None,
        cooldown_seconds: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        self._threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.FACT_CHECK_CONFIDENCE_THRESHOLD
        )
        self._cooldown = (
            cooldown_seconds
            if cooldown_seconds is not None
            else settings.FACT_CHECK_COOLDOWN_SECONDS
        )
        self._last_triggered: dict[str, float] = {}

    async def check(
        self,
        meeting_id: str,
        speaker_id: str,
        transcript_text: str,
    ) -> Optional[dict]:
        """
        Run a fact-check pass for one transcript turn.

        Returns a correction dict if a contradiction above threshold is found,
        or None if the check was skipped or no contradiction was found.
        """
        db = get_database()

        # 1. Skip if no document chunks exist for this meeting
        cursor = db.document_chunks.find({"meeting_id": meeting_id})
        chunks = await cursor.to_list(length=1)
        if not chunks:
            logger.debug("No document chunks for meeting=%s, skipping fact-check", meeting_id)
            return None

        # 2. Skip if within cooldown window
        now = time.monotonic()
        last = self._last_triggered.get(meeting_id, 0.0)
        if (now - last) < self._cooldown:
            logger.debug("Fact-check cooldown active for meeting=%s", meeting_id)
            return None

        # 3. Embed the transcript text
        query_vector = await get_embedding(transcript_text)

        # 4. Vector search against document chunks
        results = await vector_search(meeting_id, query_vector)
        if not results:
            return None

        # Use the top result
        top = results[0]
        excerpt = top.get("text", "")
        document_name = top.get("document_name", "Unknown Document")

        # 5. Claude contradiction check
        check_result = await claude_contradiction_check(
            claim=transcript_text,
            excerpt=excerpt,
            document_name=document_name,
        )

        if not check_result.get("contradicts"):
            return None

        confidence = check_result.get("confidence", 0.0)
        if confidence < self._threshold:
            logger.debug(
                "Contradiction confidence %.2f below threshold %.2f, skipping",
                confidence,
                self._threshold,
            )
            return None

        # 6. Update cooldown timestamp
        self._last_triggered[meeting_id] = time.monotonic()

        # 7. Enqueue correction
        correction_text = check_result.get("correction", "")
        queue = get_or_create_queue(meeting_id)
        await queue.enqueue_correction(
            meeting_id=meeting_id,
            correction_text=correction_text,
            source_document=document_name,
            source_excerpt=excerpt,
        )

        result = {
            "contradicts": True,
            "confidence": confidence,
            "correction_text": correction_text,
            "source_document": document_name,
            "source_excerpt": excerpt,
        }
        logger.info(
            "Fact-check contradiction enqueued for meeting=%s confidence=%.2f",
            meeting_id,
            confidence,
        )
        return result


# Module-level singleton
fact_checker = FactChecker()
