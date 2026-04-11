# Task: Meeting Access Control

## Objective

Implement the full meeting access control model defined in SRS §3.18 (FR-058–FR-074). This includes:
- **Invite-only access**: only users on the invite list or the host may join
- **Waiting room (lobby)**: invited participants wait until the host admits them
- **Host-only controls**: end meeting, remove participants, mute/remove Arni, transfer host role
- **Grace period**: auto-end meeting if host disconnects for 10+ minutes
- **Privacy**: meetings not discoverable; dashboard and search scoped to user's own meetings
- **Arni joins on creation**: not on first participant join (FR-073)

This task must be implemented before fact-checking and reasoning tasks, because it changes the meeting lifecycle and bot initialization sequence.

## Files

- Creates:
  - `backend/app/lobby/__init__.py`
  - `backend/app/lobby/lobby_manager.py` — Redis-backed waiting room state (ephemeral, never persisted to MongoDB)
  - `backend/app/lobby/grace_period.py` — host disconnect 10-minute grace period timer
  - `backend/tests/test_lobby.py`
  - `backend/tests/test_access_control.py`
- Modifies:
  - `backend/app/models/meeting.py` — add `invite_list: list[str]`, `host_grace_period_until: datetime | None`, confirm `participant_ids` includes `"arni"` from creation
  - `backend/app/routers/meetings.py` — add invite, remove participant, waiting-room, admit, reject, transfer-host endpoints; enforce invite-only join; scope dashboard/search to user's meetings; add host-only middleware to end/delete
  - `backend/app/bot/arni_bot.py` — trigger Arni bot join on meeting **creation** (not on first participant join)
  - `backend/app/deps.py` — add `require_host` dependency; add `require_participant` dependency that checks invite_list
  - `frontend/src/pages/MeetingRoom.tsx` — add waiting room lobby UI; show grace period countdown
  - `frontend/src/components/ProtectedRoute.tsx` — check invite_list membership before rendering meeting room
  - `frontend/src/pages/ErrorPage.tsx` — show "You are not authorized to join this meeting" (FR-060)
  - `backend/app/config.py` — add `HOST_GRACE_PERIOD_MINUTES=10`
- Reads:
  - `docs/srs.md` — FR-058 through FR-074, §7 Meetings API (all new endpoints), §8.2 Meeting model, §4.6 Event Bus Schema (participant.* and host.* events)
  - `docs/architecture.md` — §7 Event Bus Schema, §8 Meeting Initialization Sequence

## Implementation Steps

1. **Update `Meeting` model** (`backend/app/models/meeting.py`):
   - Add `invite_list: list[str]` — emails of authorized participants
   - Add `host_grace_period_until: datetime | None = None`
   - Confirm `participant_ids` list is initialized with `["arni"]` in the service layer

2. **Arni joins on creation** — update `POST /meetings/create` handler:
   - After creating the Meeting document, immediately call `arni_bot.start(meeting_id)` so Arni is in `participant_ids` from creation (FR-073)

3. **Create `backend/app/lobby/lobby_manager.py`**:
   - `add_to_waiting_room(meeting_id, user_id)` — stores in Redis hash `lobby:{meeting_id}` (TTL: 24h)
   - `get_waiting_room(meeting_id) → list[user_id]`
   - `remove_from_waiting_room(meeting_id, user_id)`
   - `clear_waiting_room(meeting_id)` — called on meeting end

4. **Add `require_host` dependency** (`backend/app/deps.py`):
   - Fetch meeting, check `current_user.id == meeting.host_id`; raise 403 if not

5. **Add `require_participant` dependency** (`backend/app/deps.py`):
   - Check `current_user.email in meeting.invite_list OR current_user.id == meeting.host_id`
   - If not: raise 403 with body `{"detail": "You are not authorized to join this meeting"}` (FR-060)

