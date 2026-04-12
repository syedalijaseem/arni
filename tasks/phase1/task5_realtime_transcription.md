# Task: Real-Time Transcription (Deepgram + Speaker Labeling)

## Objective

Integrate Deepgram Nova for per-participant streaming STT. Route each participant's Daily.co audio track to a dedicated Deepgram stream, map track IDs to user IDs for speaker labeling, store transcript chunks in MongoDB, and stream live transcripts to the frontend via WebSocket. Arni's backend bot also joins Daily.co here as a prerequisite for audio routing.

## Files

- Creates:
  - `backend/app/bot/arni_bot.py` — Arni Daily.co bot participant (joins room, routes audio)
  - `backend/app/bot/bot_manager.py` — manages per-meeting bot lifecycle
  - `backend/app/bot/__init__.py`
  - `backend/app/models/transcript.py` — TranscriptChunk MongoDB model
  - `backend/app/routers/transcripts.py` — WebSocket stream + transcript storage
  - `backend/tests/test_transcription.py`
- Modifies:
  - `backend/app/main.py` — register transcripts router, start bot on meeting activate
  - `backend/app/config.py` — add `DEEPGRAM_API_KEY`
  - `backend/requirements.txt` — add `deepgram-sdk`
  - `frontend/src/pages/MeetingRoom.tsx` — live transcript panel
- Reads:
  - `docs/srs.md` — FR-009 to FR-014, §8.3 Transcript Chunk model, §4.5 Arni Bot Participant Model
  - `docs/architecture.md` — §2 Live Meeting Pipeline, §3 Audio Feedback Loop Prevention

## Implementation Steps

1. Create `TranscriptChunk` model: `meeting_id`, `speaker_id`, `speaker_name`, `timestamp`, `text`, `is_final`, `source` = `"transcript"`
2. Create `arni_bot.py`: connects to Daily.co room as `"arni"` system participant; subscribes to all participant audio tracks; tags its own output track as `ai-source`
3. Create `bot_manager.py`: `start(meeting_id)` / `stop(meeting_id)` bot lifecycle
4. Create Deepgram streaming connection per audio track; map `track_id → user_id` via Daily.co participant event
5. Store final transcript chunks in MongoDB with correct `speaker_id`
6. WebSocket `/meetings/{id}/stream`: subscribe to Redis `transcript.created` events and forward to frontend
7. Frontend transcript panel: display rolling live transcript with speaker names

## Success Criteria

- [x] Each participant's speech is transcribed with correct `speaker_id`
- [x] Interim transcripts appear in the UI within 1 second of speech (NFR-002)
- [x] Final transcripts stored in MongoDB with `speaker_id`, `timestamp`, `text`, `is_final: true`
- [x] Arni bot joins Daily.co room as system participant `id: "arni"`
- [x] `DEEPGRAM_API_KEY` read from environment — never hardcoded

## Testing Requirements

- Unit tests for: track ID → user ID mapping, transcript chunk model validation
- Integration tests for: simulated audio track → Deepgram → transcript stored in MongoDB → WebSocket delivers to client

## Status

complete

---

## Progress Notes
<!-- loop-operator updates this as work proceeds -->
