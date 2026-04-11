# Task: AI Response Generation (Claude Integration)

## Objective

Integrate Claude Sonnet as the AI response engine for Arni. Implement the hybrid context strategy (rolling summary + last 20 transcript turns), the sequential AI request queue, and the internal `/ai/respond` endpoint. This is the core intelligence layer that wake word detection feeds into.

## Files

- Creates:
  - `backend/app/ai/__init__.py`
  - `backend/app/ai/context_manager.py`
  - `backend/app/ai/response_queue.py`
  - `backend/app/ai/ai_service.py`
  - `backend/app/routers/ai.py`
  - `backend/tests/test_context_manager.py`
  - `backend/tests/test_response_queue.py`
- Modifies:
  - `backend/app/main.py` — register `/ai` router
  - `backend/app/config.py` — add `ANTHROPIC_API_KEY`, `AI_CONTEXT_WINDOW` (default 20), `AI_MAX_RESPONSES` (default 30)
  - `backend/requirements.txt` — add `anthropic`
- Reads:
  - `docs/srs.md` — FR-021 to FR-027, §4.2 AI Service API, §8.8 Meeting Summary model
  - `docs/architecture.md` — §4.2 AI Service API, live meeting pipeline
  - `backend/app/bot/wake_word.py` — wake event structure
  - `backend/app/routers/transcripts.py` — transcript model

## Implementation Steps

1. Add `ANTHROPIC_API_KEY` and `AI_CONTEXT_WINDOW=20` to `backend/app/config.py`
2. Create `backend/app/ai/context_manager.py`:
   - `build_context(meeting_id)` → fetches latest rolling summary from MongoDB + last N transcript turns
   - Returns `{"system": str, "summary": str, "turns": list[dict]}`
   - Context window size is configurable via `AI_CONTEXT_WINDOW` env var
3. Create `backend/app/ai/response_queue.py`:
   - Asyncio `Queue` instance (FIFO, per meeting)
   - `enqueue(meeting_id, command, speaker_id)` — adds request; drops if within 10-second cooldown (RL-001)
   - `process_next()` — dequeues and calls `ai_service.respond()`
   - Max 30 responses per meeting enforced (RL-002); returns rate limit message beyond that
4. Create `backend/app/ai/ai_service.py`:
   - `respond(meeting_id, command, context)` → calls Anthropic Claude Sonnet API
   - System prompt: Arni's persona + "You are participating in a live meeting. Answer concisely and conversationally."
   - On LLM failure: return canned fallback (SRS NFR-011)
5. Create `backend/app/routers/ai.py` with `POST /ai/respond`:
   - Body: `{meeting_id, command, speaker_id}`
   - Calls `context_manager.build_context()` → `response_queue.enqueue()` → returns `{response_text}`
6. Register router in `main.py`
7. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] `POST /ai/respond` returns a contextually relevant response to a command within 3 seconds
- [ ] Context includes rolling summary + last 20 transcript turns (configurable)
- [ ] Concurrent wake events are queued and processed sequentially (FIFO)
- [ ] Cooldown of 10 seconds enforced per meeting — duplicate triggers dropped
- [ ] Max 30 AI responses per meeting — 31st returns rate limit message
- [ ] LLM API failure returns canned fallback message (not a 500)
- [ ] `ANTHROPIC_API_KEY` is read from environment — never hardcoded

## Testing Requirements

- Unit tests for:
  - `context_manager.build_context()`: correct summary + turn count, respects window size
  - `response_queue`: FIFO ordering, cooldown enforcement, rate limit at 30
  - Fallback response on simulated LLM timeout/error
- Integration tests for:
  - Full wake → context build → Claude call → response returned
  - Queue processes second request only after first completes

## Status

pending
