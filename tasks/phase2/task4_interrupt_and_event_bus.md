# Task: Interrupt Handling + Redis Event Bus

## Objective

Implement VAD-based interrupt handling (human speech during AI playback stops Arni immediately) and wire up the full Redis Pub/Sub event bus. All inter-service communication must move from direct coupling to event-driven flow. Every event published must conform strictly to the schemas defined in SRS §4.6.

## Files

- Creates:
  - `backend/app/events/__init__.py`
  - `backend/app/events/publisher.py` — typed Redis event publishers for all event types
  - `backend/app/events/subscriber.py` — Redis subscriber base class
  - `backend/app/events/schemas.py` — Pydantic schemas for every event type (enforce §4.6)
  - `backend/app/vad/vad_handler.py` — VAD interrupt detection
  - `backend/tests/test_event_schemas.py`
  - `backend/tests/test_vad.py`
- Modifies:
  - `backend/app/bot/arni_bot.py` — integrate VAD; stop audio on human speech detection
  - `backend/app/ai/ai_service.py` — publish events via `publisher.py` instead of direct calls
  - `backend/app/routers/transcripts.py` — publish `transcript.created` via publisher
  - `backend/app/bot/wake_word.py` — publish `wake.detected` via publisher
  - `backend/app/routers/meetings.py` — publish `meeting.started`, `meeting.ended` via publisher
  - `backend/app/config.py` — confirm `REDIS_URL` is set
- Reads:
  - `docs/srs.md` — FR-028 to FR-030 (interrupt), §4.6 Event Bus Schema (all 17 event types)
  - `docs/architecture.md` — §7 Event Bus Schema, live meeting sequence diagram (interrupt scenario)

## Implementation Steps

1. Create `backend/app/events/schemas.py` — Pydantic models for every event in SRS §4.6:
   - `TranscriptCreatedEvent`, `WakeDetectedEvent`, `AIRequestedEvent`, `AIRespondedEvent`
   - `AIStateChangedEvent`, `FactCheckedEvent`, `MeetingStartedEvent`, `MeetingEndedEvent`
   - `MeetingProcessedEvent`, `MeetingAutoEndedEvent`, `SummaryUpdatedEvent`, `DocumentUploadedEvent`
   - `ParticipantInvitedEvent`, `ParticipantAdmittedEvent` (includes `admitted_by`), `ParticipantRemovedEvent`, `ParticipantRejectedEvent`
   - `HostTransferredEvent`
   - All fields must be required; no extra fields allowed (`model_config = ConfigDict(extra="forbid")`)
2. Create `backend/app/events/publisher.py`:
   - One typed publish function per event type, e.g. `publish_transcript_created(...)`, `publish_wake_detected(...)`
   - Each validates against the Pydantic schema before publishing to Redis
   - Channel naming: `arni:{meeting_id}:{event_type}`
3. Create `backend/app/events/subscriber.py`:
   - Base async subscriber class; real-time-gateway uses this to forward events to WebSocket clients
4. Create `backend/app/vad/vad_handler.py`:
   - `on_participant_speech_detected(meeting_id)` — called by Daily.co VAD callback
   - If Arni is in `speaking` state: call `audio_injection.stop()`, publish `ai.state_changed` (listening)
5. Integrate VAD into `backend/app/bot/arni_bot.py`:
   - Register Daily.co VAD callback → `vad_handler.on_participant_speech_detected()`
6. Migrate all existing direct event calls in transcripts, wake_word, meetings routers to use `publisher.py`
7. Write failing tests first (TDD), then implement until tests pass

## Success Criteria

- [ ] Human speech during AI playback immediately stops Arni's audio (FR-028–FR-030)
- [ ] After interrupt, AI state transitions back to Listening and indicator updates in UI
- [ ] All 17 event types have Pydantic schemas with `extra="forbid"` — no undocumented fields can be published
- [ ] `fact.checked` and `participant.rejected` event schemas implemented and validated
- [ ] `participant.admitted` schema includes `admitted_by` field (SRS §4.6)
- [ ] All inter-service events published via `publisher.py` (no raw `redis.publish()` calls outside publisher)
- [ ] `transcript.created` published for every final transcript
- [ ] `wake.detected` published on every wake phrase detection
- [ ] `meeting.started` and `meeting.ended` published at correct lifecycle transitions
- [ ] WebSocket gateway forwards all relevant events to frontend clients in real time

## Testing Requirements

- Unit tests for:
  - Every Pydantic event schema: valid payload passes, missing field raises ValidationError, extra field raises ValidationError
  - `vad_handler.on_participant_speech_detected()`: does not stop audio if Arni is in Listening state; stops audio if in Speaking state
- Integration tests for:
  - Publish `transcript.created` → subscriber receives event with correct schema
  - Interrupt: simulate AI speaking → trigger VAD → assert audio stopped + `ai.state_changed` (listening) published

## Status

complete

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
