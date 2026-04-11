# Software Requirements Specification (SRS)

## Arni — Voice AI Meeting Participant

Version: 4.0
Date: 2026-04-11

---

## Revision History

| Version | Date | Description |
|---------|------|-------------|
| 1.0 | 2026 | Initial draft |
| 1.1 | 2026 | Minor updates |
| 2.0 | 2026-03-16 | Comprehensive revision: added missing features, technology stack, API specification, data models, frontend pages, deployment requirements, testing strategy, requirement IDs, and quantified ambiguous requirements |
| 2.1 | 2026-03-16 | Final review pass: added target users, consolidated duplicate context management requirements, fixed user class permissions, added optional LLM classification for wake detection, linked action items to meeting model, extended AI safety to action items, removed redundant value repetitions |
| 3.0 | 2026-04-11 | Major additions: pre-meeting document upload + unified RAG pipeline, strict service boundary definitions, AI Service API contract, RAG chunk size specification, Arni bot participant model, formal event schema |
| 3.1 | 2026-04-11 | Meeting access & privacy lockdown: invite-only access model, lobby/waiting room, host-only controls, Arni joins on creation, participant management, navigation guards, meeting visibility scoping, new event schemas (FR-063–FR-077) |
| 4.0 | 2026-04-11 | Architect review: added Proactive Fact-Checking (FR-078–FR-084), AI Teammate Reasoning (FR-085–FR-088), consolidated access control into FR-058–FR-074, added /ai/fact-check endpoint, fact.checked + participant.rejected event schemas, Cross-Meeting Memory future enhancement, updated configurability and testing sections |

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
- **Pre-meeting document upload** (PDFs, DOCX, TXT) attached to a meeting room (FR-057a–FR-057i)
- **Unified RAG context**: Arni answers questions by searching across both uploaded documents and meeting transcripts simultaneously (see §5 Document Ingestion Pipeline and §6 Unified RAG Pipeline in architecture.md)
- **Proactive Fact-Checking**: Arni monitors transcripts in real time and automatically corrects factual contradictions against uploaded documents (FR-078–FR-084)
- **AI Teammate Reasoning**: Arni gives explicit recommendations with justification when asked to compare or choose between options (FR-085–FR-088)

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
| AI Service | Internal microservice boundary that owns all LLM/TTS/STT orchestration, isolated from meeting business logic |

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

> **Service Boundaries** — To prevent monolithic files and ensure clear ownership, all functional requirements map to one of these backend services:
>
> | Service | Responsibility |
> |---------|----------------|
> | `auth-service` | Registration, login, JWT, Google OAuth |
> | `meeting-service` | Meeting lifecycle, room creation, participant management |
> | `transcript-service` | STT ingestion, transcript storage, wake detection |
> | `ai-service` | LLM orchestration, TTS, context management, RAG |
> | `document-service` | Pre-meeting document upload, chunking, embedding ingestion |
> | `postprocessing-service` | End-of-meeting summary, decisions, action items, timeline, embedding |
> | `realtime-gateway` | WebSocket server, Redis event routing to frontend |

---

## 3.1 Meeting Lifecycle

| Req ID | Requirement |
|--------|-------------|
| FR-001 | The system must support the following meeting states: Created, Active, Ended, Processed |
| FR-002 | State transitions must follow the sequence: Created → Active → Ended → Processed |
| FR-003 | A meeting transitions to Active when the first **admitted** participant joins; participants in the waiting room do not trigger this transition |
| FR-004 | A meeting transitions to Ended when the host ends the meeting (host-only action) |
| FR-005 | A meeting transitions to Processed after post-meeting intelligence generation completes |

---

## 3.2 Meeting Creation

| Req ID | Requirement |
|--------|-------------|
| FR-006 | Users must be able to create meeting rooms |
| FR-007 | The system must generate a shareable invite link for each meeting |
| FR-008 | Arni must automatically join the meeting as a participant **when the meeting is first created** — Arni is present in the participant list from the Created state, before any human participant joins |

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

## 3.17 Pre-Meeting Document Upload

Users may upload reference documents to a meeting room before or during a meeting. Arni will use these documents as additional context when answering questions — exactly like a meeting partner who has read the briefing materials.

