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

## Day 2 — Authentication
**Date:** 2026-03-26

### What was built
- User model (Pydantic schemas: UserCreate, UserLogin, GoogleAuthRequest, AuthResponse)
- `POST /auth/register` — bcrypt hashing + JWT issuance
- `POST /auth/login` — credential verification + JWT
- `POST /auth/google` — Google ID token verification + find-or-create user
- `GET /auth/me` — return current user from JWT (frontend hydration)
- Protected route dependency (`deps.py`) — extracts Bearer token, validates JWT, returns user
- React AuthContext with token persistence in localStorage
- Login page, Register page, Dashboard stub
- ProtectedRoute component — redirects to /login if unauthenticated

### Tech decisions
- **Direct `bcrypt` over `passlib`** — passlib has a known incompatibility with bcrypt 4.x on Python 3.12 (ValueError on password hashing)
- **Google tokeninfo endpoint** — simpler than using Google's Python SDK; validates ID tokens via `https://oauth2.googleapis.com/tokeninfo`
- **`/auth/me` endpoint** — enables frontend token hydration on page refresh without re-login
- **Google OAuth disabled by default** — button renders but is disabled until `GOOGLE_CLIENT_ID` is configured

### Blockers & fixes
- `passlib[bcrypt]` crashes on Python 3.12 with `ValueError: password cannot be longer than 72 bytes` → replaced with direct `bcrypt` module
- Backend needed `email-validator` for Pydantic's `EmailStr` type

### Verification
- 6 curl tests passed: register, login, /me (valid token), /me (no token → 403), duplicate email → 409, wrong password → 401
- Browser flow: `/dashboard` → redirect to `/login` → register → dashboard shows "Welcome, Ali Jaseem" → sign out → back to login

### UI Framework Overhaul
- Converted styling to **Tailwind CSS v4** + **shadcn/ui** components.
- Built a custom **Muted Tech Blue** aesthetic (blue-600 primary, sky-400 secondary, slate-50/950 backgrounds) matching modern SaaS design systems.
- Replaced manual component styles with generic utility classes and unified `<ThemeToggle>` and context.
- Verified smooth toggling between Dark and Light mode.

---
