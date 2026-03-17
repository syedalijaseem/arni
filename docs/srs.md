# Software Requirements Specification (SRS)

## Arni — Voice AI Meeting Participant

Version: 2.1
Date: 2026-03-16

---

## Revision History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | 2026 | Initial draft |
| 1.1 | 2026 | Minor updates |
| 2.0 | 2026-03-16 | Comprehensive revision: added missing features, technology stack, API specification, data models, frontend pages, deployment requirements, testing strategy, requirement IDs, and quantified ambiguous requirements |
| 2.1 | 2026-03-16 | Final review pass: added target users, consolidated duplicate context management requirements, fixed user class permissions, added optional LLM classification for wake detection, linked action items to meeting model, extended AI safety to action items, removed redundant value repetitions |

---

# 1. Introduction

## 1.1 Purpose

This document defines the functional and non-functional requirements for **Arni**, a real-time AI meeting participant system.

Arni joins web-based meetings, listens to conversations, responds when addressed, and generates structured knowledge from meeting transcripts.

This SRS serves as the primary contract between stakeholders, designers, developers, and testers. All implementation and testing work must trace back to requirements defined here.

---

## 1.2 Scope

Arni is an active AI meeting participant capable of:

- real-time transcription with speaker identification
- voice interaction during meetings via wake phrase
- interrupt handling and AI state management
- periodic auto-summarization during meetings
- post-meeting summarization, decision extraction, and action item generation
- meeting timeline with topic segmentation
- meeting history dashboard
- semantic search across meetings
- question answering over transcripts with source attribution

### In Scope (MVP)

- Meeting room creation with shareable invite links
- AI participant joining meetings automatically
- Real-time transcription with speaker labels
- Wake phrase detection and AI voice responses
- AI response queue for concurrent triggers
- Interrupt handling via VAD
- Periodic rolling auto-summaries
- Post-meeting reports (title, summary, decisions, action items, timeline)
- Editable action items
- Meeting history dashboard
- Post-meeting question answering with source attribution

### Out of Scope (MVP)

- Zoom, Google Meet, or Microsoft Teams integration
- Mobile applications
- Fine-tuned AI models
- Calendar integration
- Slack or Notion integrations
- Enterprise multi-organization features
- Meeting analytics (speaking time, engagement, sentiment)

---

## 1.3 Definitions and Acronyms

| Term | Definition |
|------|------------|
| AI | Artificial Intelligence |
| LLM | Large Language Model |
| STT | Speech-to-Text |
| TTS | Text-to-Speech |
| VAD | Voice Activity Detection |
| RAG | Retrieval-Augmented Generation |
| WebRTC | Web Real-Time Communication — browser-based audio/video protocol |
| JWT | JSON Web Token — compact token format for authenticated API access |
| OAuth | Open Authorization — delegated authentication protocol |

---

## 1.4 Assumptions and Dependencies

### Assumptions

- Users access the system via modern web browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- Users have a stable internet connection with sufficient bandwidth for WebRTC audio streaming
- Meetings are conducted in English (additional language support is out of scope for MVP)

### External Dependencies

| Dependency | Purpose | Risk |
|------------|---------|------|
| Daily.co | WebRTC audio infrastructure | Service outage blocks meeting audio |
| Deepgram Nova | Streaming speech-to-text | Service outage blocks transcription |
| Claude Sonnet (Anthropic) | LLM response generation | Service outage blocks AI responses |
| ElevenLabs | Text-to-speech generation | Service outage blocks voice responses |
| MongoDB Atlas | Database and vector search | Service outage blocks all data operations |
| Redis | Event bus (Pub/Sub) | Service outage blocks real-time event routing |

### Operational Constraints

| Service | Constraint |
|---------|------------|
| Deepgram free tier | ~12,000 transcription minutes per month |
| ElevenLabs | Character generation limits per billing tier |
| Daily.co | Limited concurrent meeting rooms per plan |

---

# 2. Overall Description

## 2.1 Product Perspective

Arni is a web-based system integrating:

- WebRTC audio infrastructure (Daily.co)
- Streaming transcription (Deepgram Nova)
- LLM-based reasoning (Claude Sonnet)
- Text-to-speech generation (ElevenLabs)
- Document storage and vector search (MongoDB Atlas)
- Real-time event routing (Redis Pub/Sub)

