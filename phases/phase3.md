# Phase 3: Post-Meeting Intelligence (Days 11–14)

## Objective

Build the complete post-meeting processing system: async report generation, editable action items, unified RAG pipeline (transcript + uploaded documents), and the meeting history dashboard with semantic search.

At the end of Phase 3, every meeting has a structured, searchable knowledge artifact. Users can ask questions about any past meeting and get answers with source attribution from both transcripts and uploaded documents.

## Owner

planner (initial tasks) / loop-operator (dynamic tasks)

## Status

pending

---

## Day 11 — Post-Meeting Processing

**Goal:** When a meeting ends, `postprocessing-service` automatically generates a full structured report.

- [ ] Meeting end event → trigger `postprocessing-service` asynchronously
- [ ] `POST /ai/summarize` — generate final meeting title + summary
- [ ] `POST /ai/extract-decisions` — extract only explicitly stated decisions (SRS FR-042)
- [ ] `POST /ai/extract-actions` — extract only explicit action items/assignments (SRS FR-043)
- [ ] Store structured report (title, summary, decisions, action_item_ids, timeline) in MongoDB Meeting model
- [ ] Publish `meeting.processed` event on completion
- [ ] Frontend: "Meeting ended, processing..." state while report is being generated
- [ ] Processing must complete within 60 seconds of meeting end (SRS NFR-003)
- [ ] Integration test: end meeting → verify all report fields populated in MongoDB

---

## Day 12 — Editable Action Items + Timeline

**Goal:** Action items are editable by all participants; a timestamped topic timeline is generated.

- [ ] Action Item data model (SRS §8.7)
- [ ] `POST /ai/timeline` — generate timestamped topic segmentation
- [ ] `PATCH /meetings/{id}/action-items/{item_id}` — edit description, assignee, deadline (SRS FR-046–FR-048)
- [ ] Edits persisted immediately and reflected on report page
- [ ] Frontend: editable action item cards on post-meeting report page
- [ ] Frontend: timeline visualization on report page
- [ ] Unit tests: action item CRUD, validation
- [ ] Integration test: edit action item → verify persisted in MongoDB

---

## Day 13 — Unified Semantic Search (RAG)

**Goal:** Users can ask questions answered from both transcript chunks AND uploaded document chunks.

- [ ] Transcript chunking post-meeting: 200–400 tokens, 50-token overlap, `text-embedding-3-large` (SRS §4.4)
- [ ] Store transcript chunks in MongoDB Atlas Vector Index tagged `source: "transcript"` (SRS §8.3)
- [ ] `POST /ai/qa` — unified vector search across `source: "transcript"` AND `source: "document"` chunks simultaneously (SRS FR-057e)
- [ ] `POST /meetings/{id}/ask` — public endpoint calling `/ai/qa`
- [ ] Source attribution in every answer:
  - Transcript: speaker name + timestamp + excerpt
  - Document: filename + excerpt (SRS FR-057f)
- [ ] Max 20 queries per meeting per user (SRS RL-003)
- [ ] Frontend: post-meeting Q&A chat interface on report page
- [ ] Unit tests: vector search scoping, source attribution format
- [ ] Integration test: upload doc + run meeting → ask question → verify answer uses both sources

---

## Day 14 — Meeting History Dashboard

**Goal:** Users can browse and search all their meetings from a central dashboard.

- [ ] `GET /dashboard` — paginated meeting list scoped to authenticated user (host + invited meetings only, SRS FR-073)
- [ ] `GET /meetings/search?q=` — keyword and semantic search, scoped to user's own meetings only (SRS FR-073)
- [ ] Meeting cards: title, date, participants, duration, action item count (SRS FR-050)
- [ ] Each card links to the full post-meeting report page (SRS FR-051)
- [ ] Frontend: Dashboard UI with search bar, meeting cards, filter/sort controls
- [ ] Frontend: full Post-Meeting Report page (summary, decisions, action items, timeline, transcript accordion, Q&A panel)
- [ ] Frontend: navigation guard — `/meeting/:id` verifies participant authorization before rendering (SRS FR-074)
- [ ] Frontend: proper error page for ended/deleted/unauthorized meetings (SRS FR-078)
- [ ] Integration test: search returns only user's own meetings

---

## Completion Criteria

Phase 3 is complete when:
- Ending a meeting automatically generates a full report (title, summary, decisions, action items, timeline) within 60 seconds.
- Action items are editable by any participant and changes persist immediately.
- "What earnings did we report last quarter?" correctly searches both the meeting transcript and uploaded financial docs, returning an answer with source attribution.
- Dashboard shows only the authenticated user's meetings.
- Semantic search returns accurate results scoped to the user's meetings.
- All Phase 3 unit and integration tests pass.
