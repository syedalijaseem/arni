# Phase 2: AI Core (Days 6–10)

## Objective

Build the complete real-time AI pipeline: wake word detection → Claude LLM response generation → ElevenLabs TTS voice output → interrupt handling → Redis event bus → periodic rolling summaries.

At the end of Phase 2, Arni can:
- Hear participants, respond in voice, maintain coherent context across an entire meeting
- Answer questions using uploaded reference documents and meeting transcripts simultaneously (unified RAG)
- Automatically correct factual contradictions in real time (proactive fact-checking)
- Give reasoned recommendations when asked to compare options (AI Teammate Reasoning)
- Enforce invite-only access, manage a waiting room, and enforce all host-only controls

## Owner

planner (initial tasks) / loop-operator (dynamic tasks)

## Status

in_progress

---

## Day 6 — Wake Word Detection ✅

**Goal:** Detect "Hey Arni" + command in the live transcript stream.

- [x] Detect "Hey Arni" + command in transcript stream
- [x] Parse command intent from wake phrase
- [x] Trigger AI request pipeline on detection
- [x] 10-second cooldown between triggers (rate limiting)

---

## Day 7 — AI Response Generation

**Goal:** Claude Sonnet responds to wake commands with hybrid context (rolling summary + last 20 turns).

**→ Task file:** `tasks/phase2/task1_ai_response_generation.md`

- [ ] Claude API integration (`ai-service`)
- [ ] Context strategy: rolling summary + last 20 turns (SRS FR-025)
- [ ] AI response queue — sequential FIFO processing (SRS FR-021–FR-023)
- [ ] `POST /ai/respond` internal endpoint
- [ ] Unit tests: context construction, queue ordering, rate limit enforcement

---

## Day 7b — Pre-Meeting Document Upload

**Goal:** Users can upload reference docs (PDF, DOCX, TXT) before meetings. Arni uses them as RAG context.

**→ Task file:** `tasks/phase2/task2_document_upload_pipeline.md`

- [ ] `POST /meetings/{id}/documents` endpoint (`document-service`)
- [ ] `GET /meetings/{id}/documents` — list uploaded files
- [ ] `DELETE /meetings/{id}/documents/{doc_id}`
- [ ] File validation: type (PDF/DOCX/TXT), size (≤20 MB), count (≤10 per meeting)
- [ ] Text extraction from PDF, DOCX, TXT
- [ ] Chunking pipeline: 200–400 tokens, 50-token overlap
- [ ] Embedding generation: `text-embedding-3-large`
- [ ] Store document chunks in MongoDB Atlas Vector Index tagged `source: "document"`
- [ ] Publish `document.uploaded` event to Redis (status: processing → ready)
- [ ] Frontend: document upload panel on pre-flight/meeting creation screen
- [ ] Unit tests: chunking boundaries, overlap, type validation

---

## Day 8 — Voice Response (TTS)

**Goal:** Arni speaks responses through the meeting via ElevenLabs.

**→ Task file:** `tasks/phase2/task3_voice_response_tts.md`

- [ ] ElevenLabs TTS integration (streaming)
- [ ] Convert AI text response → audio stream
- [ ] Inject audio into meeting via Daily.co Arni bot track (tagged `ai-source`)
- [ ] Audio feedback loop prevention: exclude `ai-source` tracks from Deepgram STT (SRS FR-033–FR-035)
- [ ] Frontend: AI status indicator — Listening → Processing → Speaking (SRS §6.1)
- [ ] Unit tests: track tagging, exclusion logic
- [ ] Integration test: full pipeline — wake → Claude → ElevenLabs → Daily.co audio

---

## Day 9 — Interrupt Handling + Event Bus

**Goal:** Human speech interrupts Arni mid-response; all 17 inter-service events move to Redis.

**→ Task file:** `tasks/phase2/task4_interrupt_and_event_bus.md`

- [ ] VAD: detect human speech during AI playback → stop AI audio immediately (SRS FR-028–FR-030)
- [ ] Redis Pub/Sub: wire up event bus for all 17 event types defined in SRS §4.6
  - `transcript.created`, `wake.detected`, `ai.requested`, `ai.responded`, `ai.state_changed`
  - `fact.checked`, `meeting.started`, `meeting.ended`, `meeting.processed`, `meeting.auto_ended`
  - `summary.updated`, `document.uploaded`
  - `participant.invited`, `participant.admitted` (with `admitted_by`), `participant.removed`, `participant.rejected`
  - `host.transferred`
