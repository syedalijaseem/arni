# Arni — Voice AI Meeting Participant

Project Outline

## Agent Name

**Arni**

Arni is an AI meeting participant that joins meetings, listens to conversations, responds when addressed, and converts meetings into a searchable knowledge base.

---

# 1. Project Overview

## Elevator Pitch

Arni is a real time AI meeting participant that joins web based meeting rooms, listens to conversations, responds with voice when addressed, and automatically converts meetings into a searchable knowledge base.

---

## Target Users

- Remote teams
- Students and academic project groups
- Professionals running frequent meetings
- Small organizations

---

## Primary Value

Unlike passive meeting recorders, Arni acts as an **active participant** that can:

- answer questions during meetings
- summarize discussions on demand
- generate structured meeting reports
- enable semantic search across past meetings

---

# 2. System Scope

## In Scope (MVP)

The system will support:

- Meeting room creation
- Invite links for participants
- AI participant joining meetings
- Real time transcription
- Speaker labeling
- AI responses when addressed
- Meeting summaries
- Meeting history dashboard
- Question answering over transcripts

---

## Out of Scope (MVP)

The following features are excluded from the initial version:

- Zoom / Google Meet / Microsoft Teams integration
- Mobile applications
- Fine tuned AI models
- Calendar integration
- Slack or Notion integrations
- Enterprise multi organization features

---

# 3. Core Functional Capabilities

---

## 3.1 Meeting Creation

Users can:

- create meeting rooms
- generate shareable invite links
- invite participants

Arni automatically joins the meeting as a participant.

---

## 3.2 Real Time Meeting Participation

During meetings:

- audio streams are captured via WebRTC
- speech is transcribed in real time
- transcripts appear live in the interface

Each transcript entry includes **speaker labels**.

---

## 3.3 Speaker Identification Strategy

Speaker identification uses **Daily.co participant audio tracks**.

Pipeline:

Participant Audio Track
↓
Track ID mapped to User ID
↓
Deepgram Speech to Text
↓
Transcript stored with speaker_id

Benefits:

- accurate speaker identification
- improved AI context understanding
- enables future meeting analytics

---

## 3.4 Wake Word Detection

Participants can trigger Arni using a wake phrase.

Example:

"Hey Arni, summarize what we've discussed so far."

The system detects the wake phrase and triggers the response pipeline.

---

## 3.5 Smart Wake Word Detection

Wake detection follows the pattern:

Wake word + command

Examples:

- Hey Arni summarize
- Hey Arni what did John say
- Hey Arni what is the next step

Detection methods may include:

- regex pattern detection
- optional LLM classification

---

## 3.6 AI Response Queue

Multiple participants may trigger the AI simultaneously.

To prevent overlapping responses, triggers are placed into a **response queue**.

Pipeline:

Wake Word Event
↓
Added to AI Request Queue
↓
Processed sequentially

---

## 3.7 Voice Response

When triggered:

1. LLM generates a response
2. response is converted to speech
3. audio is injected into the meeting

Participants hear Arni as another meeting participant.

---

## 3.8 Interrupt Handling

Human speech should interrupt AI speech.

Logic:

If participant speech detected
AND Arni currently speaking
→ stop AI playback
→ resume listening

This uses **Voice Activity Detection (VAD)**.

---

## 3.9 Conversation Context Strategy

AI responses rely on a hybrid context model:

Meeting Summary So Far

- Recent Conversation (last 20 turns)

Benefits:

- reduces token usage
- improves reasoning
- supports longer meetings

---

## 3.10 Periodic Auto Summaries

The system generates **rolling summaries every 10 minutes**.

Benefits:

- improves long meeting context
- improves final summary accuracy

---

## 3.11 Post Meeting Intelligence

When a meeting ends, Arni generates:

- meeting title
- meeting summary
- key decisions
- action items

---

## 3.12 AI Safety and Hallucination Control

Arni should only extract **explicitly stated decisions**.

Prompt rule:

Extract decisions ONLY if explicitly stated.
Do not infer decisions.

---

## 3.13 Editable Action Items

AI generated tasks must be editable by users.

This allows correction of:

- incorrect assignees
- misinterpreted tasks
- incorrect deadlines

---

## 3.14 Meeting Timeline

Meetings include a topic timeline.

Example:

0:00 Introductions
3:40 Budget discussion
12:10 Hiring plans
20:30 Action items

Timeline is generated using **topic segmentation**.

---

## 3.15 Meeting History Dashboard

Users can view:

- past meetings
- summaries
- participants
- durations
- action items

Each meeting has a detailed report page.

---

## 3.16 Post Meeting Question Answering

Users can ask questions about past meetings.

Example:

"What did we decide about the budget?"

The system retrieves relevant transcript segments and generates answers.

---

## 3.17 Source Attribution

Each AI answer displays the **source transcript excerpt**.