---

## 2.2 Target Users

- Remote teams
- Students and academic project groups
- Professionals running frequent meetings
- Small organizations

---

## 2.3 User Classes

### Host

- creates and manages meetings
- ends meetings
- accesses meeting reports
- deletes meeting data
- edits AI-generated action items

### Participant

- joins meetings via shareable links
- interacts with AI during meetings
- views transcripts and reports
- asks post-meeting questions
- edits AI-generated action items

---

## 2.4 Operating Environment

- **Client**: Modern web browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- **Backend**: Cloud-hosted Python (FastAPI) application deployed via Docker containers
- **Hosting**: Fly.io (backend), Vercel (frontend)
- **Database**: MongoDB Atlas (cloud-hosted)

---

## 2.5 Constraints

- API rate limits imposed by third-party services (Deepgram, ElevenLabs, Anthropic)
- LLM token limits constrain maximum context window size
- Real-time latency requirements demand streaming architectures
- Maximum meeting duration: 2 hours (see NFR-007)

---

# 3. Functional Requirements

---

## 3.1 Meeting Lifecycle

| Req ID | Requirement |
|--------|-------------|
| FR-001 | The system must support the following meeting states: Created, Active, Ended, Processed |
| FR-002 | State transitions must follow the sequence: Created → Active → Ended → Processed |
| FR-003 | A meeting transitions to Active when the first participant joins |
| FR-004 | A meeting transitions to Ended when the host ends the meeting |
| FR-005 | A meeting transitions to Processed after post-meeting intelligence generation completes |

---

## 3.2 Meeting Creation

| Req ID | Requirement |
|--------|-------------|
| FR-006 | Users must be able to create meeting rooms |
| FR-007 | The system must generate a shareable invite link for each meeting |
| FR-008 | Arni must automatically join the meeting as a participant when the meeting becomes Active |

---

## 3.3 Real-Time Transcription

| Req ID | Requirement |
|--------|-------------|
| FR-009 | The system must generate interim transcripts for real-time UI display |
| FR-010 | The system must generate final transcripts for storage and AI processing |
| FR-011 | Each transcript entry must include: speaker_id, timestamp, and text |

---

## 3.4 Speaker Identification

| Req ID | Requirement |
|--------|-------------|
| FR-012 | Each participant's audio must be captured as a separate Daily.co audio track |
| FR-013 | Each audio track ID must be mapped to the corresponding user ID |
| FR-014 | Mapped speaker identity must be passed to Deepgram STT so transcripts are stored with the correct speaker_id |

Speaker identification pipeline:

```
Participant Audio Track → Track ID mapped to User ID → Deepgram STT → Transcript stored with speaker_id
```

---

## 3.5 Wake Phrase Detection

| Req ID | Requirement |
|--------|-------------|
| FR-015 | The system must detect the wake phrase at the start of an utterance |
| FR-016 | Supported wake phrase forms: "Hey Arni" and "Arni" |
| FR-017 | Primary detection: wake phrases must be detected using regex pattern matching on final transcript text |
| FR-018 | The text following the wake phrase in the same utterance must be treated as the user's command/question |
| FR-019 | Detection confidence: the wake phrase must be an exact substring match (case-insensitive) at the start of the utterance, or preceded only by filler words |
| FR-020 | Optional secondary detection: LLM-based classification may be used as a fallback when regex matching is inconclusive |

---

## 3.6 AI Response Queue

| Req ID | Requirement |
|--------|-------------|
| FR-021 | If multiple wake events occur, requests must be queued |
| FR-022 | Queued requests must be processed sequentially (FIFO) |
| FR-023 | Duplicate wake triggers during the cooldown period (see RL-001) must be ignored |

---

## 3.7 AI Response Generation and Context Management

| Req ID | Requirement |
|--------|-------------|
| FR-024 | The system must generate responses using Claude Sonnet with structured context |
| FR-025 | The LLM input must be constructed from: (1) system instruction, (2) rolling meeting summary, (3) recent transcript window (last N turns, default: 20, configurable) |
| FR-026 | The system must maintain a rolling meeting summary that is regenerated every 10 minutes during an active meeting |
| FR-027 | The hybrid context approach (summary + recent turns) must keep total token usage within the LLM's context window limit |

---

## 3.8 Interrupt Handling

