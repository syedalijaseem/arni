# Task: Unified Semantic Search (RAG Pipeline)

## Objective

Build the post-meeting Q&A system using Retrieval-Augmented Generation (RAG). Transcript chunks are embedded post-meeting and stored in MongoDB Atlas Vector Index. The `/ai/qa` endpoint performs unified vector search across **both** transcript chunks AND pre-uploaded document chunks simultaneously, then generates an answer with full source attribution. Users can ask "What earnings did we report last quarter?" and get an answer citing both transcript moments and uploaded docs.

## Files

- Creates:
  - `backend/app/rag/__init__.py`
  - `backend/app/rag/embedder.py` — transcript chunk embedding post-meeting
  - `backend/app/rag/retriever.py` — unified vector search across transcript + document chunks
  - `backend/tests/test_rag.py`
- Modifies:
  - `backend/app/postprocessing/processor.py` — add transcript embedding step after report generation
  - `backend/app/routers/ai.py` — add `POST /ai/qa`
  - `backend/app/routers/meetings.py` — add `POST /meetings/{id}/ask` (public endpoint calling `/ai/qa`)
  - `backend/app/models/transcript.py` — confirm `source: "transcript"` and `embedding` fields exist
- Reads:
  - `docs/srs.md` — FR-045, FR-053 to FR-056, FR-057d to FR-057f, §4.4 RAG Chunking Spec, §8.3 Transcript Chunk model, §8.5 Document Chunk model, RL-003 (20 queries/meeting/user)
  - `docs/architecture.md` — §6 Unified RAG Pipeline diagram

## Implementation Steps

1. Create `backend/app/rag/embedder.py`:
   - `embed_transcript(meeting_id)` — fetches all final transcript chunks for meeting, splits into 200–400 token chunks (50-token overlap), generates `text-embedding-3-large` embeddings, stores `embedding` field on each `TranscriptChunk`
   - Idempotent: skip chunks that already have embeddings
2. Update `backend/app/postprocessing/processor.py`:
   - After generating report, call `embedder.embed_transcript(meeting_id)`
   - This runs within the 60-second SLA window
3. Create `backend/app/rag/retriever.py`:
   - `retrieve(meeting_id, query_text, top_k=5) → list[dict]`
   - Generate query embedding via `text-embedding-3-large`
   - Run MongoDB Atlas Vector Search across both `TranscriptChunk` AND `DocumentChunk` collections, filtered to `meeting_id`
   - Return results with `source`, `text`, and attribution metadata (`speaker_name + timestamp` for transcript; `filename + chunk_index` for document)
4. Add `POST /ai/qa` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id, question, user_id}`
   - Enforce RL-003: max 20 queries per meeting per user (track in MongoDB or Redis counter)
   - Call `retriever.retrieve(meeting_id, question)`
   - Build prompt: system instruction + retrieved chunks with source labels + question
   - Call Claude Sonnet → return `{answer, sources: [{source, excerpt, attribution}]}`
5. Add `POST /meetings/{id}/ask` to meetings router:
   - Auth: participant-only
   - Delegates to `POST /ai/qa`
   - Returns answer + sources

## Success Criteria

- [ ] Transcript chunks embedded post-meeting with `text-embedding-3-large` (200–400 tokens, 50-token overlap)
- [ ] Vector search queries both `source: "transcript"` and `source: "document"` chunks simultaneously
- [ ] Answer includes source attribution:
  - Transcript: speaker name + timestamp + excerpt
  - Document: filename + excerpt
- [ ] Answer clearly distinguishes when context came from a document vs. a transcript
- [ ] Max 20 queries per meeting per user enforced (RL-003); 21st returns rate limit message
- [ ] Non-participant receives 403
- [ ] Integration test: upload a PDF with known content → run a meeting → ask a question whose answer is only in the PDF → verify answer cites the document

## Testing Requirements

- Unit tests for:
  - `embedder.embed_transcript()`: correct chunk count and token range; idempotent on re-run
  - `retriever.retrieve()`: returns results from both transcript and document collections; `source` field correct on each result
  - Rate limit: 20th query succeeds; 21st returns 429 with user-friendly message
- Integration tests for:
  - Full post-meeting flow: end meeting → embed transcript → ask question → get answer with transcript source
  - Upload PDF → ask question → get answer with document source attribution
  - Unified: question answerable from both sources → answer cites both

## Status

pending

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
