# Task: Post-Meeting Processing Pipeline

## Objective

When a host ends a meeting, `postprocessing-service` asynchronously generates the full structured report: title, summary, key decisions, and action items. All extractions use the `/ai/summarize`, `/ai/extract-decisions`, and `/ai/extract-actions` endpoints from the AI Service API. Processing must complete within 60 seconds of meeting end.

## Files

- Creates:
  - `backend/app/postprocessing/__init__.py`
  - `backend/app/postprocessing/processor.py` — orchestrates full post-meeting pipeline
  - `backend/tests/test_postprocessing.py`
- Modifies:
  - `backend/app/routers/meetings.py` — trigger `processor.run(meeting_id)` asynchronously on `POST /meetings/{id}/end`
  - `backend/app/routers/ai.py` — add `POST /ai/extract-decisions`, `POST /ai/extract-actions`
  - `backend/app/config.py` — confirm `ANTHROPIC_API_KEY` present
- Reads:
  - `docs/srs.md` — FR-041 to FR-045, NFR-003 (60-second SLA), §4.2 AI Service API, §8.2 Meeting model
  - `docs/architecture.md` — §4 Post-Meeting Processing Pipeline, §10 Post-Meeting Processing sequence diagram

## Implementation Steps

1. Add `POST /ai/extract-decisions` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id, transcript_text}`
   - System prompt: `"Extract decisions ONLY if explicitly stated in the transcript. Do not infer. Return a JSON array of strings."`
   - Return `{"decisions": list[str]}`
2. Add `POST /ai/extract-actions` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id, transcript_text}`
   - System prompt: `"Extract action items ONLY from explicit commitments or assignments stated in the transcript. Do not infer tasks. Return a JSON array of {description, assignee, deadline}."`
   - Return `{"action_items": list[dict]}`
3. Create `backend/app/postprocessing/processor.py` — `run(meeting_id)` async function:
   1. Set meeting `state: Ended`
   2. Fetch full transcript from MongoDB
   3. Call `/ai/summarize` → store `summary` and `title` on Meeting
   4. Call `/ai/extract-decisions` → store `decisions[]` on Meeting
   5. Call `/ai/extract-actions` → create `ActionItem` documents, store IDs on Meeting
   6. Set meeting `state: Processed`
   7. Publish `meeting.processed` event to Redis
   8. Total time must be under 60 seconds (NFR-003)
4. In `POST /meetings/{id}/end`: call `asyncio.create_task(processor.run(meeting_id))` — non-blocking
5. Frontend: on `meeting.ended` event → show "Processing your meeting report..."; on `meeting.processed` → show "Report ready" notification

## Success Criteria

- [ ] Ending a meeting triggers async post-processing without blocking the API response
- [ ] Meeting title and summary generated and stored in MongoDB
- [ ] Decisions extracted — only explicitly stated ones; no inferred decisions (FR-042)
- [ ] Action items extracted — only from explicit commitments; no inferred tasks (FR-043)
- [ ] `ActionItem` documents created and linked via `action_item_ids` on Meeting
- [ ] Meeting state transitions: Active → Ended → Processed
- [ ] `meeting.processed` event published when complete
- [ ] Full pipeline completes within 60 seconds (NFR-003)
- [ ] Frontend shows "processing" state then "report ready" notification

## Testing Requirements

- Unit tests for:
  - `extract-decisions`: with explicit decision in transcript → extracted; with only implied decision → empty list
  - `extract-actions`: with explicit assignment → extracted; with vague discussion → empty list
  - State transitions: Active → Ended → Processed
- Integration tests for:
  - End meeting → assert all report fields populated in MongoDB within 60 seconds
  - `meeting.processed` event published and received by WebSocket subscriber

## Status

complete

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
