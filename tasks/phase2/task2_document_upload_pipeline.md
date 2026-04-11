# Task: Pre-Meeting Document Upload Pipeline

## Objective

Allow users to upload reference documents (PDF, DOCX, TXT) to a meeting room before or during the meeting. Documents are chunked, embedded, and stored in the same MongoDB Atlas Vector Index as transcript chunks (tagged `source: "document"`). This gives Arni access to briefing materials when answering questions — exactly like a meeting partner who has read the pre-reads.

## Files

- Creates:
  - `backend/app/documents/__init__.py`
  - `backend/app/documents/document_service.py` — upload, chunk, embed, store
  - `backend/app/documents/text_extractor.py` — PDF/DOCX/TXT extraction
  - `backend/app/documents/chunker.py` — 200–400 token chunks, 50-token overlap
  - `backend/app/models/document.py` — Document + DocumentChunk MongoDB models
  - `backend/app/routers/documents.py` — REST endpoints
  - `backend/tests/test_chunker.py`
  - `backend/tests/test_document_service.py`
  - `frontend/src/components/DocumentUpload.tsx` — upload panel component
- Modifies:
  - `backend/app/main.py` — register `/meetings/{id}/documents` router
  - `backend/app/config.py` — add `OPENAI_API_KEY` (for text-embedding-3-large), `MAX_UPLOAD_SIZE_MB=20`, `MAX_DOCS_PER_MEETING=10`
  - `backend/requirements.txt` — add `pypdf2` or `pdfplumber`, `python-docx`, `openai`, `tiktoken`
  - `frontend/src/pages/Dashboard.tsx` or meeting creation flow — add DocumentUpload panel
- Reads:
  - `docs/srs.md` — FR-057a through FR-057i, §8.4 Document model, §8.5 Document Chunk model, §4.4 RAG chunking spec
  - `docs/architecture.md` — §5 Document Ingestion Pipeline diagram

## Implementation Steps

1. Add `OPENAI_API_KEY`, `MAX_UPLOAD_SIZE_MB`, `MAX_DOCS_PER_MEETING` to `backend/app/config.py`
2. Create `backend/app/models/document.py`:
   - `Document`: `id`, `meeting_id`, `uploaded_by`, `filename`, `file_type`, `file_size_bytes`, `status` (processing/ready/error), `chunk_count`, `uploaded_at`
   - `DocumentChunk`: `id`, `meeting_id`, `document_id`, `filename`, `chunk_index`, `text`, `embedding` (float[]), `source` = `"document"`
3. Create `backend/app/documents/text_extractor.py`:
   - `extract(file_bytes, file_type) → str` — handles PDF (pdfplumber), DOCX (python-docx), TXT (decode)
4. Create `backend/app/documents/chunker.py`:
   - `chunk(text, chunk_size_tokens=300, overlap_tokens=50) → list[str]`
   - Use `tiktoken` to count tokens
   - Chunk size must be 200–400 tokens; default 300
5. Create `backend/app/documents/document_service.py`:
   - `upload_document(meeting_id, user_id, file) → Document`:
     1. Validate: file type (pdf/docx/txt), size ≤ 20 MB, meeting doc count ≤ 10
     2. Save Document record with `status: processing`
     3. Publish `document.uploaded` (status: processing) to Redis
     4. Extract text → chunk → embed each chunk via `text-embedding-3-large`
     5. Store all DocumentChunk records in MongoDB
     6. Update Document `status: ready`, `chunk_count`
     7. Publish `document.uploaded` (status: ready) to Redis
     8. On any failure: update Document `status: error`, publish error event
6. Create `backend/app/routers/documents.py`:
   - `POST /meetings/{id}/documents` — multipart/form-data upload (participant-only, JWT required)
   - `GET /meetings/{id}/documents` — list documents for meeting (participant-only)
   - `DELETE /meetings/{id}/documents/{doc_id}` — delete doc + chunks (participant-only)
7. Create `frontend/src/components/DocumentUpload.tsx`:
   - Drag-and-drop + file picker for PDF/DOCX/TXT
   - Shows upload progress and document status (processing → ready / error)
   - Listens to `document.uploaded` WebSocket events for real-time status updates
8. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] `POST /meetings/{id}/documents` accepts PDF, DOCX, TXT files ≤ 20 MB
- [ ] Rejects files over 20 MB with a 413 error and clear message
- [ ] Rejects unsupported file types with a 415 error
- [ ] Rejects upload if meeting already has 10 documents (400 error)
- [ ] Document chunks stored with `source: "document"` and correct `filename`, `chunk_index`
- [ ] Chunk sizes are 200–400 tokens with 50-token overlap
- [ ] Embedding model used is `text-embedding-3-large`
- [ ] Processing (chunking + embedding) completes within 30 seconds for files under 5 MB (SRS FR-057i)
- [ ] `document.uploaded` events published with correct schema (processing → ready)
- [ ] `DELETE` removes Document record and all associated DocumentChunks
- [ ] Only authenticated meeting participants can upload, list, or delete documents
- [ ] `OPENAI_API_KEY` is read from environment — never hardcoded

## Testing Requirements

- Unit tests for:
  - `chunker.chunk()`: correct token boundaries, overlap respected, min/max token range enforced
  - `text_extractor.extract()`: correctly extracts text from sample PDF, DOCX, TXT
  - File validation: size limit, type check, count limit
- Integration tests for:
  - Full upload → extract → chunk → embed → store → verify `chunk_count` in MongoDB
  - `DELETE` removes document and all associated chunks from vector index
  - Upload rejected for non-participant (403)

## Status

pending
