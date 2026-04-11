# Task: Authentication (JWT + Google OAuth)

## Objective

Implement a complete authentication system: email/password registration and login with JWT tokens, Google OAuth, protected route middleware on the backend, and auth context + route guards on the frontend.

## Files

- Creates:
  - `backend/app/models/user.py` — User MongoDB model
  - `backend/app/routers/auth.py` — register, login, google OAuth endpoints
  - `backend/app/utils/auth.py` — JWT creation/verification, password hashing
  - `backend/app/deps.py` — `get_current_user` FastAPI dependency
  - `frontend/src/context/AuthContext.tsx` — auth state, token storage
  - `frontend/src/pages/Login.tsx`
  - `frontend/src/pages/Register.tsx`
  - `frontend/src/components/ProtectedRoute.tsx`
  - `backend/tests/test_auth.py`
- Modifies:
  - `backend/app/main.py` — register auth router
  - `backend/app/config.py` — add `JWT_SECRET`, `JWT_EXPIRE_HOURS=24`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
  - `backend/requirements.txt` — add `python-jose`, `passlib[bcrypt]`, `python-multipart`
  - `frontend/src/App.tsx` — add auth routes, wrap with AuthContext
- Reads:
  - `docs/srs.md` — FR-057 to FR-060, NFR-014 to NFR-018, §8.1 User model

## Implementation Steps

1. Create `User` model: `id`, `email`, `name`, `password_hash`, `auth_provider`, `created_at`
2. `POST /auth/register`: validate email uniqueness, hash password (bcrypt cost ≥ 10), return JWT
3. `POST /auth/login`: verify credentials, return JWT (expires 24 hours)
4. `POST /auth/google`: exchange OAuth code, upsert user, return JWT
5. `get_current_user` FastAPI dependency: decode JWT from `Authorization: Bearer` header
6. Frontend `AuthContext`: store JWT in `localStorage`, expose `user`, `isAuthenticated`, `login()`, `logout()`
7. `ProtectedRoute`: redirect to `/login` if `!isAuthenticated`

## Success Criteria

- [x] `POST /auth/register` creates user, returns JWT
- [x] `POST /auth/login` validates credentials, returns JWT
- [x] `POST /auth/google` authenticates via Google OAuth
- [x] Protected routes return 401 without a valid JWT
- [x] JWT expires after 24 hours
- [x] Passwords hashed with bcrypt (cost ≥ 10) — never stored plain
- [x] Frontend redirects unauthenticated users to `/login`
- [x] `JWT_SECRET` read from environment — never hardcoded

## Testing Requirements

- Unit tests for: JWT creation/verification, password hashing, token expiry
- Integration tests for: register → login → access protected route; invalid token → 401

## Status

complete