| Req ID | Requirement |
|--------|-------------|
| FR-028 | The system must detect human speech using Voice Activity Detection (VAD) |
| FR-029 | If human speech is detected while Arni is speaking, the system must immediately stop AI audio playback |
| FR-030 | After interruption, the system must return to the Listening state and prioritize human audio |

---

## 3.9 Voice Response

| Req ID | Requirement |
|--------|-------------|
| FR-031 | AI text responses must be converted to speech using ElevenLabs TTS |
| FR-032 | Generated audio must be injected into the meeting via Daily.co so all participants hear it |

---

## 3.10 Audio Feedback Loop Prevention

| Req ID | Requirement |
|--------|-------------|
| FR-033 | AI audio streams must be tagged with an AI source identifier |
| FR-034 | Audio tracks tagged as AI source must be excluded from the STT pipeline |
| FR-035 | Under no circumstances should AI-generated speech be transcribed back into the meeting transcript |

---

## 3.11 AI State Machine

| Req ID | Requirement |
|--------|-------------|
| FR-036 | The AI must operate in the following defined states: Idle, Listening, Processing, Speaking |
| FR-037 | State transitions must follow valid paths: Idle → Listening (on meeting Active), Listening → Processing (on wake event), Processing → Speaking (on TTS ready), Speaking → Listening (on response complete or interrupt) |
| FR-038 | Current AI state must be exposed to the frontend in real time via WebSocket events |

---

## 3.12 Error State UX Behavior

| Req ID | Requirement |
|--------|-------------|
| FR-039 | The system must display user-visible messages for: transcription interruptions, AI processing failures, reconnection attempts |
| FR-040 | Error messages must appear in the meeting UI within 2 seconds of the error occurring |

---

## 3.13 Post-Meeting Processing

| Req ID | Requirement |
|--------|-------------|
| FR-041 | Upon meeting end, the system must generate: meeting title, summary, key decisions, and action items |
| FR-042 | Decisions must be extracted only if explicitly stated in the transcript — the system must not infer decisions |
| FR-043 | Action items must be extracted only from explicit commitments or assignments stated in the transcript — the system must not infer tasks |
| FR-044 | The system must generate a meeting timeline with timestamped topic segments |
| FR-045 | Post-meeting processing must also generate transcript chunk embeddings and store them in the vector index for future search |

Example timeline output:

```
0:00  Introductions
3:40  Budget discussion
12:10 Hiring plans
20:30 Action items
```

---

## 3.14 Editable Action Items

| Req ID | Requirement |
|--------|-------------|
| FR-046 | AI-generated action items must be editable by all meeting participants (host and attendees) |
| FR-047 | Editable fields include: task description, assignee, and deadline |
| FR-048 | Edits must be persisted immediately and reflected in the meeting report |

---

## 3.15 Meeting History Dashboard

| Req ID | Requirement |
|--------|-------------|
| FR-049 | Users must be able to view a list of their past meetings |
| FR-050 | The dashboard must display for each meeting: title, date, participants, duration, and action item count |
| FR-051 | Each meeting entry must link to its detailed report page |
| FR-052 | Users must be able to search across meetings using keyword and semantic search |

---

## 3.16 Post-Meeting Question Answering

| Req ID | Requirement |
|--------|-------------|
| FR-053 | Users must be able to ask natural language questions about past meetings |
| FR-054 | The system must retrieve relevant transcript chunks via vector similarity search (RAG) |
| FR-055 | The system must generate an answer using the retrieved chunks as LLM context |
| FR-056 | Each answer must include source transcript excerpts with speaker and timestamp |

---

## 3.17 Access Control

| Req ID | Requirement |
|--------|-------------|
| FR-057 | Only authenticated meeting participants may access transcripts and reports for that meeting |
| FR-058 | The meeting host may delete all data associated with a meeting |
| FR-059 | Authentication must use JWT tokens issued via email/password registration or Google OAuth |

---

## 3.18 Data Retention

| Req ID | Requirement |
|--------|-------------|
| FR-060 | Transcripts and meeting data must be stored for a configurable duration (default: 90 days) |
| FR-061 | Users may manually delete their own meetings at any time |

---

# 4. System Architecture

> For detailed diagrams (system architecture, pipeline flowcharts, and sequence diagrams), see [architecture.md](architecture.md).

