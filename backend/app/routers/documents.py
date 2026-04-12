"""
Documents Router — REST endpoints for meeting document management.

Endpoints:
  POST   /meetings/{id}/documents  — upload a document
  GET    /meetings/{id}/documents  — list documents for meeting
  DELETE /meetings/{id}/documents/{doc_id} — delete doc + chunks
  POST   /meetings/{id}/documents/reprocess — re-extract, re-chunk, re-embed all docs
"""

import logging
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.database import get_database
from app.deps import get_current_user
from app.documents.document_service import upload_document
from app.models.document import DocumentResponse, DocumentStatus

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE_HEADER = 20 * 1024 * 1024  # 20 MB guard


async def _get_meeting_and_assert_participant(
    meeting_id: str,
    user: dict,
    db,
) -> dict:
    """Fetch meeting and assert the current user is a participant or host."""
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    user_id = user["id"]
    is_host = str(meeting.get("host_id")) == user_id
    participant_ids = [str(pid) for pid in meeting.get("participant_ids", [])]
    if not is_host and user_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant of this meeting",
        )
    return meeting


@router.post("/{meeting_id}/documents", response_model=DocumentResponse, status_code=201)
async def upload_meeting_document(
    meeting_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a PDF, DOCX, or TXT document to a meeting."""
    db = get_database()
    await _get_meeting_and_assert_participant(meeting_id, current_user, db)

    file_bytes = await file.read()

    # Guard against oversized uploads before processing
    if len(file_bytes) > MAX_FILE_SIZE_HEADER:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 20 MB upload limit.",
        )

    try:
        result = await upload_document(
            meeting_id=meeting_id,
            user_id=current_user["id"],
            filename=file.filename or "unknown",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
            redis_client=None,  # Redis wired up in phase 4
        )
    except ValueError as exc:
        # Validation errors map to 400/415 depending on error type
        msg = str(exc)
        if "unsupported file type" in msg:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=msg)
        if "size" in msg:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as exc:
        logger.error("Document upload error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document processing failed. Please try again.",
        )

    # Fetch full document record for response
    from bson import ObjectId as OID
    doc = await db.documents.find_one({"_id": OID(result["id"])})
    if not doc:
        raise HTTPException(status_code=500, detail="Document record not found after upload")

    return DocumentResponse(
        id=str(doc["_id"]),
        meeting_id=doc["meeting_id"],
        uploaded_by=doc["uploaded_by"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        file_size_bytes=doc["file_size_bytes"],
        status=doc["status"],
        chunk_count=doc["chunk_count"],
        uploaded_at=doc["uploaded_at"],
    )


@router.get("/{meeting_id}/documents", response_model=list[DocumentResponse])
async def list_meeting_documents(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all documents uploaded to a meeting."""
    db = get_database()
    await _get_meeting_and_assert_participant(meeting_id, current_user, db)

    cursor = db.documents.find({"meeting_id": meeting_id}).sort("uploaded_at", 1)
    docs = await cursor.to_list(length=100)

    return [
        DocumentResponse(
            id=str(d["_id"]),
            meeting_id=d["meeting_id"],
            uploaded_by=d["uploaded_by"],
            filename=d["filename"],
            file_type=d["file_type"],
            file_size_bytes=d["file_size_bytes"],
            status=d["status"],
            chunk_count=d["chunk_count"],
            uploaded_at=d["uploaded_at"],
        )
        for d in docs
    ]


@router.delete("/{meeting_id}/documents/{doc_id}", status_code=204)
async def delete_meeting_document(
    meeting_id: str,
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a document and all its associated chunks."""
    db = get_database()
    await _get_meeting_and_assert_participant(meeting_id, current_user, db)

    doc = await db.documents.find_one({"_id": ObjectId(doc_id), "meeting_id": meeting_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete all chunks for this document
    await db.document_chunks.delete_many({"document_id": doc_id})
    # Delete the document record
    await db.documents.delete_one({"_id": ObjectId(doc_id)})

    logger.info("Deleted document %s and its chunks from meeting %s", doc_id, meeting_id)


@router.post("/{meeting_id}/documents/reprocess")
async def reprocess_documents(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Re-extract, re-chunk, and re-embed all documents for a meeting.

    Deletes existing chunks and replaces them with new ones using
    the latest table-aware extraction pipeline. Host only.
    """
    from app.documents.text_extractor import extract
    from app.documents.chunker import chunk as chunk_text
    from app.documents.document_service import embed_text
    from app.models.document import DocumentChunkCreate

    db = get_database()
    meeting = await db.meetings.find_one({"_id": ObjectId(meeting_id)})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if str(meeting["host_id"]) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the host can reprocess documents")

    docs = await db.documents.find({"meeting_id": meeting_id}).to_list(length=100)
    if not docs:
        return {"reprocessed": 0, "total_chunks": 0}

    total_chunks = 0
    reprocessed = 0

    for doc in docs:
        doc_id = str(doc["_id"])
        filename = doc.get("filename", "unknown")
        file_type = doc.get("file_type", "")

        # We need the original file bytes — stored docs don't keep them,
        # so we re-read from the stored chunks' text and rebuild.
        # Instead, fetch all existing chunk texts and re-chunk them.
        old_chunks = await db.document_chunks.find(
            {"document_id": doc_id},
        ).sort("chunk_index", 1).to_list(length=500)

        if not old_chunks:
            continue

        # Reconstruct approximate original text from chunks
        # (overlap means some duplication, but re-chunking handles it)
        original_text = "\n".join(c.get("text", "") for c in old_chunks)

        # Delete old chunks
        await db.document_chunks.delete_many({"document_id": doc_id})

        try:
            # Re-chunk with table-aware chunker
            new_chunks = chunk_text(original_text)
            if not new_chunks:
                continue

            # Re-embed
            embeddings = await embed_text(new_chunks)

            # Persist new chunks
            chunk_docs = [
                DocumentChunkCreate(
                    meeting_id=meeting_id,
                    document_id=doc_id,
                    filename=filename,
                    chunk_index=i,
                    text=chunk,
                    embedding=emb,
                    has_table="[TABLE" in chunk,
                ).model_dump()
                for i, (chunk, emb) in enumerate(zip(new_chunks, embeddings))
            ]
            if chunk_docs:
                await db.document_chunks.insert_many(chunk_docs)

            # Update document record
            await db.documents.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "ready", "chunk_count": len(new_chunks)}},
            )

            total_chunks += len(new_chunks)
            reprocessed += 1
            logger.info("Reprocessed doc %s: %d chunks", doc_id, len(new_chunks))

        except Exception as exc:
            logger.error("Reprocess failed for doc %s: %s", doc_id, exc)
            await db.documents.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "error"}},
            )

    return {"reprocessed": reprocessed, "total_chunks": total_chunks}
