# Task: Proactive Fact-Checking Pipeline

## Objective

Implement Arni's most important differentiator: after every final transcript entry, Arni silently runs a background vector search against uploaded document chunks. If a participant states a fact that contradicts a document above a configurable confidence threshold (default: 0.85), Arni automatically interjects with a voice correction — without waiting for a wake phrase.

**Example:**
> Participant: "Our churn last quarter was 12%."
> Uploaded doc says: churn = 7%
> Arni: "Small correction — according to the Q4 report, churn rate was 7%, not 12%."

This task depends on:
- task2 (document upload + vector index): documents must be chunked and embedded before fact-checking can run
- task3 (TTS + audio injection): correction must be spoken via ElevenLabs
- task4 (event bus + schemas): `fact.checked` event schema must already be defined
- task5 (rolling summaries): not strictly required but should be in place

## Files

- Creates:
  - `backend/app/ai/fact_checker.py` — core fact-check orchestration
  - `backend/app/routers/ai.py` additions — `POST /ai/fact-check` endpoint
  - `backend/tests/test_fact_checker.py`
- Modifies:
  - `backend/app/routers/transcripts.py` — after storing final transcript, fire-and-forget `fact_checker.check(meeting_id, transcript_chunk)`
  - `backend/app/ai/response_queue.py` — support enqueueing fact-check corrections (same queue as wake responses, FR-082)
  - `backend/app/config.py` — add `FACT_CHECK_CONFIDENCE_THRESHOLD=0.85`, `FACT_CHECK_COOLDOWN_SECONDS=30`
  - `backend/app/events/schemas.py` — confirm `FactCheckedEvent` is defined (done in task4; verify only)
  - `frontend/src/pages/MeetingRoom.tsx` — render `fact.checked` events in transcript feed with distinct "📎 Fact Check" label (FR-083)
- Reads:
  - `docs/srs.md` — FR-078 through FR-084, §4.2 AI Service API (`POST /ai/fact-check`), §4.6 Event Bus (`fact.checked`)
  - `docs/architecture.md` — §5b Proactive Fact-Check Pipeline diagram

## Implementation Steps

1. Add to `backend/app/config.py`:
   - `FACT_CHECK_CONFIDENCE_THRESHOLD: float = 0.85`
   - `FACT_CHECK_COOLDOWN_SECONDS: int = 30`

2. Create `backend/app/ai/fact_checker.py`:
   - `check(meeting_id, transcript_chunk) → None` — called as `asyncio.create_task()` (non-blocking, FR-078)
   - Step 1: Check if any documents exist for this meeting — if none, return immediately (FR-084)
   - Step 2: Check cooldown — if `fact_check_last_triggered[meeting_id] + COOLDOWN > now`, return immediately (FR-081)
   - Step 3: Generate embedding for `transcript_chunk.text` (text-embedding-3-large)
   - Step 4: Vector search **document chunks only** (`source: "document"`) for this meeting — topK=3
   - Step 5: For each candidate: ask Claude "Does this transcript claim contradict this document excerpt? Reply with JSON `{contradicts: bool, confidence: float, correction: str, excerpt: str}`"
   - Step 6: If any result has `contradicts: true` and `confidence >= THRESHOLD`:
     a. Update cooldown timestamp: `fact_check_last_triggered[meeting_id] = now`
     b. Enqueue correction in AI response queue (FR-082): `response_queue.enqueue_correction(meeting_id, correction_text, source_document, source_excerpt)`
     c. Publish `fact.checked` event: `meeting_id`, `speaker_id`, `original_claim`, `correction_text`, `source_document`, `source_excerpt`, `confidence_score`, `timestamp`

3. Add `POST /ai/fact-check` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id: str, transcript_text: str, speaker_id: str}`
   - Calls `fact_checker.check()` synchronously (for testability; transcript router uses async task)
   - Returns: `{contradicts: bool, confidence: float, correction_text: str | None, source_document: str | None, source_excerpt: str | None}`

4. Update `backend/app/ai/response_queue.py`:
   - Add `enqueue_correction(meeting_id, correction_text, source_document, source_excerpt)` method
   - Corrections are tagged with `response_type: "fact_check"` to distinguish from wake responses
   - Obeys same FIFO queue — does not jump the queue

5. Update `backend/app/routers/transcripts.py`:
   - After storing final transcript chunk: `asyncio.create_task(fact_checker.check(meeting_id, chunk))`
   - This must be fire-and-forget — the transcript pipeline must not await the fact-check result

6. Update `frontend/src/pages/MeetingRoom.tsx`:
   - Subscribe to `fact.checked` WebSocket events
   - Render in transcript feed with a distinct visual label: "📎 Fact Check" (different color from wake responses, FR-083)
   - Show: Arni's correction text + source document name + excerpt

7. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] After every final transcript, `fact_checker.check()` runs as a background task — transcript storage is NOT blocked (FR-078)
- [ ] If no documents uploaded, check silently skipped with no error (FR-084)
- [ ] If cooldown active (< 30 seconds since last correction), check silently skipped (FR-081)
- [ ] Fact-check correction only fires when confidence ≥ 0.85 (configurable) (FR-079)
- [ ] Correction cites source document name and relevant excerpt (FR-080)
- [ ] Correction is enqueued in the same queue as wake responses — does not interrupt in-progress AI response (FR-082)
- [ ] `fact.checked` event published on every correction with all 8 required fields (SRS §4.6)
- [ ] Frontend renders fact-check responses with "📎 Fact Check" label, visually distinct from wake responses (FR-083)
- [ ] `FACT_CHECK_CONFIDENCE_THRESHOLD` and `FACT_CHECK_COOLDOWN_SECONDS` configurable via env vars
- [ ] `POST /ai/fact-check` endpoint returns correct response shape for both contradiction-found and no-contradiction cases

## Testing Requirements

- Unit tests for:
  - `fact_checker.check()`: no documents → immediate return without calling embedder
  - `fact_checker.check()`: cooldown active → immediate return without calling vector search
  - `fact_checker.check()`: confidence below threshold → no enqueue, no event published
  - `fact_checker.check()`: confidence above threshold → correction enqueued, `fact.checked` published
  - Cooldown timer: second call within 30s skipped; call after 30s proceeds
  - `enqueue_correction()`: tagged as `response_type: "fact_check"`; respects FIFO order behind existing wake responses
- Integration tests for:
  - Upload doc with churn = 7% → participant says "churn was 12%" → verify `fact.checked` event published with correct `source_document` and `confidence_score >= 0.85`
  - Participant says correct fact → verify no `fact.checked` event published
  - Two contradictions within 30 seconds → only first triggers correction (FR-081)
  - Fact-check correction enqueued while wake response processing → correction plays after wake response completes (FR-082)
  - No documents uploaded → transcript entry processed → no `fact.checked` event

## Status

pending
