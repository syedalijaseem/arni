# Task: AI Teammate Reasoning (Prompt Routing)

## Objective

Implement Arni's "AI Teammate" behavior: when a wake phrase command contains comparison language (e.g. "which", "better", "prefer", "recommend", "vs", "or"), the existing `/ai/respond` endpoint automatically routes to a reasoning-optimized prompt template. Arni must give an **explicit recommendation with justification** — not a neutral summary.

This is a **prompt routing behavior inside `/ai/respond`** — no new endpoints, no new pipelines. The change is entirely in the prompt construction layer of the AI service.

**Example:**
> "Hey Arni, should we go with Option A or Option B for the backend?"
> Arni: "I'd go with Option B. Given that you mentioned scaling to 100k users earlier, the long-term scalability benefit outweighs the short-term speed advantage of Option A. Option A would likely need a rewrite within 6 months."

This task depends on:
- task1 (AI response generation): `/ai/respond` endpoint and context manager must already exist
- task2 (document upload): RAG must be available so document context can be included in reasoning
- task5 (rolling summaries): rolling summary must be available as reasoning context

## Files

- Creates:
  - `backend/app/ai/reasoning_detector.py` — detects comparison/recommendation intent from command text
  - `backend/app/ai/prompt_templates.py` — Standard response template + Reasoning response template
  - `backend/tests/test_reasoning_detector.py`
  - `backend/tests/test_prompt_templates.py`
- Modifies:
  - `backend/app/ai/ai_service.py` — before calling Claude, run intent through `reasoning_detector.is_reasoning_request(command)`; select correct prompt template
  - `backend/app/ai/context_manager.py` — reasoning context must include: rolling summary + last 20 turns + RAG document chunks (FR-088)
- Reads:
  - `docs/srs.md` — FR-085 through FR-088, §4.2 AI Service API (`/ai/respond` description), §4.3 Key Pipelines (AI Teammate Reasoning)
  - `docs/architecture.md` — §6 Unified RAG Pipeline (document chunks included in reasoning context)

## Implementation Steps

1. Create `backend/app/ai/reasoning_detector.py`:
   - `is_reasoning_request(command: str) → bool`
   - Triggers when command contains any of: `"which"`, `"better"`, `"prefer"`, `"recommend"`, `"vs"`, `"versus"`, `"or"`, `"choose"`, `"decision"`, `"compare"`, `"between"` (case-insensitive, tokenized — not substring to avoid false positives like "for")
   - Returns `True` if any keyword present in the lowercased, tokenized command

2. Create `backend/app/ai/prompt_templates.py`:
   - `STANDARD_PROMPT`: Arni's default persona prompt — "You are Arni, an AI participant in a live meeting. Answer concisely and helpfully."
   - `REASONING_PROMPT`: "You are Arni, an AI participant in a live meeting. You have been asked to compare options and give a recommendation. You MUST: (1) State your explicit recommendation clearly. (2) Explain the key tradeoffs. (3) Reference any relevant context from this meeting or the provided documents. Do NOT give a neutral answer — take a position."
   - Both accept: `{summary}`, `{recent_turns}`, `{document_context}`, `{command}` as template variables

3. Update `backend/app/ai/context_manager.py` — add `build_reasoning_context(meeting_id, command)`:
   - Includes rolling summary + last 20 turns (same as standard)
   - **Additionally**: runs RAG retrieval against both transcript chunks and document chunks for `command` (top-5 results)
   - Returns full context dict with `document_context` field populated

4. Update `backend/app/ai/ai_service.py` — `respond(meeting_id, command, speaker_id)`:
   - Step 1: `is_reasoning = reasoning_detector.is_reasoning_request(command)`
   - Step 2:
     - If `is_reasoning`: use `context_manager.build_reasoning_context(meeting_id, command)` + `REASONING_PROMPT`
     - Else: use `context_manager.build_context(meeting_id)` + `STANDARD_PROMPT`
   - Step 3: Call Claude with the selected prompt + context (no other changes to the existing respond flow)

5. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] Command with "which do you recommend" → routes to `REASONING_PROMPT` (FR-085)
- [ ] Command with "summarize what we discussed" → routes to `STANDARD_PROMPT` (not reasoning)
- [ ] Reasoning response includes an explicit recommendation (e.g. "I recommend Option B") — Claude must not hedge or refuse to choose (FR-087)
- [ ] Reasoning response includes tradeoffs considered (FR-086)
- [ ] Reasoning context includes rolling summary + last 20 turns + RAG document chunks (FR-088)
- [ ] If no documents uploaded, reasoning still works using transcript context only (graceful degradation)
- [ ] Standard responses are unaffected — wake commands without comparison language use the existing standard prompt
- [ ] Reasoning detection is tokenized (not substring) — "for" does not accidentally match inside other words
- [ ] No new endpoints created — this is pure prompt routing inside `/ai/respond`

## Testing Requirements

- Unit tests for `reasoning_detector.is_reasoning_request()`:
  - `"which option is better"` → True
  - `"should we go with A or B"` → True
  - `"recommend the backend framework"` → True
  - `"summarize the discussion"` → False
  - `"what did John say about performance"` → False
  - `"explore our options"` → False (no keyword match — "or" appears only as substring of "explore")
- Unit tests for `prompt_templates.py`:
  - `REASONING_PROMPT` rendered with all variables → correct string, no missing placeholders
  - `STANDARD_PROMPT` rendered → correct string
- Integration tests for:
  - Wake command with "which" → `/ai/respond` uses `REASONING_PROMPT` → Claude returns answer with explicit recommendation
  - Wake command without comparison language → `/ai/respond` uses `STANDARD_PROMPT` → standard answer
  - Reasoning context includes document chunks when documents are uploaded
  - Reasoning context works correctly when no documents are uploaded (empty `document_context`)

## Status

complete

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