- [ ] All events must conform strictly to the schemas in SRS §4.6 — no extra fields
- [ ] Integration tests: event publish → subscriber receives correct schema

---

## Day 9b — Meeting Access Control

**Goal:** Invite-only access, waiting room, host-only controls, Arni joins on creation.

**→ Task file:** `tasks/phase2/task6_meeting_access_control.md`

- [ ] Arni added to `participant_ids` on meeting **creation** (not first participant join) (FR-073)
- [ ] Invite list (`invite_list: list[str]`) enforced on every join attempt
- [ ] Non-invited users receive 403 + "You are not authorized to join this meeting" (FR-060)
- [ ] Invited users placed in Redis-backed waiting room (ephemeral, never MongoDB)
- [ ] Host endpoints: admit, reject, invite, remove participant, transfer host
- [ ] Host grace period: auto-end after 10-minute disconnect (FR-065)
- [ ] Dashboard and search scoped to user's own meetings (FR-068)
- [ ] Frontend: waiting room lobby UI + grace period countdown
- [ ] All participant/host events published (participant.invited, participant.admitted, participant.removed, participant.rejected, host.transferred, meeting.auto_ended)

---

## Day 10 — Periodic Summaries + Context

**Goal:** Arni maintains coherent context across 30+ minute meetings via rolling summaries.

**→ Task file:** `tasks/phase2/task5_rolling_summaries.md`

- [ ] `POST /ai/summarize` — rolling summary generation every 10 minutes (SRS FR-026)
- [ ] Store rolling summaries in MongoDB (SRS §8.8 Meeting Summary model)
- [ ] Feed rolling summary + last 20 turns into Claude context on each `ai.respond` call
- [ ] Verify: AI responses stay contextually coherent in simulated 30-minute meeting
- [ ] Publish `summary.updated` event on each regeneration
- [ ] Integration test: simulate long meeting, assert summary is updated every 10 min

---

## Day 10b — Proactive Fact-Checking

**Goal:** Arni automatically corrects factual contradictions against uploaded documents — no wake phrase needed.

**→ Task file:** `tasks/phase2/task7_proactive_fact_checking.md`

- [ ] `POST /ai/fact-check` internal endpoint
- [ ] Background fact-check triggered after every final transcript (non-blocking, fire-and-forget)
- [ ] Skip if no documents uploaded (FR-084)
- [ ] 30-second cooldown between corrections per meeting (FR-081)
- [ ] Corrections enqueued in same AI response queue as wake responses (FR-082)
- [ ] `fact.checked` event published on every correction (all 8 fields)
- [ ] Frontend: fact-check responses rendered with "📎 Fact Check" label (FR-083)
- [ ] Configurable threshold (default 0.85) and cooldown via env vars

---

## Day 10c — AI Teammate Reasoning

**Goal:** Arni gives explicit recommendations with justification when asked to compare options.

**→ Task file:** `tasks/phase2/task8_ai_teammate_reasoning.md`

- [ ] `reasoning_detector.is_reasoning_request(command)` detects comparison language
- [ ] Reasoning-optimized prompt template routes from within `/ai/respond` (no new endpoints)
- [ ] Reasoning context includes rolling summary + last 20 turns + RAG document chunks (FR-088)
- [ ] Arni always takes a position — never gives a neutral non-answer (FR-087)
- [ ] Standard responses unaffected when comparison language absent

---

## Completion Criteria

Phase 2 is complete when:
- "Hey Arni, what were our key decisions?" triggers a voice response using both meeting transcript context and any uploaded documents.
- "Hey Arni, should we use Option A or Option B?" returns an explicit recommendation with justification, citing meeting context.
- A participant stating a wrong metric from an uploaded document triggers an automatic voice correction citing the document.
- Rolling summaries are generated every 10 minutes and fed back into AI context.
- All invited participants pass through the waiting room and are admitted by the host.
- Non-invited users receive a 403 response with the correct message.
- All 17 Redis event bus schemas are enforced with `extra="forbid"`.
- All Phase 2 unit and integration tests pass.
- `docker compose up` runs the full AI pipeline cleanly.
