# Task: Daily.co WebRTC Integration

## Objective

Integrate Daily.co to provision WebRTC meeting rooms programmatically, generate per-participant meeting tokens, and render multi-participant audio/video in the frontend. Arni's backend bot joins the room as a Daily.co participant (deferred to Day 5 and implemented alongside Deepgram).

## Files

- Creates:
  - `backend/app/utils/daily.py` — Daily.co REST API client (create room, generate token)
  - `frontend/src/pages/MeetingRoom.tsx` — meeting room UI with Daily.co SDK
  - `backend/tests/test_daily.py`
- Modifies:
  - `backend/app/routers/meetings.py` — provision Daily.co room on `POST /meetings/create`; generate token on join
  - `backend/app/config.py` — add `DAILY_API_KEY`, `DAILY_API_URL`
  - `backend/requirements.txt` — add `httpx`
  - `frontend/package.json` — add `@daily-co/daily-js`
- Reads:
  - `docs/srs.md` — FR-006 to FR-008, FR-012 (speaker identification setup)
  - `docs/architecture.md` — §1 system diagram (Daily.co node)

## Implementation Steps

1. Create `backend/app/utils/daily.py`:
   - `create_room(meeting_id) → room_url` — POST to Daily.co API
   - `create_token(room_name, user_id, is_owner) → token` — generate meeting access token
2. On `POST /meetings/create`: call `daily.create_room()`, store `room_url` on Meeting
3. On participant join: call `daily.create_token()`, return token to frontend
4. Frontend `MeetingRoom.tsx`: join room using `@daily-co/daily-js`, render participant tiles
5. Verify: two browser tabs can join the same room and hear each other

## Success Criteria

- [x] Daily.co room created automatically on meeting creation
- [x] Participants receive valid tokens for their room
- [x] Multiple participants can join and hear each other in the browser
- [x] `DAILY_API_KEY` read from environment — never hardcoded

## Testing Requirements

- Unit tests for: `create_room()` and `create_token()` with mocked Daily.co API responses
- Integration tests for: token returned on join; room URL stored in Meeting document

## Status

complete
