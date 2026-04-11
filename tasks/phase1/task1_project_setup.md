# Task: Project Setup

## Objective

Bootstrap the full development environment: monorepo layout, FastAPI backend, MongoDB connection, React + TypeScript frontend, and Docker Compose orchestrating all four services (frontend, backend, mongodb, redis). Verify end-to-end connectivity before any feature work begins.

## Files

- Creates:
  - `backend/` — FastAPI project scaffold
  - `backend/app/main.py` — FastAPI app with health endpoint + CORS
  - `backend/app/config.py` — environment config (MongoDB URI, etc.)
  - `backend/app/database.py` — MongoDB connection utility
  - `backend/requirements.txt`
  - `backend/Dockerfile`
  - `frontend/` — React + TypeScript scaffold (Vite + React Router)
  - `frontend/Dockerfile`
  - `docker-compose.yml` — services: frontend, backend, mongodb, redis
  - `docs/` — project documentation directory
  - `.gitignore`
- Modifies: N/A
- Reads:
  - `docs/srs.md` — §5 Technology Stack, §2.4 Operating Environment
  - `docs/architecture.md` — §1 System Architecture Diagram

## Implementation Steps

1. Create monorepo structure: `/frontend`, `/backend`, `/docs`
2. Scaffold FastAPI backend: `app/main.py` with `GET /health` → `{"status": "ok"}`
3. Add CORS middleware permitting frontend origin
4. Create MongoDB connection utility in `app/database.py` using `motor` (async)
5. Create `app/config.py` reading all secrets from environment variables
6. Scaffold React + TypeScript frontend using Vite; add React Router
7. Write `docker-compose.yml` with four services: `frontend` (5173), `backend` (8000), `mongodb` (27017), `redis` (6379)
8. Write `backend/Dockerfile` and `frontend/Dockerfile`
9. Verify: `docker compose up` → frontend loads → `/health` returns 200 → MongoDB ping succeeds

## Success Criteria

- [x] `docker compose up` starts all four services without errors
- [x] `GET /health` returns `{"status": "ok"}` with HTTP 200
- [x] Backend successfully connects to MongoDB on startup
- [x] Frontend is served at `http://localhost:5173`
- [x] Frontend can reach backend health endpoint
- [x] No secrets committed to source control

## Testing Requirements

- Unit tests for: MongoDB connection utility (mock motor client)
- Integration tests for: `GET /health` endpoint returns 200

## Status

complete
