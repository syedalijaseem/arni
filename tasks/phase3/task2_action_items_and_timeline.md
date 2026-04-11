# Task: Editable Action Items + Meeting Timeline

## Objective

Make AI-generated action items editable by all meeting participants. Build the `PATCH` endpoint for editing description, assignee, and deadline. Separately, implement the `/ai/timeline` endpoint that generates a timestamped topic segmentation timeline, and surface both on the post-meeting report page.

## Files

- Creates:
  - `backend/app/models/action_item.py` — ActionItem MongoDB model (if not already created in task1)
  - `frontend/src/components/ActionItemCard.tsx` — editable action item card
  - `frontend/src/components/MeetingTimeline.tsx` — timeline visualization
  - `backend/tests/test_action_items.py`
- Modifies:
  - `backend/app/routers/meetings.py` — add `PATCH /meetings/{id}/action-items/{item_id}`
  - `backend/app/routers/ai.py` — add `POST /ai/timeline`
  - `backend/app/postprocessing/processor.py` — call `/ai/timeline` in pipeline, store timeline on Meeting
  - `frontend/src/pages/PostMeetingReport.tsx` — render action items + timeline
- Reads:
  - `docs/srs.md` — FR-041 to FR-048, §8.7 Action Item model, §7 API spec (PATCH endpoint)
  - `docs/architecture.md` — §10 Post-Meeting Processing sequence diagram

## Implementation Steps

1. Ensure `ActionItem` model exists: `id`, `meeting_id`, `description`, `assignee`, `deadline`, `is_edited`, `created_at`
2. Add `POST /ai/timeline` to `backend/app/routers/ai.py`:
   - Body: `{meeting_id, transcript_text}`
   - Prompt: "Segment this meeting transcript into topics with timestamps. Return JSON array of `{timestamp, topic}`."
   - Return `{"timeline": list[{timestamp, topic}]}`
3. Update `processor.py`: call `/ai/timeline` → store `timeline[]` array on Meeting document
4. Add `PATCH /meetings/{id}/action-items/{item_id}` to meetings router:
   - Body: any subset of `{description, assignee, deadline}`
   - Any authenticated meeting participant may edit (not host-only) (FR-046)
   - Set `is_edited: true` on first edit
   - Persist immediately; return updated action item
5. Create `frontend/src/components/ActionItemCard.tsx`:
   - Inline editable fields for description, assignee, deadline
   - Saves on blur/enter; shows "Edited" badge if `is_edited: true`
6. Create `frontend/src/components/MeetingTimeline.tsx`:
   - Vertical timeline with timestamp + topic label
7. Integrate both into `PostMeetingReport.tsx`

## Success Criteria

- [ ] Action items editable by any authenticated meeting participant (not host-only)
- [ ] Edit persists immediately and is reflected if page is refreshed
- [ ] `is_edited` flag set to `true` after first manual edit
- [ ] Host editing works the same as participant editing
- [ ] Meeting timeline generated with at least one timestamped topic segment
- [ ] Timeline stored on Meeting document under `timeline[]`
- [ ] Frontend report page shows editable action item cards and topic timeline

## Testing Requirements

- Unit tests for:
  - `PATCH` endpoint: valid edit persists; `is_edited` becomes `true`; non-participant gets 403
  - `PATCH` with partial body: only provided fields updated; others unchanged
  - `/ai/timeline`: returns valid array of `{timestamp, topic}` objects
- Integration tests for:
  - Edit action item → fetch meeting → assert updated fields in response
  - Timeline generated during post-processing → stored on Meeting document

## Status

pending

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