| Req ID | Requirement |
|--------|-------------|
| FR-057a | Users must be able to upload documents to a meeting room before or during the meeting via `POST /meetings/{id}/documents` |
| FR-057b | Supported file types: PDF, DOCX, TXT (maximum 20 MB per file, maximum 10 files per meeting) |
| FR-057c | Uploaded documents must be chunked (200–400 tokens, 50-token overlap) and embedded using the same pipeline as transcript chunks |
| FR-057d | Document chunks must be stored in the same vector index as transcript chunks, tagged with `source: "document"` and the document filename |
| FR-057e | When Arni answers a question, the vector search must pull from both transcript chunks and document chunks simultaneously |
| FR-057f | Arni's response must attribute answers to source documents (filename + excerpt) in addition to transcript excerpts when document context is used |
| FR-057g | Only authenticated meeting participants may upload, view, or delete documents for that meeting |
| FR-057h | The frontend must display a document upload panel on the meeting creation/pre-flight screen, accessible before the meeting goes Active |
| FR-057i | Upload processing (chunking + embedding) must complete within 30 seconds of file upload for files under 5 MB |

---

## 3.18 Access Control

> **Implementation note:** Waiting room state is **ephemeral** — stored in Redis only, never persisted in MongoDB.

### Join Authorization

| Req ID | Requirement |
|--------|-------------|
| FR-058 | Only authenticated users on the meeting invite list may join a meeting via invite link |
| FR-059 | The invite list is managed exclusively by the host |
| FR-060 | Users not on the invite list who attempt to join must receive HTTP 403 with message: `"You are not authorized to join this meeting"` |
| FR-061 | The host may add participants by email before or during a meeting via `POST /meetings/{id}/invite`; added users receive an email notification |
| FR-062 | The host may remove participants during an active meeting via `DELETE /meetings/{id}/participants/{user_id}`; removed users lose access immediately |

### Host-Only Controls

| Req ID | Requirement |
|--------|-------------|
| FR-063 | Only the host may end an active meeting |
| FR-064 | Only the host may mute or remove Arni from a meeting |
| FR-065 | If the host disconnects, a **10-minute grace period** begins; if the host does not reconnect, the meeting auto-ends and `meeting.auto_ended` is published; the countdown must be visible to remaining participants |
| FR-066 | The host may transfer the host role to another active participant via `POST /meetings/{id}/transfer-host` |

### Privacy & Visibility

| Req ID | Requirement |
|--------|-------------|
| FR-067 | Meetings are private by default — not publicly discoverable by any search or listing endpoint |
| FR-068 | Dashboard and search results must be scoped to only meetings where the authenticated user is the host or an invited participant |

### Frontend Navigation Guards

| Req ID | Requirement |
|--------|-------------|
| FR-069 | The frontend must verify participant authorization before rendering the meeting room; unauthorized users are redirected to the dashboard with an error message |

### Meeting Lobby (Waiting Room)

| Req ID | Requirement |
|--------|-------------|
| FR-070 | Invited participants who click the invite link must be placed in a **waiting room** until explicitly admitted by the host |
| FR-071 | The host must explicitly admit each waiting participant via `POST /meetings/{id}/admit/{user_id}`; the admit action publishes `participant.admitted` |
| FR-072 | The host may reject a waiting participant; rejected users see: `"You were not admitted to this meeting"` and `participant.rejected` is published |

### Arni & Data Access

| Req ID | Requirement |
|--------|-------------|
| FR-073 | Arni must automatically join as a participant when the meeting is first created — not when the first human participant joins |
| FR-074 | Only the host may delete a meeting and all associated data including uploaded documents and vector chunks |

---

## 3.19 Data Retention

| Req ID | Requirement |
|--------|-------------|
| FR-075 | Transcripts, uploaded documents, and all meeting data must be stored for a configurable duration (default: 90 days) |
| FR-076 | Users may manually delete their own meetings at any time |

---

## 3.20 Proactive Fact-Checking

Arni passively monitors the meeting transcript in real time. When a participant states a fact or metric that contradicts an uploaded document, Arni automatically interjects with a voice correction — without waiting for a wake phrase. This is Arni's most important differentiator: it makes Arni feel like a thinking participant, not a chatbot.

**Example:**
> Participant: "Our churn last quarter was 12%."
> Uploaded doc says: churn = 7%
> Arni: "Small correction — according to the Q4 report, churn rate was 7%, not 12%."

