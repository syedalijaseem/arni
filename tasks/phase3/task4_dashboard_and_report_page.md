# Task: Meeting History Dashboard + Post-Meeting Report Page

## Objective

Build the meeting history dashboard and the full post-meeting report page. The dashboard shows only the authenticated user's meetings (scoped by host + invite list). The report page surfaces the AI-generated report (summary, decisions, action items, timeline, transcript) and the Q&A chat interface. Frontend navigation guards verify participant authorization before rendering any meeting or report content.

## Files

- Creates:
  - `frontend/src/pages/PostMeetingReport.tsx` — full report page
  - `frontend/src/components/QnAChat.tsx` — post-meeting Q&A chat interface
  - `frontend/src/pages/ErrorPage.tsx` — proper error page for unauthorized/expired meetings
  - `backend/tests/test_dashboard.py`
- Modifies:
  - `backend/app/routers/meetings.py` — add `GET /dashboard`, `GET /meetings/search?q=`
  - `frontend/src/App.tsx` — add report route, error page route; strengthen navigation guards
  - `frontend/src/pages/Dashboard.tsx` — full implementation with search, meeting cards
  - `frontend/src/components/ProtectedRoute.tsx` — add meeting participant check before rendering `/meeting/:id` and `/report/:id`
- Reads:
  - `docs/srs.md` — FR-049 to FR-056, FR-072 to FR-074, FR-078, §7 API Dashboard section
  - `docs/architecture.md` — §6 Unified RAG Pipeline diagram

## Implementation Steps

1. Add `GET /dashboard` to meetings router:
   - Returns meetings where `host_id == current_user.id` OR `current_user.email in invite_list`
   - Paginated (default page size: 20)
   - Each item includes: `id`, `title`, `started_at`, `duration_seconds`, `participant_count`, `action_item_count`, `state`
2. Add `GET /meetings/search?q=` to meetings router:
   - Keyword search across `title` and `summary` fields
   - Scoped to user's own meetings only (same filter as dashboard) (FR-073)
   - Returns same shape as dashboard items
3. Build `frontend/src/pages/Dashboard.tsx`:
   - Search bar (debounced, hits `/meetings/search`)
   - Meeting cards: title, date, duration, participant count, action item count, state badge
   - Click → navigate to `/report/:id` (for Processed meetings) or `/meeting/:id` (for Active)
4. Build `frontend/src/pages/PostMeetingReport.tsx`:
   - Sections: Summary, Key Decisions, Action Items (uses `ActionItemCard`), Timeline (uses `MeetingTimeline`), Full Transcript (accordion), Q&A Chat
5. Build `frontend/src/components/QnAChat.tsx`:
   - Input field + send button
   - POST to `/meetings/{id}/ask`
   - Render answer with source citations (transcript speaker+time, document filename)
   - Show "Rate limit reached" message after 20 queries
6. Update `frontend/src/components/ProtectedRoute.tsx`:
   - For `/meeting/:id` and `/report/:id`: after JWT check, call `GET /meetings/{id}` to verify user is on participant list
   - If 403/404: redirect to dashboard with error toast (FR-074)
7. Build `frontend/src/pages/ErrorPage.tsx`:
   - Shows for 403 (not authorized), 404 (not found), meeting Ended/Processed without access
   - Clear message + "Back to Dashboard" button (FR-078)

## Success Criteria

- [ ] Dashboard shows only meetings where the authenticated user is host or invited participant (FR-073)
- [ ] Search is scoped to the user's own meetings — cannot find other users' meetings
- [ ] Each meeting card displays: title, date, participants, duration, action item count
- [ ] Each card links to the correct report or meeting room page
- [ ] Post-meeting report page renders all sections: summary, decisions, action items, timeline, transcript
- [ ] Q&A chat returns answers with source citations; rate limit message shown after 20 queries
- [ ] Navigating to `/meeting/:id` as a non-participant redirects to dashboard with error message (FR-074)
- [ ] Navigating to a deleted or non-existent meeting shows the error page, not a raw 404 (FR-078)

## Testing Requirements

- Unit tests for:
  - `GET /dashboard`: returns only user's meetings; excludes meetings where user is neither host nor participant
  - `GET /meetings/search`: results scoped to user; does not return other users' meetings
- Integration tests for:
  - Create meeting as user A → log in as user B → `/dashboard` does not show user A's meeting
  - Non-participant navigates to meeting → 403 → redirected to dashboard
  - Q&A: 20 successful queries → 21st → rate limit message

## Status

pending
