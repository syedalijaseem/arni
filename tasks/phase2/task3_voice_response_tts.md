# Task: Voice Response (TTS + Audio Injection)

## Objective

Connect Claude's text response to ElevenLabs TTS, inject the resulting audio into the Daily.co meeting via Arni's bot track, and implement audio feedback loop prevention so Arni never transcribes its own speech. Update the frontend AI status indicator to reflect real-time state changes.

## Files

- Creates:
  - `backend/app/tts/__init__.py`
  - `backend/app/tts/elevenlabs_client.py` — TTS integration
  - `backend/app/tts/audio_injection.py` — Daily.co audio injection via Arni bot track
  - `backend/tests/test_tts.py`
- Modifies:
  - `backend/app/ai/ai_service.py` — chain response text → TTS → audio injection
  - `backend/app/bot/arni_bot.py` — tag Arni's audio track as `ai-source`; ensure STT pipeline skips it
  - `backend/app/routers/transcripts.py` — filter out `speaker_id: "arni"` from transcript storage and wake detection
  - `backend/app/config.py` — add `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`
  - `backend/requirements.txt` — add `elevenlabs`
  - `frontend/src/pages/MeetingRoom.tsx` — AI status indicator: Listening → Processing → Speaking
- Reads:
  - `docs/srs.md` — FR-031 to FR-035 (voice response, feedback loop), §6.1 AI Status Indicator states, §4.5 Arni Bot Participant Model
  - `docs/architecture.md` — §3 Audio Feedback Loop Prevention diagram, live meeting pipeline

## Implementation Steps

1. Add `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` to `backend/app/config.py`
2. Create `backend/app/tts/elevenlabs_client.py`:
   - `text_to_speech(text: str) → bytes` — calls ElevenLabs streaming API
   - On ElevenLabs failure: log error, return `None` (triggers text-only fallback in caller)
3. Create `backend/app/tts/audio_injection.py`:
   - `inject_audio(audio_bytes: bytes, meeting_id: str)` — sends audio to Daily.co via Arni's bot connection
   - Arni's audio track must be tagged with `audio_track_tag: "ai-source"` (SRS §4.5)
4. Update `backend/app/ai/ai_service.py`:
   - After Claude returns response text:
     a. Publish `ai.state_changed` (speaking) to Redis
     b. Call `elevenlabs_client.text_to_speech(response_text)`
     c. If TTS fails: publish `ai.responded` with `response_text` only (text-only fallback per NFR-010); publish `ai.state_changed` (listening)
     d. If TTS succeeds: call `audio_injection.inject_audio(audio_bytes, meeting_id)`; then publish `ai.state_changed` (listening)
5. Update `backend/app/bot/arni_bot.py`:
   - Tag Arni's Daily.co audio track with `audio_track_tag: "ai-source"` on bot initialization
   - Pass tag to Deepgram track routing — Deepgram must never receive the `ai-source` track
6. Update `backend/app/routers/transcripts.py`:
   - Filter out any transcript chunk where `speaker_id == "arni"` before saving to MongoDB
   - Filter out `speaker_id == "arni"` before passing transcript to wake detector
7. Update `frontend/src/pages/MeetingRoom.tsx`:
   - Subscribe to `ai.state_changed` WebSocket events
   - Display: Listening → "Arni is listening..." / Processing → "Arni is generating a response..." / Speaking → "Arni is speaking..."
   - Animated indicator (pulse/spinner) per current state

## Success Criteria

- [ ] Arni's text response is converted to speech and played into the meeting room
- [ ] All participants in the Daily.co room hear Arni's voice response
- [ ] Arni's audio track is tagged `ai-source` and never forwarded to Deepgram STT (FR-034)
- [ ] Arni's speech is never stored as a transcript chunk in MongoDB (FR-035)
- [ ] `speaker_id: "arni"` transcripts never trigger wake detection
- [ ] ElevenLabs failure displays response as text in the UI, no 500 error (NFR-010)
- [ ] AI status indicator in the UI updates in real time for all three states
- [ ] `ELEVENLABS_API_KEY` is read from environment — never hardcoded

## Testing Requirements

- Unit tests for:
  - `elevenlabs_client.text_to_speech()`: returns bytes on success; returns `None` on API error
  - Transcript filtering: assert `speaker_id == "arni"` rows are excluded from storage
  - Track tag: assert `ai-source` tag is set on Arni bot initialization
- Integration tests for:
  - Full pipeline: wake phrase → Claude response → ElevenLabs audio → Daily.co injection
  - TTS failure path: Claude responds, ElevenLabs fails → text displayed in UI, no crash

## Status

pending
