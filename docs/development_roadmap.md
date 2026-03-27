# Arni — Development Roadmap

## Phase 1: Foundation (Days 1–5)

### Day 1 — Project Setup

- [x] Monorepo structure: `/frontend`, `/backend`, `/docs`
- [x] FastAPI backend scaffold with health endpoint + CORS
- [x] MongoDB connection utility with environment config
- [x] React + TypeScript frontend scaffold (Vite 8 + React Router)
- [x] Docker Compose: `frontend`, `backend`, `mongodb`, `redis`
- [x] Verify end-to-end: frontend → backend health check → MongoDB ping through Docker

> [!NOTE]
> Redis is included now even though it won't be used until the real-time event bus (Day 8+). Zero cost to include, saves setup time later.

---

### Day 2 — Authentication

- [x] User data model in MongoDB
- [x] `POST /auth/register` — email/password registration
- [x] `POST /auth/login` — JWT token issuance
- [x] `POST /auth/google` — Google OAuth flow
- [x] Protected route middleware (JWT verification)
- [x] Frontend: login/register pages, auth context, token storage
- [x] Route guards on frontend

---

### Day 3 — Meeting CRUD

- [x] Meeting data model in MongoDB
- [x] `POST /meetings/create` — create room, generate invite link
- [x] `GET /meetings/{id}` — fetch meeting details
- [x] `DELETE /meetings/{id}` — delete meeting (owner only)
- [x] Frontend: create meeting flow, invite link copy/share
- [x] Basic dashboard page listing user's meetings

---

http://localhost:5173/meeting/c_WoMcGb

### Day 4 — Daily.co Integration

- [x] Daily.co API: create room programmatically
- [x] Backend: generate Daily.co meeting tokens per participant
- [x] Frontend: join meeting room via Daily.co SDK
- [x] Audio/video tile rendering in meeting UI
- [ ] Arni bot joins as a Daily.co participant (backend-side) — **Deferred to Day 5** (implemented alongside Deepgram integration)
- [x] Verify: multiple participants can join and hear each other (requires Daily.co API key)

---

### Day 5 — Real-Time Transcription

- [ ] Deepgram streaming SDK integration on backend
- [ ] Route participant audio tracks → Deepgram per-track
- [ ] Speaker labeling via Daily.co track ID → user mapping
- [ ] Transcript storage in MongoDB (speaker_id, timestamp, text)
- [ ] WebSocket: stream live transcript to frontend
- [ ] Frontend: live transcript panel in meeting room UI

---

## Phase 2: AI Core (Days 6–10)

### Day 6 — Wake Word Detection

- [ ] Detect "Hey Arni" + command in transcript stream
- [ ] Parse command intent from wake phrase
- [ ] Trigger AI request pipeline on detection
- [ ] 10-second cooldown between triggers (rate limiting)

---

### Day 7 — AI Response Generation

- [ ] Claude API integration
- [ ] Context strategy: rolling summary + last 20 turns
- [ ] AI response queue (sequential processing)
- [ ] `POST /meetings/{id}/ai-respond` internal endpoint

---

### Day 8 — Voice Response (TTS)

- [ ] ElevenLabs TTS integration
- [ ] Convert AI text response → audio
- [ ] Inject audio into meeting via Daily.co bot track
- [ ] Audio feedback loop prevention (tag AI audio, exclude from STT)
- [ ] Frontend: AI status indicator (Listening → Thinking → Speaking)

---

### Day 9 — Interrupt Handling + Event Bus

- [ ] VAD: detect human speech during AI playback → stop AI audio
- [ ] Redis Pub/Sub: wire up event bus for audio/wake/AI/meeting events
- [ ] Replace any direct coupling with event-driven flow

---

### Day 10 — Periodic Summaries + Context

- [ ] Rolling summary generation every 10 minutes
- [ ] Store rolling summaries in meeting document
- [ ] Feed summaries into AI context window
- [ ] Verify: AI responses stay coherent in 30+ minute meetings

---

## Phase 3: Post-Meeting Intelligence (Days 11–14)

### Day 11 — Post-Meeting Processing

- [ ] Meeting end event → trigger processing pipeline
- [ ] Generate: title, summary, key decisions, action items
- [ ] AI safety: extract only explicitly stated decisions
- [ ] Store structured report in MongoDB

---

### Day 12 — Editable Action Items

- [ ] Action item data model
- [ ] CRUD endpoints for action items
- [ ] Frontend: editable action items on report page
- [ ] Meeting timeline generation (topic segmentation)

---

### Day 13 — Semantic Search (RAG)

- [ ] Transcript chunking strategy
- [ ] Embedding generation (per chunk)
- [ ] Store embeddings in MongoDB Atlas vector index
- [ ] `POST /meetings/{id}/ask` — vector search → LLM answer
- [ ] Source attribution in responses

---

### Day 14 — Meeting History Dashboard

- [ ] `GET /dashboard` — paginated meeting list
- [ ] `GET /meetings/search?q=` — search across meetings
- [ ] Frontend: dashboard UI (meetings, summaries, participants, durations)
- [ ] Frontend: post-meeting report detail page
- [ ] Post-meeting Q&A chat interface

---

## Phase 4: Polish + Deploy (Days 15–17)

### Day 15 — Frontend Polish

- [ ] Landing page
- [ ] Responsive design pass
- [ ] Loading states, error handling, toast notifications
- [ ] Meeting room UI refinements

---

### Day 16 — Backend Hardening

- [ ] Rate limiting (wake word cooldown, max AI responses, query limits)
- [ ] Error handling: STT/TTS/LLM failure fallbacks
- [ ] Reconnection logic for user disconnects
- [ ] Input validation and security audit

---

### Day 17 — Containerize + Deploy

- [ ] Production Dockerfiles (multi-stage builds)
- [ ] Environment config for production
- [ ] Deploy backend to Fly.io
- [ ] Deploy frontend to Vercel
- [ ] MongoDB Atlas production cluster
- [ ] Smoke test full flow in production

---

## What's Next (Post-MVP)

Once the 17-day MVP is complete, the following are natural next steps from [Section 15 of the project outline](file:///home/syedalijaseem/arni/docs/project_outline.md#L632):

| Priority | Feature                                                        | Why                                    |
| -------- | -------------------------------------------------------------- | -------------------------------------- |
| 1        | **Meeting analytics** — speaking time, engagement, sentiment   | High user value, data already captured |
| 2        | **Observability** — OpenTelemetry + Prometheus + Grafana       | Needed before scaling                  |
| 3        | **Proactive AI participation** — AI speaks without being asked | Differentiator feature                 |
| 4        | **Zoom/Meet/Teams integration**                                | Largest growth unlock                  |
| 5        | **Slack/Notion integrations**                                  | Action item follow-through             |
| 6        | **Mobile app**                                                 | Broader accessibility                  |
