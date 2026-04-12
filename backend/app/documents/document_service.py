"""
Document Service — orchestrates the full upload pipeline.

Pipeline (SRS FR-057a–FR-057i):
1. Validate file type, size, and per-meeting count limit
2. Persist Document record (status: processing)
3. Publish document.uploaded (processing) to Redis
4. Extract text → chunk → embed each chunk
5. Persist all DocumentChunk records
6. Update Document status: ready, chunk_count
7. Publish document.uploaded (ready) to Redis
8. On any failure: set status: error, publish error event
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.database import get_database
from app.models.document import DocumentCreate, DocumentChunkCreate, DocumentStatus
from app.documents.text_extractor import extract, SUPPORTED_TYPES
from app.documents.chunker import chunk as chunk_text

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = SUPPORTED_TYPES


async def validate_upload(
    filename: str,
    content_type: str,
    file_size_bytes: int,
    existing_doc_count: int,
) -> None:
    """
    Validate an incoming upload against all business rules.

    Raises:
        ValueError with a user-visible message on any violation.
    """
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError(
            f"unsupported file type: {content_type!r}. "
            "Only PDF, DOCX, and TXT files are accepted."
        )

    if file_size_bytes > max_bytes:
        raise ValueError(
            f"File size {file_size_bytes / (1024*1024):.1f} MB exceeds the "
            f"{settings.MAX_UPLOAD_SIZE_MB} MB size limit."
        )

    if existing_doc_count >= settings.MAX_DOCS_PER_MEETING:
        raise ValueError(
            f"This meeting has reached the document upload limit "
            f"({settings.MAX_DOCS_PER_MEETING} documents)."
        )


async def embed_text(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of text strings using OpenAI text-embedding-3-large.

    Returns a list of embedding vectors (one per input text).
    """
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
    )
    return [item.embedding for item in response.data]


async def upload_document(
    meeting_id: str,
    user_id: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    redis_client=None,
) -> dict:
    """
    Execute the full document upload pipeline.

    Args:
        meeting_id: Target meeting.
        user_id: ID of the uploading participant.
        filename: Original filename.
        content_type: MIME type of the uploaded file.
        file_bytes: Raw file content.
        redis_client: Optional Redis client for pub/sub events.

    Returns:
        The stored document dict with 'id' field set.

    Raises:
        ValueError: On validation failure (bubbled up to router).
    """
    db = get_database()
    settings = get_settings()

    # Count existing docs for this meeting
    existing_count = await db.documents.count_documents({"meeting_id": meeting_id})

    await validate_upload(
        filename=filename,
        content_type=content_type,
        file_size_bytes=len(file_bytes),
        existing_doc_count=existing_count,
    )

    # Insert initial Document record
    doc_record = DocumentCreate(
        meeting_id=meeting_id,
        uploaded_by=user_id,
        filename=filename,
        file_type=content_type,
        file_size_bytes=len(file_bytes),
        status=DocumentStatus.PROCESSING,
    )
    result = await db.documents.insert_one(doc_record.model_dump())
    document_id = str(result.inserted_id)

    # Publish processing event
    await _publish_event(redis_client, {
        "event": "document.uploaded",
        "meeting_id": meeting_id,
        "document_id": document_id,
        "filename": filename,
        "status": "processing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    try:
        # Extract text
        text = extract(file_bytes, content_type)

        if not text.strip():
            raise ValueError("Document appears to be empty or could not be parsed.")

        # Chunk text
        chunks = chunk_text(text)

        # Embed chunks
        embeddings = await embed_text(chunks)

        # Persist chunks
        chunk_docs = [
            DocumentChunkCreate(
                meeting_id=meeting_id,
                document_id=document_id,
                filename=filename,
                chunk_index=i,
                text=chunk,
                embedding=embedding,
                has_table="[TABLE" in chunk,
            ).model_dump()
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        if chunk_docs:
            await db.document_chunks.insert_many(chunk_docs)

        # Update document status
        chunk_count = len(chunks)
        await db.documents.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": DocumentStatus.READY, "chunk_count": chunk_count}},
        )

        # Publish ready event
        await _publish_event(redis_client, {
            "event": "document.uploaded",
            "meeting_id": meeting_id,
            "document_id": document_id,
            "filename": filename,
            "status": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(
            "Document uploaded: meeting=%s, doc=%s, chunks=%d",
            meeting_id,
            document_id,
            chunk_count,
        )
        return {"id": document_id, "chunk_count": chunk_count, "status": "ready"}

    except Exception as exc:
        logger.error(
            "Document upload failed: meeting=%s, doc=%s, error=%s",
            meeting_id,
            document_id,
            exc,
        )
        await db.documents.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": DocumentStatus.ERROR}},
        )
        await _publish_event(redis_client, {
            "event": "document.uploaded",
            "meeting_id": meeting_id,
            "document_id": document_id,
            "filename": filename,
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise


async def _publish_event(redis_client, event: dict) -> None:
    """Publish event to Redis if a client is available."""
    if redis_client is None:
        return
    import json
    try:
        await redis_client.publish("arni:events", json.dumps(event))
    except Exception as exc:
        logger.warning("Failed to publish event to Redis: %s", exc)