Example:

Answer:
The team decided to postpone budget approval.

Source:
John: "Let's delay budget approval until next week."

---

## 3.18 Meeting Analytics (Future)

Future analytics may include:

- speaking time distribution
- participant engagement
- interruptions
- sentiment analysis

---

# 4. System Architecture

The system consists of:

1. Frontend client
2. Backend API
3. Real time audio pipeline
4. AI processing layer
5. Data storage layer
6. Event bus layer

---

## 4.1 Event Bus Layer

Real time events are managed through a messaging system.

Example events:

- audio events
- wake word events
- AI response events
- meeting end events

Recommended technology:

**Redis Pub/Sub**

---

## 4.2 Live Meeting Pipeline

Participant Speech
↓
Daily.co WebRTC Stream
↓
Audio Track Routing
↓
Deepgram Streaming STT
↓
Transcript Storage
↓
Wake Word Detection
↓
AI Request Queue
↓
Claude Response Generation
↓
ElevenLabs TTS
↓
Audio Played into Meeting

---

## 4.3 Audio Feedback Loop Prevention

AI audio must not be transcribed.

Solution:

AI Audio Track
↓
Tagged as AI source
↓
Excluded from STT pipeline

---

## 4.4 Post Meeting Processing Pipeline

Meeting End Event
↓
Transcript Retrieval
↓
Summary Generation
↓
Decision Extraction
↓
Transcript Chunking
↓
Embedding Generation
↓
Vector Index Storage

---

## 4.5 Question Answering Pipeline

User Question
↓
Embedding Generation
↓
Vector Search
↓
Relevant Transcript Chunks
↓
LLM Response Generation

---

# 5. Technology Stack

| Layer                | Technology         |
| -------------------- | ------------------ |
| Frontend             | React + Tailwind   |
| Backend              | FastAPI            |
| Audio Infrastructure | Daily.co           |
| Speech to Text       | Deepgram Nova      |
| LLM                  | Claude Sonnet      |
| Text to Speech       | ElevenLabs         |
| Database             | MongoDB            |
| Vector Search        | MongoDB Atlas      |
| Event Bus            | Redis              |
| Auth                 | JWT + Google OAuth |
| Deployment           | Fly.io + Vercel    |
| Containerization     | Docker             |

---

# 6. Frontend Pages

- Landing page
- Authentication pages
- Dashboard
- Meeting room
- Post meeting report page

---

## 6.1 AI Status Indicator

The interface shows Arni’s state.

Possible states:

- Listening
- Thinking
- Speaking
- Idle

Example:

Arni is listening...
Arni is generating response...
Arni is speaking...

---

# 7. Backend API

### Authentication

POST /auth/register
POST /auth/login
POST /auth/google

### Meetings

POST /meetings/create
GET /meetings/{id}
DELETE /meetings/{id}
POST /meetings/{id}/end

### Real Time

WS /meetings/{id}/stream

### Post Meeting

GET /meetings/{id}/transcript
GET /meetings/{id}/summary
POST /meetings/{id}/ask

### Dashboard

GET /dashboard
GET /meetings/search?q=

---

# 8. Data Models

Primary entities:

- User
- Meeting
- Transcript Chunk
- Meeting Summary

Transcript chunks include:

- speaker_id
- timestamp
- text
- embedding

---

# 9. Non Functional Requirements

### Performance

Target AI response latency:

**under 2 seconds**

Transcript delay:

**under 1 second**

---

### Meeting Duration

Maximum supported meeting duration:

**2 hours**

---

### Scalability

Initial capacity:

**5 to 10 concurrent meetings**

---

### Availability

Target uptime:

**99 percent**

---

# 10. Reliability and Error Handling

### STT Failure

System attempts automatic reconnection.

---

### TTS Failure

AI response text is displayed instead of audio.

---

### LLM Failure

Fallback response is returned.

---

### User Disconnection

Users may reconnect without losing transcript continuity.

---

# 11. Rate Limiting

Wake word cooldown:

**10 seconds**

Maximum AI responses per meeting:

**30**

Post meeting query limit:

**20**

---

# 12. Security and Privacy

Meeting data security includes:

- TLS encryption in transit
- encrypted transcripts at rest
- access restricted to meeting participants

---

# 13. Operational Constraints

Deepgram free tier:

~12,000 transcription minutes per month

ElevenLabs:

character generation limits

Daily.co:

limited concurrent meeting rooms

---

# 14. Observability and Metrics

System metrics include:

- STT latency
- LLM latency
- TTS latency
- total response latency
- meeting duration
- number of AI interactions

Possible tools:

- OpenTelemetry
- Prometheus
- Grafana

---

# 15. Future Enhancements

Potential improvements include:

- proactive AI participation
- enterprise meeting analytics
- Zoom / Meet integrations
- Slack integrations
- mobile applications