## 4.1 System Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | Frontend client | React + Tailwind | Meeting UI, dashboard, post-meeting reports |
| 2 | Backend API | FastAPI | REST endpoints, WebSocket server, authentication |
| 3 | Audio pipeline | Daily.co + Deepgram | WebRTC streaming, speech-to-text |
| 4 | AI processing layer | Claude Sonnet + ElevenLabs | Wake detection, response generation, text-to-speech |
| 5 | Data storage | MongoDB Atlas | Document storage, vector search index |
| 6 | Event bus | Redis Pub/Sub | Real-time event routing between components |

## 4.2 Key Pipelines

**Live Meeting Pipeline**: Participant speech → Daily.co WebRTC → audio track routing → Deepgram streaming STT → transcript storage → wake phrase detection → AI request queue → Claude response generation → ElevenLabs TTS → audio played into meeting.

**Audio Feedback Loop Prevention**: AI audio tracks are tagged with an AI source identifier and excluded from the STT pipeline to prevent self-transcription.

**Post-Meeting Processing Pipeline**: Meeting end event → transcript retrieval → summary generation → decision & action extraction → timeline generation → transcript chunking → embedding generation → vector index storage.

**Question Answering Pipeline (RAG)**: User question → embedding generation → vector search → relevant transcript chunks → LLM response generation → answer with source attribution.

## 4.3 Event Bus

Real-time events are managed through Redis Pub/Sub. Event types include: audio stream events, wake word events, AI state change events, AI response events, meeting lifecycle events, and error events.

---

# 5. Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Tailwind CSS |
| Backend | FastAPI (Python) |
| Audio Infrastructure | Daily.co |
| Speech-to-Text | Deepgram Nova (streaming) |
| LLM | Claude Sonnet (Anthropic) |
| Text-to-Speech | ElevenLabs |
| Database | MongoDB |
| Vector Search | MongoDB Atlas Vector Search |
| Event Bus | Redis Pub/Sub |
| Authentication | JWT + Google OAuth |
| Deployment (Backend) | Fly.io + Docker |
| Deployment (Frontend) | Vercel |
| Containerization | Docker |

---

# 6. Frontend Pages

| Page | Description |
|------|-------------|
| Landing Page | Product overview, call-to-action to sign up / log in |
| Authentication Pages | Registration, login, Google OAuth flow |
| Dashboard | Meeting history list with search, meeting cards showing title/date/participants/duration |
| Meeting Room | Live meeting interface with transcript feed, AI status indicator, participant list |
| Post-Meeting Report | Summary, decisions, action items (editable), timeline, transcript, Q&A interface |

---

## 6.1 AI Status Indicator

The meeting room interface must display Arni's current state.

| State | Display Text |
|-------|-------------|
| Idle | — |
| Listening | "Arni is listening..." |
| Processing | "Arni is generating a response..." |
| Speaking | "Arni is speaking..." |

State changes must update the indicator in real time via WebSocket events.

---

# 7. Backend API Specification

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new user with email/password |
| POST | `/auth/login` | Log in and receive JWT token |
| POST | `/auth/google` | Authenticate via Google OAuth |

### Meetings

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/meetings/create` | Create a new meeting room |
| GET | `/meetings/{id}` | Get meeting details |
| DELETE | `/meetings/{id}` | Delete a meeting and all associated data (host only) |
| POST | `/meetings/{id}/end` | End an active meeting and trigger post-processing |

### Real-Time

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/meetings/{id}/stream` | WebSocket for live transcript, AI state, and event streaming |

