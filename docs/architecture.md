# Arni — System Architecture

Version: 3.0
Date: 2026-04-11

Detailed architecture diagrams and pipeline specifications for the Arni system.

For requirements, see [srs.md](srs.md).

---

## Table of Contents

1. [System Architecture Diagram](#1-system-architecture-diagram)
2. [Live Meeting Pipeline](#2-live-meeting-pipeline)
3. [Audio Feedback Loop Prevention](#3-audio-feedback-loop-prevention)
4. [Post-Meeting Processing Pipeline](#4-post-meeting-processing-pipeline)
5. [Document Ingestion Pipeline](#5-document-ingestion-pipeline)
5b. [Proactive Fact-Check Pipeline](#5b-proactive-fact-check-pipeline)
6. [Unified RAG Pipeline](#6-unified-rag-pipeline-question-answering)
7. [Event Bus Schema](#7-event-bus-schema)
8. [Meeting Initialization Sequence](#8-meeting-initialization-sequence)
9. [Live Meeting Sequence Diagram](#9-live-meeting-sequence-diagram)
10. [Post-Meeting Processing Sequence Diagram](#10-post-meeting-processing-sequence-diagram)
11. [Rolling Auto-Summary Flow](#11-rolling-auto-summary-flow)

---

## 1. System Architecture Diagram

```mermaid
flowchart TB
    subgraph Client ["Frontend (React + Tailwind)"]
        UI["Meeting UI"]
        Dash["Dashboard"]
        Report["Post-Meeting Report"]
        DocUpload["Document Upload Panel"]
    end

    subgraph AuthSvc ["auth-service"]
        Auth["JWT + Google OAuth"]
    end

    subgraph MeetingSvc ["meeting-service"]
        API["Meeting REST API"]
    end

    subgraph TranscriptSvc ["transcript-service"]
        Deepgram["Deepgram Nova STT"]
        Wake["Wake Phrase Detector"]
        TStore["Transcript Store"]
    end

    subgraph DocSvc ["document-service"]
        DocAPI["Document Upload API"]
        Chunker["Chunker (200-400 tok, 50 overlap)"]
        DocEmbed["Embedder (text-embedding-3-large)"]
    end

    subgraph AISvc ["ai-service"]
        Queue["AI Request Queue"]
        Context["Context Manager"]
        Claude["Claude Sonnet LLM"]
        EL["ElevenLabs TTS"]
    end

    subgraph PostProc ["postprocessing-service"]
        PPipe["Summary / Decisions / Actions / Timeline"]
        TEmbed["Transcript Embedder"]
    end

    subgraph AutoSumSvc ["Auto-Summary Scheduler"]
        AutoSum["Rolling Summarizer"]
    end

    subgraph Gateway ["realtime-gateway"]
        WS["WebSocket Server"]
    end

    subgraph Audio ["Audio Infrastructure"]
        Daily["Daily.co WebRTC"]
    end

    subgraph Storage ["Data Storage"]
        Mongo[("MongoDB Atlas")]
        Vector[("Unified Vector Index\n(transcript + document chunks)")]
    end

    Redis{{"Redis Pub/Sub"}}

    UI <-->|"WebSocket"| WS
    UI <-->|"WebRTC Audio"| Daily
    Dash & Report <-->|"REST"| API
    DocUpload -->|"POST /meetings/{id}/documents"| DocAPI
    API & WS <--> Auth

    Daily -->|"Audio Tracks (tagged)"| Deepgram
    Deepgram -->|"Final Transcripts"| TStore
    TStore -->|"Persist"| Mongo
    TStore -->|"Publish transcript.created"| Redis
    Redis -->|"transcript.created"| Wake
    Redis -->|"transcript.created"| WS
    Wake -->|"wake.detected"| Redis
    Redis -->|"wake.detected"| Queue
    Queue --> Context
    Context -->|"Unified RAG Query"| Vector
    Context <-->|"Summary + Turns"| Mongo
    Context -->|"Prompt + RAG Context"| Claude
    Claude -->|"Response Text"| EL
    EL -->|"Audio (tagged ai-source)"| Daily

    DocAPI --> Chunker
    Chunker --> DocEmbed
    DocEmbed -->|"source: document"| Vector
    DocAPI -->|"Publish document.uploaded"| Redis

    Redis -->|"State Events"| WS
    API <--> Mongo

    AutoSum -->|"POST /ai/summarize"| AISvc
    AutoSum <-->|"Read/Write"| Mongo

    PPipe -->|"POST /ai/summarize, /ai/extract-*"| AISvc
    TEmbed -->|"source: transcript"| Vector
    PPipe <-->|"Read/Write"| Mongo
```

---

## 2. Live Meeting Pipeline

```mermaid
flowchart LR
    A["Participant Speech"] --> B["Daily.co\nWebRTC Stream"]
    B --> C["Audio Track\nRouting"]
    C --> D["Deepgram\nStreaming STT"]
    D --> E["Transcript\nStorage"]
    E --> F["Wake Phrase\nDetection"]
    F --> G["AI Request\nQueue"]
    G --> H["Claude\nResponse Gen"]
    H --> I["ElevenLabs\nTTS"]
    I --> J["Audio Played\ninto Meeting"]
```

---

## 3. Audio Feedback Loop Prevention

AI-generated audio must never be transcribed back into the meeting transcript.

```mermaid
flowchart LR
    A["AI Audio Track"] --> B["Tagged as\nAI Source"]
    B --> C["Excluded from\nSTT Pipeline"]
```

---

## 4. Post-Meeting Processing Pipeline

```mermaid
flowchart LR
    A["Meeting End\nEvent"] --> B["Transcript\nRetrieval"]
    B --> C["Summary\nGeneration"]
    C --> D["Decision &\nAction Extraction"]
    D --> E["Timeline\nGeneration"]
    E --> F["Transcript\nChunking"]
    F --> G["Embedding\nGeneration"]
    G --> H["Vector Index\nStorage"]
```

---

## 5. Document Ingestion Pipeline

Triggered immediately after a user uploads a document (`PDF`, `DOCX`, or `TXT`) to a meeting room.

```mermaid
flowchart LR
    A["User Upload\n(PDF/DOCX/TXT)"] --> B["document-service\nValidation"]
    B --> C["Text Extraction"]
    C --> D["Chunking\n200-400 tokens\n50-token overlap"]
    D --> E["Embedding\n(text-embedding-3-large)"]
    E --> F["Vector Index\nsource: 'document'\n+ filename"]
    B --> G["Publish\ndocument.uploaded\n(status: processing)"]
    F --> H["Publish\ndocument.uploaded\n(status: ready)"]
```

---

## 6. Unified RAG Pipeline (Question Answering)

Used both during live meetings (`/ai/respond`) and post-meeting Q&A (`/ai/qa`). Pulls context from **both** transcript and document chunks simultaneously.

```mermaid
flowchart LR
    A["User Question /\nWake Command"] --> B["Embedding\nGeneration\n(text-embedding-3-large)"]
    B --> C["Unified Vector\nSearch"]
    C --> D1["Transcript Chunks\n(source: transcript)"]
    C --> D2["Document Chunks\n(source: document)"]
    D1 & D2 --> E["Context Assembly +\nPrompt Construction"]
    E --> F["Claude Sonnet\nResponse Generation"]
    F --> G["Answer + Source Attribution\n(speaker+timestamp / filename+excerpt)"]
```

---

## 7. Event Bus Schema

All events published to **Redis Pub/Sub** must conform to the following schemas. Consumers must not rely on undocumented fields.

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

### All Event Schemas

| Event | Required Fields |
|-------|----------------|
| `transcript.created` | `meeting_id`, `speaker_id`, `text`, `timestamp`, `is_final` |
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

## 8. Meeting Initialization Sequence

Triggered when the **first admitted participant** joins a meeting. Arni is already present in the participant list from the moment the meeting was created (FR-008).

```mermaid
sequenceDiagram
    actor P as First Participant
    participant FE as Frontend UI
    participant API as Backend API
    participant Daily as Daily.co
    participant DG as Deepgram STT
    participant Redis as Redis Pub/Sub

    P ->> FE: Join meeting via invite link
    FE ->> API: POST /meetings/{id}/join
    API ->> API: Check: first participant?

    Note over API: First participant → initialize

    API ->> API: Meeting state → Active
    API ->> Daily: Provision room (if needed)
    Daily -->> API: Room ready
    API ->> DG: Open STT stream (exclude tracks tagged ai-source)
    DG -->> API: STT stream connected
    API ->> Redis: Publish meeting.started
    Redis ->> FE: Meeting active

    Note over FE: AI State → Listening
    API ->> Redis: Publish ai.state_changed (listening)
    Redis ->> FE: Update AI indicator

    FE ->> Daily: Connect participant audio track
    Daily ->> DG: Begin forwarding audio
```

---

## 9. Live Meeting Sequence Diagram

Full request lifecycle from participant speech through AI response, including unified RAG context, interrupt, and error fallback paths.

```mermaid
sequenceDiagram
    actor P as Participant
    participant Daily as Daily.co
    participant DG as Deepgram STT
    participant BE as Backend API
    participant Redis as Redis Pub/Sub
    participant Wake as Wake Detector
    participant Queue as AI Queue
    participant Claude as Claude LLM
    participant EL as ElevenLabs TTS
    participant FE as Frontend UI

    Note over P, FE: Meeting Active — AI in Listening State

    P ->> Daily: Speak into meeting
    Daily ->> DG: Forward audio track
    DG ->> BE: Interim transcript
    BE ->> Redis: Publish transcript event
    Redis ->> FE: Display live transcript
    DG ->> BE: Final transcript
    BE ->> BE: Store transcript chunk

    BE ->> Wake: Check for wake phrase
    Wake -->> BE: Wake phrase detected

    Note over FE: AI State → Processing
    BE ->> Redis: Publish state change
    Redis ->> FE: Update AI indicator

    BE ->> Queue: Enqueue AI request
    Queue ->> Queue: Check cooldown & rate limits

    Note over Queue: Unified RAG: vector search across transcript + document chunks

    alt Rate limit / cooldown exceeded
        Queue ->> Redis: Publish rate limit message
        Redis ->> FE: Display limit message
        Queue ->> Redis: Publish AI state → Listening
        Redis ->> FE: Update AI indicator
    else Within limits
        Queue ->> Claude: Send prompt (system instruction + summary + recent turns)

        alt LLM failure (NFR-011)
            Claude --x Queue: Error / timeout
            Queue ->> Redis: Publish fallback text response
            Redis ->> FE: Display fallback message in chat
            Queue ->> Redis: Publish AI state → Listening
            Redis ->> FE: Update AI indicator
        else LLM success
            Claude -->> Queue: Response text

            Note over FE: AI State → Speaking
            Queue ->> Redis: Publish state change
            Redis ->> FE: Update AI indicator

            Queue ->> EL: Convert response to speech

            alt TTS failure (NFR-010)
                EL --x Queue: Error / timeout
                Queue ->> Redis: Publish text-only response
                Redis ->> FE: Display response as text in chat
                Queue ->> Redis: Publish AI state → Listening
                Redis ->> FE: Update AI indicator
            else TTS success
                EL -->> Queue: Audio stream
                Queue ->> Daily: Inject audio (tagged as AI)
                Daily ->> P: Play AI audio

                Note over FE: AI State → Listening
                Queue ->> Redis: Publish state change
                Redis ->> FE: Update AI indicator
            end
        end
    end

    Note over P, FE: Interrupt Scenario
    P ->> Daily: Speak during AI playback
    Daily ->> BE: VAD detects human speech
    BE ->> Daily: Stop AI audio playback
    BE ->> Redis: Publish state → Listening
    Redis ->> FE: Update AI indicator
```

---

## 10. Post-Meeting Processing Sequence Diagram

Triggered when the host ends the meeting. All processing steps run asynchronously via `postprocessing-service`, which calls `ai-service` internally.

```mermaid
sequenceDiagram
    actor H as Host
    participant FE as Frontend UI
    participant API as Backend API
    participant Mongo as MongoDB
    participant Claude as Claude LLM
    participant Vector as Vector Index
    participant Redis as Redis Pub/Sub

    H ->> FE: End meeting
    FE ->> API: POST /meetings/{id}/end
    API ->> API: Meeting state → Ended
    API ->> Redis: Publish meeting.ended event
    Redis ->> FE: Display "Meeting ended, processing..."

    Note over API: Async post-processing begins

    API ->> Mongo: Retrieve full transcript
    Mongo -->> API: Transcript chunks

    API ->> Claude: Generate meeting title + summary
    Claude -->> API: Title + summary

    API ->> Claude: Extract decisions (explicit only)
    Claude -->> API: Decisions list

    API ->> Claude: Extract action items (explicit only)
    Claude -->> API: Action items

    API ->> Claude: Generate topic timeline
    Claude -->> API: Timestamped topics

    API ->> Mongo: Store summary, decisions, action items, timeline

    Note over API: Embedding generation

    API ->> API: Chunk transcript into segments
    loop For each transcript chunk
        API ->> API: Generate embedding
        API ->> Vector: Store chunk + embedding
    end

    API ->> API: Meeting state → Processed
    API ->> Redis: Publish meeting.processed event
    Redis ->> FE: Report ready notification
```

---

## 11. Rolling Auto-Summary Flow

During active meetings, the system regenerates a rolling summary every 10 minutes to maintain context for long meetings.

```mermaid
sequenceDiagram
    participant Scheduler as Auto-Summary Scheduler
    participant Mongo as MongoDB
    participant Claude as Claude LLM
    participant Redis as Redis Pub/Sub

    Note over Scheduler: Triggers every 10 minutes during active meeting

    Scheduler ->> Mongo: Fetch previous rolling summary
    Mongo -->> Scheduler: Last summary (or empty if first)

    Scheduler ->> Mongo: Fetch transcript since last summary
    Mongo -->> Scheduler: New transcript turns

    alt New turns exist
        Scheduler ->> Claude: Generate updated summary (previous + new turns)
        Claude -->> Scheduler: Updated rolling summary
        Scheduler ->> Mongo: Store new rolling summary
        Scheduler ->> Redis: Publish summary.updated event
    else No new turns
        Note over Scheduler: Skip — no new content
    end
```