6. **Add new endpoints to `backend/app/routers/meetings.py`**:
   - `POST /meetings/{id}/invite` (host only): add email to `invite_list`; publish `participant.invited`
   - `DELETE /meetings/{id}/participants/{user_id}` (host only): remove from `participant_ids`; publish `participant.removed`; close their WebSocket session
   - `GET /meetings/{id}/waiting-room` (host only): return `lobby_manager.get_waiting_room(meeting_id)` with user metadata
   - `POST /meetings/{id}/admit/{user_id}` (host only): move user from waiting room to `participant_ids`; publish `participant.admitted` (with `admitted_by`)
   - `POST /meetings/{id}/reject/{user_id}` (host only): remove from waiting room; publish `participant.rejected`; WS message to rejected user
   - `POST /meetings/{id}/transfer-host` (host only): update `meeting.host_id`; publish `host.transferred`

7. **Enforce invite-only join** — on `GET /meetings/{id}` and WebSocket join:
   - Call `require_participant` — 403 if not on invite list
   - If invited but meeting is Active: place user in waiting room via `lobby_manager.add_to_waiting_room()`; return `{"status": "waiting"}` and WS message host

8. **Host grace period** (`backend/app/lobby/grace_period.py`):
   - `on_host_disconnect(meeting_id, host_id)`: set `host_grace_period_until = now + 10min`; start async countdown
   - If host reconnects before expiry: cancel countdown, clear `host_grace_period_until`
   - If expiry reached: call meeting end flow; publish `meeting.auto_ended` with `reason: "host_timeout"`
   - Broadcast grace period countdown to remaining participants via WebSocket

9. **Frontend waiting room**: `MeetingRoom.tsx` — if WebSocket returns `{"status": "waiting"}`, show lobby screen: "Waiting for host to admit you..."; listen for `participant.admitted` or `participant.rejected` events

10. **Frontend error page**: `ErrorPage.tsx` — show 403 message "You are not authorized to join this meeting" with Back to Dashboard button

11. **Scope dashboard/search**: `GET /dashboard` and `GET /meetings/search` must filter by `host_id == user OR user.email in invite_list` (FR-068)

12. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] Arni is added to `participant_ids` when the meeting is first **created** (FR-073)
- [ ] Users not on `invite_list` receive HTTP 403 with correct message when attempting to join (FR-060)
- [ ] Invited users are placed in the waiting room; host sees them in `GET /meetings/{id}/waiting-room` (FR-070)
- [ ] Host admits user → user moves from waiting room to `participant_ids` → `participant.admitted` event published with `admitted_by` (FR-071)
- [ ] Host rejects user → `participant.rejected` event published → rejected user sees "You were not admitted to this meeting" (FR-072)
- [ ] `POST /meetings/{id}/invite` adds email to `invite_list`; `participant.invited` event published (FR-061)
- [ ] `DELETE /meetings/{id}/participants/{user_id}` removes participant immediately; `participant.removed` event published (FR-062)
- [ ] `POST /meetings/{id}/transfer-host` updates `host_id`; `host.transferred` event published (FR-066)
- [ ] Host disconnect → 10-minute grace period begins → countdown visible to participants → meeting auto-ends if host does not return → `meeting.auto_ended` published (FR-065)
- [ ] Dashboard returns only meetings where user is host or in `invite_list` (FR-068)
- [ ] Meetings are not discoverable via search by non-participants (FR-067)
- [ ] Waiting room state is stored in Redis only — never in MongoDB

## Testing Requirements

- Unit tests for:
  - `lobby_manager`: add/get/remove/clear operations; Redis TTL set correctly
  - `require_participant`: authorized user passes; unauthorized user raises 403 with correct message
  - `require_host`: host passes; participant raises 403
  - Grace period: timer fires at correct time; canceled on host reconnect
  - Invite list: email match is case-insensitive
- Integration tests for:
  - Full join flow: invited user → waiting room → admitted → in meeting
  - Rejected user → sees rejection message
  - Non-invited user → 403 at join attempt
  - Transfer host → old host loses host permissions; new host gains them
  - Host disconnect → auto-end after 10 min (test with shortened TTL)
  - Dashboard: user A's meetings not visible to user B

## Status

complete

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
