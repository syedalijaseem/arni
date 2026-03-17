# Arni — System Architecture

Version: 1.0
Date: 2026-03-16

Detailed architecture diagrams and pipeline specifications for the Arni system.

For requirements, see [srs.md](srs.md).

---

## Table of Contents

1. [System Architecture Diagram](#1-system-architecture-diagram)
2. [Live Meeting Pipeline](#2-live-meeting-pipeline)
3. [Audio Feedback Loop Prevention](#3-audio-feedback-loop-prevention)
4. [Post-Meeting Processing Pipeline](#4-post-meeting-processing-pipeline)
5. [Question Answering Pipeline (RAG)](#5-question-answering-pipeline-rag)
6. [Event Bus](#6-event-bus)
7. [Meeting Initialization Sequence](#7-meeting-initialization-sequence)
8. [Live Meeting Sequence Diagram](#8-live-meeting-sequence-diagram)
9. [Post-Meeting Processing Sequence Diagram](#9-post-meeting-processing-sequence-diagram)
10. [Rolling Auto-Summary Flow](#10-rolling-auto-summary-flow)

---

## 1. System Architecture Diagram

```mermaid
flowchart TB
    subgraph Client ["Frontend (React + Tailwind)"]
        UI["Meeting UI"]
        Dash["Dashboard"]
        Report["Post-Meeting Report"]
    end

    subgraph Backend ["Backend API (FastAPI)"]
        API["REST API"]
        WS["WebSocket Server"]
        Auth["Auth (JWT + OAuth)"]
        PostProc["Post-Meeting Processor"]
        AutoSum["Auto-Summary Scheduler"]
    end

    subgraph Audio ["Audio Pipeline"]
        Daily["Daily.co WebRTC"]
        Deepgram["Deepgram Nova STT"]
        EL["ElevenLabs TTS"]
    end

    subgraph AI ["AI Processing Layer"]
        Wake["Wake Phrase Detection"]
        Queue["AI Request Queue"]
        Claude["Claude Sonnet LLM"]
        Context["Context Manager"]
    end

    subgraph Storage ["Data Storage"]
        Mongo[("MongoDB Atlas")]
        Vector[("Vector Index")]
    end

    Redis{{"Redis Pub/Sub"}}

    UI <-->|"WebSocket"| WS
    UI <-->|"WebRTC Audio"| Daily
    Dash & Report <-->|"REST"| API
    API & WS <--> Auth

    Daily -->|"Audio Tracks"| Deepgram
    Deepgram -->|"Transcripts"| BE_Store
    BE_Store["Backend: Store"] -->|"Persist"| Mongo
    BE_Store -->|"Publish"| Redis
    Redis -->|"Transcript Events"| Wake
    Redis -->|"Transcript Events"| FE_Display["Frontend: Live Display"]
    Wake -->|"Wake Events"| Queue
    Queue --> Context
    Context -->|"Prompt"| Claude
    Context <-->|"Summary + Turns"| Mongo
    Claude -->|"Response Text"| EL
    EL -->|"Audio"| Daily

    Redis -->|"State Events"| WS
    API <--> Mongo
    API <--> Vector

    AutoSum -->|"Summary Prompt"| Claude
    AutoSum <-->|"Read/Write"| Mongo

    PostProc -->|"Summary + Extraction"| Claude
    PostProc -->|"Embeddings"| Vector
    PostProc <-->|"Read/Write"| Mongo
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

## 5. Question Answering Pipeline (RAG)

```mermaid
flowchart LR
    A["User Question"] --> B["Embedding\nGeneration"]
    B --> C["Vector\nSearch"]
    C --> D["Relevant\nTranscript Chunks"]
    D --> E["LLM Response\nGeneration"]
    E --> F["Answer with\nSource Attribution"]
```

---

## 6. Event Bus

Real-time events are managed through **Redis Pub/Sub**.

| Event Type | Description |
|------------|-------------|
| Audio stream events | New audio track connected/disconnected |
| Transcript events | New interim/final transcript available |
| Wake word events | Wake phrase detected in transcript |
| AI state change events | Idle → Listening → Processing → Speaking |
| AI response events | AI response text/audio ready |
| Meeting lifecycle events | Meeting created, started, ended |
| Auto-summary events | Rolling summary regenerated |
| Error events | STT/LLM/TTS failures, reconnections |

---

## 7. Meeting Initialization Sequence

Triggered when the first participant joins a meeting.

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
    API ->> DG: Open STT stream
    DG -->> API: STT stream connected
    API ->> Redis: Publish meeting.started event
    Redis ->> FE: Meeting active

    Note over FE: AI State → Listening
    API ->> Redis: Publish AI state → Listening
    Redis ->> FE: Update AI indicator

    FE ->> Daily: Connect participant audio track
    Daily ->> DG: Begin forwarding audio
```

---

## 8. Live Meeting Sequence Diagram

Full request lifecycle from participant speech through AI response, including interrupt and error fallback paths.

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

## 9. Post-Meeting Processing Sequence Diagram

Triggered when the host ends the meeting. All processing steps run asynchronously on the backend.

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

## 10. Rolling Auto-Summary Flow

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
