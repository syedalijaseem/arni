# Arni — Build Journal

A daily devlog tracking decisions, progress, and lessons learned.

---

## Day 1 — Project Scaffold
**Date:** 2026-03-25

### What was built
- Monorepo structure: `backend/`, `frontend/`, `docs/`
- FastAPI backend with health endpoint, CORS, and async MongoDB connection (Motor)
- React + TypeScript frontend (Vite 8) with React Router and API proxy
- Docker Compose with 4 services: backend, frontend, MongoDB 7, Redis 7
- Landing page with live system status card (API + Database health)
- Dark-mode design system (Inter font, CSS custom properties)
- 17-day development roadmap

### Tech decisions
- **MongoDB over Supabase/Pinecone** — document model fits transcript chunks naturally, Atlas Vector Search handles RAG at MVP scale without a second database
- **Redis included early** — zero cost in Compose, avoids setup tax when implementing event bus (Day 9)
- **Vite proxy** — `/api/*` routes to `backend:8000`, avoiding CORS complexity in development
- **`network: host` for Docker builds** — needed because Docker DNS resolution failed in the build environment

### Blockers & fixes
- `npx create-vite` was interactive and timed out → user installed manually
- Docker build failed with DNS resolution errors → fixed with `network: host` in build config
- Frontend container had no port mapping (created while port 5173 was occupied) → fixed with `--force-recreate`

### Verification
- `curl localhost:8000/health` → `{"status": "healthy", "database": "connected"}`
- Browser at `localhost:5173` → landing page shows API Online + Database Connected
- All 4 containers healthy

---