| Req ID | Requirement |
|--------|-------------|
| FR-078 | After every final transcript entry, Arni must run a background fact-check against uploaded document chunks using vector similarity search via `POST /ai/fact-check` |
| FR-079 | If a factual contradiction is detected with confidence above a configurable threshold (default: 0.85), Arni must automatically generate a correction response without waiting for a wake phrase |
| FR-080 | Fact-check corrections must cite the source document name and the relevant excerpt |
| FR-081 | Fact-checking must not trigger more than once per 30-second window per meeting to prevent interruption overload (configurable; see §9.7) |
| FR-082 | Fact-check corrections must be enqueued in the same AI response queue as wake-phrase responses — they must not interrupt an in-progress AI response |
| FR-083 | The frontend must visually distinguish fact-check responses from wake-phrase responses (different label or color in the transcript feed) |
| FR-084 | Fact-checking must only trigger when at least one document has been uploaded to the meeting; if no documents exist, the check must be skipped silently |

---

## 3.21 AI Teammate Reasoning

When participants debate options, Arni can be asked to compare them and give a reasoned recommendation. Arni must express a preference with justification — not a neutral list of pros and cons. This is implemented as a **prompt routing behavior within `/ai/respond`** — no new endpoints required.

**Example:**
> "Hey Arni, we're choosing between Option A and Option B for the backend. Option A is faster to build. Option B is more scalable. Which do you recommend?"
> Arni: "I'd go with Option B. Given that you mentioned scaling to 100k users earlier in this meeting, the long-term benefit outweighs the short-term speed loss. Option A would likely require a rewrite within 6 months."

| Req ID | Requirement |
|--------|-------------|
| FR-085 | When a wake phrase command contains comparison language (e.g. "which", "better", "prefer", "recommend", "vs", "or"), the system must route the request to a reasoning-optimized prompt template |
| FR-086 | Reasoning responses must include: Arni's explicit recommendation, the tradeoffs considered, and relevant context from the current meeting or uploaded documents |
| FR-087 | Arni must not give a neutral non-answer — it must take a position |
| FR-088 | Reasoning context must include: rolling meeting summary, last 20 transcript turns, and any relevant document chunks retrieved via RAG |

---

# 4. System Architecture

> For detailed diagrams (system architecture, pipeline flowcharts, and sequence diagrams), see [architecture.md](architecture.md).

## 4.1 System Components

| # | Component | Technology | Responsibility |
|---|-----------|------------|----------------|
| 1 | Frontend client | React + Tailwind | Meeting UI, dashboard, document upload panel, post-meeting reports |
| 2 | `auth-service` | FastAPI | Registration, login, JWT issuance, Google OAuth |
| 3 | `meeting-service` | FastAPI | Meeting lifecycle, room provisioning, participant management |
| 4 | `transcript-service` | FastAPI + Deepgram | STT ingestion, transcript storage, wake phrase detection |
| 5 | `document-service` | FastAPI | File upload, document chunking, embedding ingestion |
| 6 | `ai-service` | FastAPI + Claude + ElevenLabs | LLM orchestration, TTS, context management, unified RAG |
| 7 | `postprocessing-service` | FastAPI | End-of-meeting summary, decisions, action items, timeline, embedding |
| 8 | `realtime-gateway` | FastAPI WebSocket + Redis | Real-time event routing to frontend |
| 9 | Data storage | MongoDB Atlas | All document storage and vector search index |
| 10 | Event bus | Redis Pub/Sub | Internal event routing between services |

## 4.2 AI Service API

