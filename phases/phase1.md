# Phase 1: Foundation (Days 1–5)

## Objective

Establish the complete project infrastructure: monorepo, backend API, database, frontend scaffold, containerization, authentication, meeting CRUD, Daily.co video rooms, and real-time Deepgram transcription.

Phase 1 is the prerequisite for all AI work. Every component built here is consumed by Phase 2.

## Owner

planner

## Status

complete

---

## Day 1 — Project Setup

**Goal:** Working local development environment with all services running.

- [x] Monorepo structure: `/frontend`, `/backend`, `/docs`
- [x] FastAPI backend scaffold with health endpoint + CORS
- [x] MongoDB connection utility with environment config
- [x] React + TypeScript frontend scaffold (Vite + React Router)
- [x] Docker Compose: `frontend`, `backend`, `mongodb`, `redis`
- [x] Verify end-to-end: frontend → backend health check → MongoDB ping through Docker

> Redis included now even though not used until Day 8+. Zero setup cost, saves time later.

---

## Day 2 — Authentication

**Goal:** Secure, JWT-based auth with Google OAuth, protected routes front and back.

- [x] User data model in MongoDB
- [x] `POST /auth/register` — email/password registration
- [x] `POST /auth/login` — JWT token issuance
- [x] `POST /auth/google` — Google OAuth flow
- [x] Protected route middleware (JWT verification)
- [x] Frontend: login/register pages, auth context, token storage
- [x] Route guards on frontend

---

## Day 3 — Meeting CRUD

**Goal:** Full meeting lifecycle management — create, read, delete, with invite links.

- [x] Meeting data model in MongoDB
- [x] `POST /meetings/create` — create room, generate invite link
- [x] `GET /meetings/{id}` — fetch meeting details
- [x] `DELETE /meetings/{id}` — delete meeting (owner only)
- [x] Frontend: create meeting flow, invite link copy/share
- [x] Basic dashboard page listing user's meetings

---

## Day 4 — Daily.co Integration

**Goal:** WebRTC video rooms with multi-participant audio support.

- [x] Daily.co API: create room programmatically
- [x] Backend: generate Daily.co meeting tokens per participant
- [x] Frontend: join meeting room via Daily.co SDK
- [x] Audio/video tile rendering in meeting UI
- [x] Arni bot joins as a Daily.co participant (backend-side) — deferred to Day 5 (implemented alongside Deepgram)
- [x] Verify: multiple participants can join and hear each other

---

## Day 5 — Real-Time Transcription

**Goal:** Live speech-to-text with per-speaker labeling streamed to the frontend.

- [x] Deepgram streaming SDK integration on backend
- [x] Route participant audio tracks → Deepgram per-track
- [x] Speaker labeling via Daily.co track ID → user mapping
- [x] Transcript storage in MongoDB (speaker_id, timestamp, text)
- [x] WebSocket: stream live transcript to frontend
- [x] Frontend: live transcript panel in meeting room UI

---

## Completion Criteria

All Day 1–5 items checked. Phase 1 is complete when:
- A user can register, create a meeting, join via Daily.co, speak, and see their live transcript in the UI.
- All services run cleanly via `docker compose up`.