### Post-Meeting

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/meetings/{id}/transcript` | Retrieve full meeting transcript |
| GET | `/meetings/{id}/summary` | Retrieve meeting summary and report |
| POST | `/meetings/{id}/ask` | Ask a question about the meeting (RAG) |
| PATCH | `/meetings/{id}/action-items/{item_id}` | Update an action item (description, assignee, deadline) |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | Get user's meeting history |
| GET | `/meetings/search?q=` | Search across meetings |

---

# 8. Data Models

## 8.1 User

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| email | string | User email (unique) |
| name | string | Display name |
| password_hash | string | Hashed password (null for OAuth users) |
| auth_provider | string | "email" or "google" |
| created_at | datetime | Account creation timestamp |

## 8.2 Meeting

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| title | string | AI-generated or user-provided title |
| host_id | ObjectId | Reference to User |
| participant_ids | ObjectId[] | References to Users |
| state | enum | Created, Active, Ended, Processed |
| invite_link | string | Shareable meeting link |
| started_at | datetime | When meeting became Active |
| ended_at | datetime | When meeting was ended |
| duration_seconds | integer | Computed meeting duration |
| summary | string | AI-generated meeting summary |
| decisions | string[] | Extracted key decisions |
| action_item_ids | ObjectId[] | References to Action Items |
| timeline | object[] | Array of {timestamp, topic} entries |
| created_at | datetime | Record creation timestamp |

## 8.3 Transcript Chunk

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| speaker_id | ObjectId | Reference to User |
| speaker_name | string | Display name at time of utterance |
| timestamp | datetime | When the utterance occurred |
| text | string | Transcript text content |
| is_final | boolean | Whether this is a final (not interim) transcript |
| embedding | float[] | Vector embedding for semantic search |

## 8.4 Action Item

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| description | string | Task description |
| assignee | string | Assigned person (editable) |
| deadline | string | Due date (editable) |
| is_edited | boolean | Whether manually edited by a user |
| created_at | datetime | Extraction timestamp |

## 8.5 Meeting Summary (Rolling)

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| summary_text | string | Auto-generated rolling summary |
| generated_at | datetime | When this summary was generated |
| turn_count | integer | Number of transcript turns covered |

---

# 9. Non-Functional Requirements

---

## 9.1 Performance

| Req ID | Requirement |
|--------|-------------|
| NFR-001 | AI response latency (wake phrase detected → audio playback begins) must be under 2 seconds at the 95th percentile |
| NFR-002 | Transcript latency (speech → text displayed in UI) must be under 1 second at the 95th percentile |
| NFR-003 | Post-meeting processing must complete within 60 seconds of meeting end |

---

## 9.2 Scalability

| Req ID | Requirement |
|--------|-------------|
| NFR-004 | The system must support 5 to 10 concurrent active meetings |
| NFR-005 | Each meeting must support up to 20 participants |

---

## 9.3 Availability

| Req ID | Requirement |
|--------|-------------|
| NFR-006 | Target uptime: 99%, measured on a rolling 30-day basis |

---

## 9.4 Meeting Duration

| Req ID | Requirement |
|--------|-------------|
| NFR-007 | Maximum supported meeting duration: 2 hours |
| NFR-008 | The system must gracefully end AI participation if the 2-hour limit is reached |

---

## 9.5 Reliability and Error Handling

| Req ID | Requirement | Failure Scenario | Required Behavior |
|--------|-------------|-------------------|-------------------|
| NFR-009 | STT stream recovery | Deepgram connection drops | Automatically reconnect within 5 seconds; buffer audio during reconnection |
| NFR-010 | TTS failure fallback | ElevenLabs unavailable | Display AI response as text in the meeting chat UI |
| NFR-011 | LLM failure fallback | Claude API unavailable | Return a canned fallback response: "I'm having trouble processing that right now. Please try again." |
| NFR-012 | User disconnection recovery | Participant loses connection | Allow reconnection without losing transcript continuity; re-sync transcript on rejoin |
| NFR-013 | Partial failure resilience | Any single component fails | The system must continue operating with degraded functionality rather than full failure |

---

## 9.6 Security

| Req ID | Requirement |
|--------|-------------|
| NFR-014 | All client-server communication must use TLS 1.2+ encryption |
| NFR-015 | Transcripts and meeting data must be encrypted at rest |
| NFR-016 | All API endpoints (except auth) must require a valid JWT token |
| NFR-017 | JWT tokens must expire after 24 hours |
| NFR-018 | Passwords must be hashed using bcrypt with a minimum cost factor of 10 |

---

## 9.7 Configurability

The following system parameters must be configurable without code changes (via environment variables or configuration file). Default values for rate limits are defined in §10; default values for other parameters are shown below:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Context window size | 20 turns | Number of recent transcript turns included in LLM context |
| Auto-summary interval | 10 minutes | Frequency of rolling summary generation |
| Data retention period | 90 days | How long meeting data is stored before auto-deletion |
| Wake word cooldown | See §10 (RL-001) | Minimum time between processing consecutive wake triggers |
| Max AI responses per meeting | See §10 (RL-002) | Maximum number of AI responses allowed in a single meeting |
| Max post-meeting queries | See §10 (RL-003) | Maximum Q&A queries per meeting |
| Max meeting duration | See §9.4 (NFR-007) | Maximum allowed meeting length |

---

# 10. Rate Limiting

| Req ID | Limit | Value | Scope |
|--------|-------|-------|-------|
| RL-001 | Wake word cooldown | 10 seconds | Per meeting, global |
| RL-002 | Max AI responses | 30 | Per meeting |
| RL-003 | Max post-meeting queries | 20 | Per meeting, per user |

Justification:

- Cost control for LLM and TTS API usage
- Abuse prevention
- Fair usage across concurrent meetings

When a rate limit is reached, the system must:
- Log the event
- Return a user-friendly message explaining the limit
- Continue normal operation for non-rate-limited functions

---

# 11. Observability

## 11.1 Metrics

The system must track and expose the following metrics:

| Metric | Description |
|--------|-------------|
| STT latency | Time from audio received to transcript generated |
| LLM latency | Time from prompt sent to response received |
| TTS latency | Time from text sent to audio generated |
| Total response latency | Time from wake phrase detected to audio playback start |
| Meeting duration | Total active meeting time |
| AI interaction count | Number of AI responses per meeting |
| Error rate | Percentage of failed AI response attempts |

Recommended tooling: OpenTelemetry for instrumentation, Prometheus for metrics collection, Grafana for dashboards.

---

## 11.2 Alerts

| Req ID | Alert Condition | Threshold |
|--------|-----------------|-----------|
| OBS-001 | Total AI response latency exceeds target | > 5 seconds for 3+ consecutive responses |
| OBS-002 | STT stream fails repeatedly | > 3 failures within 5 minutes |
| OBS-003 | LLM API error rate spikes | > 10% error rate over 5-minute window |
| OBS-004 | Meeting exceeds maximum duration | Meeting active for > 2 hours |

---

# 12. System Initialization

When the first participant joins a meeting:

| Step | Action |
|------|--------|
| 1 | Meeting state transitions to Active |
| 2 | Daily.co room is provisioned (if not already) |
| 3 | Audio pipeline initializes (track routing, STT connections) |
| 4 | AI enters Listening state |
| 5 | AI status indicator updates in the frontend |

---

# 13. Deployment Requirements

| Req ID | Requirement |
|--------|-------------|
| DEP-001 | Backend must be containerized using Docker |
| DEP-002 | Backend must be deployable to Fly.io |
| DEP-003 | Frontend must be deployable to Vercel |
| DEP-004 | All secrets and API keys must be managed via environment variables, never committed to source control |
| DEP-005 | The system must support zero-downtime deployments via rolling updates |

---

# 14. Testing Strategy

## 14.1 Unit Tests

- Wake phrase detection logic (regex matching, edge cases)
- AI state machine transitions
- Rate limit enforcement
- Context window construction (summary + recent turns)
- Action item CRUD operations

## 14.2 Integration Tests

- Full audio pipeline: audio input → STT → transcript storage → wake detection → LLM → TTS → audio output
- Post-meeting processing pipeline: meeting end → summary + decisions + timeline + embeddings
- RAG pipeline: question → embedding → vector search → LLM answer → source attribution
- Authentication flows (registration, login, Google OAuth, JWT validation)

## 14.3 End-to-End Tests

- Complete meeting lifecycle: create → join → transcribe → interact with AI → end → view report
- Multi-participant meeting with concurrent wake triggers
- User disconnection and reconnection during active meeting

## 14.4 Performance Tests

- Measure AI response latency under load (multiple concurrent meetings)
- Measure transcript latency with varying audio quality
- Verify system behavior at rate limit boundaries

---

# 15. Future Enhancements

| Feature | Description |
|---------|-------------|
| Proactive AI participation | Arni contributes unprompted when relevant (e.g., reminding of agenda items) |
| Meeting analytics | Speaking time distribution, participant engagement, interruption tracking, sentiment analysis |
| Platform integrations | Zoom, Google Meet, Microsoft Teams meeting joining |
| Productivity integrations | Slack notifications, Notion export |
| Mobile support | Native iOS and Android applications |
| Multi-language support | Transcription and AI responses in languages beyond English |