The `ai-service` exposes a strict internal HTTP API to decouple AI orchestration from meeting business logic:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/respond` | Generate a real-time voice response to a user command (RAG-enabled); uses reasoning-optimized prompt when comparison language detected (FR-085) |
| POST | `/ai/fact-check` | Accept a transcript excerpt and `meeting_id`; run vector search against document chunks; return contradiction if found above confidence threshold (FR-078–FR-079) |
| POST | `/ai/summarize` | Generate or update the rolling meeting summary |
| POST | `/ai/extract-decisions` | Extract explicit decisions from a transcript |
| POST | `/ai/extract-actions` | Extract explicit action items from a transcript |
| POST | `/ai/timeline` | Generate a timestamped topic timeline |
| POST | `/ai/qa` | Answer a post-meeting natural language question (RAG across transcripts + documents) |

## 4.3 Key Pipelines

**Live Meeting Pipeline**: Participant speech → Daily.co WebRTC → audio track routing → Deepgram streaming STT → transcript storage → wake phrase detection → AI request queue → `ai-service` `/ai/respond` → ElevenLabs TTS → audio played into meeting.

**Proactive Fact-Check Pipeline**: Final transcript entry → `ai-service` `/ai/fact-check` (background, non-blocking) → vector search against document chunks only → if contradiction found above confidence threshold → enqueue correction in AI response queue → ElevenLabs TTS → audio into meeting + `fact.checked` event published. See architecture.md §5b.

**AI Teammate Reasoning**: Wake command with comparison language → `/ai/respond` detects reasoning intent → routing to reasoning-optimized prompt template → context includes rolling summary + last 20 turns + RAG document chunks → Claude generates explicit recommendation → ElevenLabs TTS → audio into meeting.

**Document Ingestion Pipeline**: User uploads file → `document-service` chunks file (200–400 tokens, 50-token overlap) → generates embeddings (text-embedding-3-large) → stores chunks in shared vector index tagged `source: "document"`. See architecture.md §5.

**Unified RAG Pipeline**: Wake word or Q&A query → `ai-service` generates query embedding → vector search across transcript chunks **and** document chunks simultaneously → top-k results injected as context → Claude generates response → source attribution returned (speaker+timestamp for transcripts, filename+excerpt for documents). See architecture.md §6.

**Audio Feedback Loop Prevention**: AI audio tracks are tagged with an AI source identifier and excluded from the STT pipeline to prevent self-transcription.

**Post-Meeting Processing Pipeline**: Meeting end event → `postprocessing-service` retrieves transcript → calls `ai-service` for summary, decisions, actions, timeline → chunks + embeds transcript → stores in vector index.

## 4.4 RAG Chunking Specification

| Parameter | Value |
|-----------|-------|
| Chunk size | 200–400 tokens |
| Chunk overlap | 50 tokens |
| Embedding model | `text-embedding-3-large` |
| Sources | Transcript chunks (`source: "transcript"`) + document chunks (`source: "document"`) |
| Index | Shared MongoDB Atlas Vector Search index per meeting |

This applies to **both** transcript chunks (generated post-meeting) and document chunks (generated at upload time).

## 4.5 Arni Bot Participant Model

Arni is represented as a system participant in every meeting to simplify audio tagging, transcript filtering, and feedback loop prevention:

```json
{
  "id": "arni",
  "name": "Arni",
  "type": "system",
  "audio_track_tag": "ai-source"
}
```

- All audio injected by Arni is tagged with `audio_track_tag: "ai-source"`
- The STT pipeline skips any track with this tag
- Transcripts are filtered to exclude `speaker_id: "arni"` from wake detection

## 4.6 Event Bus Schema

All events published to Redis Pub/Sub must conform to these schemas. Agents must not invent new event fields.

### `transcript.created`
```json
{
  "event": "transcript.created",
  "meeting_id": "string",
  "speaker_id": "string",
  "text": "string",
  "timestamp": "ISO-8601",
  "is_final": "boolean"
}
```

### Other Events

| Event | Key Fields |
|-------|------------|
| `wake.detected` | `meeting_id`, `speaker_id`, `command`, `timestamp` |
| `ai.requested` | `meeting_id`, `request_id`, `command`, `timestamp` |
| `ai.responded` | `meeting_id`, `request_id`, `response_text`, `source_type` (`"transcript"` \| `"document"` \| `"mixed"`), `timestamp` |
| `ai.state_changed` | `meeting_id`, `state` (`"idle"` \| `"listening"` \| `"processing"` \| `"speaking"`), `timestamp` |
| `fact.checked` | `meeting_id`, `speaker_id`, `original_claim`, `correction_text`, `source_document`, `source_excerpt`, `confidence_score`, `timestamp` |
| `meeting.started` | `meeting_id`, `host_id`, `timestamp` |
| `meeting.ended` | `meeting_id`, `host_id`, `timestamp` |
| `meeting.processed` | `meeting_id`, `timestamp` |
| `meeting.auto_ended` | `meeting_id`, `reason` (`"host_timeout"`), `timestamp` |
| `summary.updated` | `meeting_id`, `summary_text`, `timestamp` |
| `document.uploaded` | `meeting_id`, `document_id`, `filename`, `status` (`"processing"` \| `"ready"` \| `"error"`), `timestamp` |
| `participant.invited` | `meeting_id`, `email`, `invited_by` (user_id), `timestamp` |
| `participant.admitted` | `meeting_id`, `user_id`, `admitted_by` (user_id), `timestamp` |
| `participant.removed` | `meeting_id`, `user_id`, `removed_by` (user_id), `timestamp` |
| `participant.rejected` | `meeting_id`, `user_id`, `timestamp` |
| `host.transferred` | `meeting_id`, `old_host_id`, `new_host_id`, `timestamp` |

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

### Authentication (`auth-service`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new user with email/password |
| POST | `/auth/login` | Log in and receive JWT token |
| POST | `/auth/google` | Authenticate via Google OAuth |

### Meetings (`meeting-service`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/meetings/create` | Create a new meeting room; Arni added to participant list immediately (FR-073) |
| GET | `/meetings/{id}` | Get meeting details (participant-only) |
| DELETE | `/meetings/{id}` | Delete meeting and all associated data including documents and vector chunks (host only, FR-074) |
| POST | `/meetings/{id}/end` | End an active meeting and trigger post-processing (host only, FR-063) |
| POST | `/meetings/{id}/invite` | Add a participant by email to the invite list (host only, FR-061) |
| DELETE | `/meetings/{id}/participants/{user_id}` | Remove a participant immediately (host only, FR-062) |
| GET | `/meetings/{id}/waiting-room` | List participants currently in the waiting room (host only, FR-070) |
| POST | `/meetings/{id}/admit/{user_id}` | Admit a participant from the waiting room (host only, FR-071) |
| POST | `/meetings/{id}/reject/{user_id}` | Reject a waiting participant (host only, FR-072) |
| POST | `/meetings/{id}/transfer-host` | Transfer host role to another participant (host only, FR-066) |

