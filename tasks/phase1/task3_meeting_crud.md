# Task: Meeting CRUD

## Objective

Implement full meeting lifecycle management: create rooms with shareable invite links, retrieve meeting details, delete meetings (host only), and a basic dashboard listing the user's meetings. This is the data foundation all AI features build on top of.

## Files

- Creates:
  - `backend/app/models/meeting.py` — Meeting MongoDB model
  - `backend/app/routers/meetings.py` — CRUD endpoints
  - `frontend/src/pages/Dashboard.tsx` — meeting list
  - `backend/tests/test_meetings.py`
- Modifies:
  - `backend/app/main.py` — register meetings router
  - `frontend/src/App.tsx` — add dashboard route
- Reads:
  - `docs/srs.md` — FR-001 to FR-008, §8.2 Meeting model, §7 API spec (Meetings section)

## Implementation Steps

1. Create `Meeting` model: `id`, `title`, `host_id`, `participant_ids`, `invite_list`, `state` (Created/Active/Ended/Processed), `invite_link`, `started_at`, `ended_at`, `duration_seconds`, `created_at`
2. `POST /meetings/create`: create meeting in `Created` state, generate unique invite link (UUID-based slug), add Arni (`"arni"`) to `participant_ids` (FR-008)
3. `GET /meetings/{id}`: return meeting details (participant-only via `get_current_user`)
4. `DELETE /meetings/{id}`: hard delete meeting + related data (host only — 403 if not host)
5. `POST /meetings/{id}/end`: transition state to `Ended` (host only)
6. Frontend Dashboard: fetch and display user's meetings as cards (title, date, state)

## Success Criteria

- [x] `POST /meetings/create` creates meeting with unique invite link; `"arni"` in `participant_ids`
- [x] `GET /meetings/{id}` returns meeting details to participants
- [x] `DELETE /meetings/{id}` succeeds for host; returns 403 for non-host
- [x] Dashboard displays user's meetings
- [x] All endpoints require valid JWT (401 otherwise)

## Testing Requirements

- Unit tests for: invite link uniqueness, state machine transitions
- Integration tests for: create → fetch → delete flow; non-host delete → 403

## Status

complete
