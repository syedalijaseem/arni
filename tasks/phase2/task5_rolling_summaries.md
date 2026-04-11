# Task: Periodic Rolling Summaries + Context Coherence

## Objective

Implement the 10-minute rolling summary scheduler. Every 10 minutes during an active meeting, `postprocessing-service` fetches new transcript turns, calls `/ai/summarize`, and stores the updated summary in MongoDB. This summary is then included in every subsequent AI context build, keeping Arni coherent in meetings longer than 20 turns.

## Files

- Creates:
  - `backend/app/scheduler/__init__.py`
  - `backend/app/scheduler/summary_scheduler.py` — per-meeting 10-minute APScheduler job
  - `backend/tests/test_summary_scheduler.py`
- Modifies:
  - `backend/app/routers/ai.py` — add `POST /ai/summarize` endpoint
  - `backend/app/ai/context_manager.py` — ensure `build_context()` reads from the latest rolling summary
  - `backend/app/routers/meetings.py` — start scheduler job on `meeting.started`; stop job on `meeting.ended`
  - `backend/app/config.py` — add `AUTO_SUMMARY_INTERVAL_MINUTES=10`
  - `backend/requirements.txt` — add `apscheduler`
- Reads:
  - `docs/srs.md` — FR-025, FR-026, FR-027, §8.8 Meeting Summary (Rolling) model, §9.7 Configurability table
  - `docs/architecture.md` — §11 Rolling Auto-Summary Flow diagram

## Implementation Steps

1. Add `AUTO_SUMMARY_INTERVAL_MINUTES=10` to `backend/app/config.py`
2. Add `POST /ai/summarize` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id}`
   - Fetch: latest rolling summary from MongoDB + all transcript turns since last summary
   - If no new turns: skip, return `{"skipped": true}`
   - Call Claude: "Given this previous summary and new transcript turns, write an updated concise meeting summary."
   - Store new `MeetingSummary` record in MongoDB (SRS §8.8)
   - Publish `summary.updated` event to Redis
   - Return `{"summary_text": str}`
3. Create `backend/app/scheduler/summary_scheduler.py`:
   - Uses APScheduler `AsyncIOScheduler`
   - `start_for_meeting(meeting_id)` — schedules `POST /ai/summarize` every N minutes
   - `stop_for_meeting(meeting_id)` — cancels the job
   - Interval is read from `AUTO_SUMMARY_INTERVAL_MINUTES` config
4. Update `backend/app/routers/meetings.py`:
   - On `meeting.started` event: call `summary_scheduler.start_for_meeting(meeting_id)`
   - On `meeting.ended` event: call `summary_scheduler.stop_for_meeting(meeting_id)`
5. Verify `backend/app/ai/context_manager.py` `build_context()`:
   - Fetches the most recent `MeetingSummary` record for the meeting
   - If none exists, uses empty string for summary portion
   - Combines with last N transcript turns (N = `AI_CONTEXT_WINDOW`)
6. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] A rolling summary is generated every 10 minutes in active meetings (configurable via env var)
- [ ] Summary generation is skipped if no new transcript turns exist since last summary
- [ ] Each new summary is stored as a new `MeetingSummary` document in MongoDB
- [ ] `summary.updated` event published on every new summary
- [ ] `context_manager.build_context()` correctly reads the latest rolling summary
- [ ] Scheduler job starts on `meeting.started` and stops on `meeting.ended`
- [ ] Simulated 30-minute meeting: 3 summaries generated (at 10, 20, 30 min)
- [ ] AI responses in a long meeting reference content from the rolling summary, not just recent turns

## Testing Requirements

- Unit tests for:
  - `POST /ai/summarize`: skips when no new turns; generates and stores summary when new turns exist
  - `context_manager.build_context()`: uses latest summary + correct number of turns; handles missing summary gracefully
  - Scheduler: `start_for_meeting()` creates job; `stop_for_meeting()` cancels it; interval is configurable
- Integration tests for:
  - Simulate 10 minutes of transcript turns → trigger summarize → assert MeetingSummary record in MongoDB
  - Next context build includes the stored summary text

## Status

pending