### Documents (`document-service`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/meetings/{id}/documents` | Upload a reference document to a meeting (PDF, DOCX, TXT, ≤20 MB) |
| GET | `/meetings/{id}/documents` | List all uploaded documents for a meeting |
| DELETE | `/meetings/{id}/documents/{doc_id}` | Delete an uploaded document and its vector chunks |

### Real-Time (`realtime-gateway`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/meetings/{id}/stream` | WebSocket for live transcript, AI state, document upload status, and event streaming |

### AI Service (internal, `ai-service`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/respond` | Generate a real-time voice response; uses reasoning-optimized prompt when comparison language detected (FR-085) |
| POST | `/ai/fact-check` | Accept transcript excerpt + `meeting_id`; vector search against document chunks; return contradiction above threshold (FR-078–FR-079) |
| POST | `/ai/summarize` | Generate or update meeting rolling summary |
| POST | `/ai/extract-decisions` | Extract explicit decisions from transcript |
| POST | `/ai/extract-actions` | Extract explicit action items from transcript |
| POST | `/ai/timeline` | Generate timestamped topic timeline |
| POST | `/ai/qa` | Answer a post-meeting question (unified RAG across transcripts + documents) |

### Post-Meeting

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/meetings/{id}/transcript` | Retrieve full meeting transcript |
| GET | `/meetings/{id}/summary` | Retrieve meeting summary and report |
| POST | `/meetings/{id}/ask` | Ask a question about the meeting (unified RAG across transcripts + documents) |
| PATCH | `/meetings/{id}/action-items/{item_id}` | Update an action item (description, assignee, deadline) |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | Get user's meeting history (scoped to host + invited meetings only) |
| GET | `/meetings/search?q=` | Semantic/keyword search — scoped to authenticated user's own meetings only |

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
| host_id | ObjectId | Reference to User (mutable — changes on host transfer) |
| participant_ids | ObjectId[] | References to Users currently in the meeting (includes `"arni"` from creation) |
| invite_list | string[] | Email addresses authorized to join; checked against JWT identity on join attempt |
| state | enum | Created, Active, Ended, Processed |
| invite_link | string | Shareable meeting link |
| started_at | datetime | When meeting became Active |
| ended_at | datetime | When meeting was ended |
| host_grace_period_until | datetime | Set when host disconnects; null otherwise. If now > this value and host has not reconnected, meeting auto-ends |
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
| embedding | float[] | Vector embedding for semantic search (text-embedding-3-large) |
| source | string | Always `"transcript"` — used to distinguish from document chunks in unified search |

## 8.4 Document

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| uploaded_by | ObjectId | Reference to User who uploaded |
| filename | string | Original filename |
| file_type | string | `"pdf"`, `"docx"`, or `"txt"` |
| file_size_bytes | integer | File size |
| status | enum | `processing`, `ready`, `error` |
| chunk_count | integer | Number of chunks generated |
| uploaded_at | datetime | Upload timestamp |

## 8.5 Document Chunk

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| document_id | ObjectId | Reference to Document |
| filename | string | Source filename (for attribution) |
| chunk_index | integer | Position of chunk within the document |
| text | string | Chunk text content |
| embedding | float[] | Vector embedding for semantic search (text-embedding-3-large) |
| source | string | Always `"document"` — used to distinguish from transcript chunks in unified search |

## 8.6 Arni Bot Participant

Arni is treated as a fixed system participant in all meetings — not stored in the User collection, but used for audio tagging and transcript filtering:

```json
{
  "id": "arni",
  "name": "Arni",
  "type": "system",
  "audio_track_tag": "ai-source"
}
```

## 8.7 Action Item

| Field | Type | Description |
|-------|------|-------------|
| id | ObjectId | Unique identifier |
| meeting_id | ObjectId | Reference to Meeting |
| description | string | Task description |
| assignee | string | Assigned person (editable) |
| deadline | string | Due date (editable) |
| is_edited | boolean | Whether manually edited by a user |
| created_at | datetime | Extraction timestamp |

## 8.8 Meeting Summary (Rolling)

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
| Fact-check confidence threshold | 0.85 | Minimum vector similarity score required to trigger a fact-check correction (FR-079) |
| Fact-check cooldown | 30 seconds | Minimum time between consecutive fact-check corrections per meeting (FR-081) |

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
- Document chunking: correct token boundaries and overlap
- Event schema validation: all published events conform to §4.6 schema
- Fact-check: confidence threshold enforcement; cooldown prevents double-trigger within 30 seconds
- Reasoning detection: comparison language correctly routes to reasoning-optimized prompt

## 14.2 Integration Tests

- Full audio pipeline: audio input → STT → transcript storage → wake detection → LLM → TTS → audio output
- Document upload pipeline: upload file → chunk → embed → store → confirm chunks appear in vector index
- Unified RAG: question answered using both transcript and document chunks; source attribution correct for both
- **Proactive fact-check**: upload doc with known metric → participant states wrong metric → verify Arni interjects with correction citing doc name + excerpt
- **AI teammate reasoning**: wake command with "which do you recommend" → verify response includes explicit recommendation + justification
- Post-meeting processing pipeline: meeting end → summary + decisions + timeline + embeddings
- Authentication flows (registration, login, Google OAuth, JWT validation)

## 14.3 End-to-End Tests

- Complete meeting lifecycle: create → join → transcribe → interact with AI → end → view report
- Multi-participant meeting with concurrent wake triggers
- User disconnection and reconnection during active meeting
- Fact-check does not trigger when no documents are uploaded (FR-084)

## 14.4 Performance Tests

- Measure AI response latency under load (multiple concurrent meetings)
- Measure transcript latency with varying audio quality
- Verify system behavior at rate limit boundaries
- Verify fact-check runs non-blocking: transcript pipeline must not stall waiting for `/ai/fact-check` response

---

# 15. Future Enhancements

| Feature | Description |
|---------|-------------|
| Cross-Meeting Memory | Arni can answer questions about previous meetings by searching across a user-scoped vector index spanning all past meetings. Requires a global vector index partitioned by user/organization, retrieval strategy for multi-meeting context, and citation logic across meeting boundaries. |
| Proactive AI participation | Arni contributes unprompted when relevant (e.g., reminding of agenda items) |
| Meeting analytics | Speaking time distribution, participant engagement, interruption tracking, sentiment analysis |
| Platform integrations | Zoom, Google Meet, Microsoft Teams meeting joining |
| Productivity integrations | Slack notifications, Notion export |
| Mobile support | Native iOS and Android applications |
| Multi-language support | Transcription and AI responses in languages beyond English |
