"""
Strictly typed Pydantic v2 event schemas for the Arni event bus.

All 17 event types are defined here. Every schema uses ConfigDict(extra="forbid")
so that any undocumented field raises a ValidationError at publish time.

Channel naming convention: arni:{meeting_id}:{event_type}
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict


class _BaseEvent(BaseModel):
    """Shared base: forbid any extra fields on all event schemas."""

    model_config = ConfigDict(extra="forbid")

    meeting_id: str
    timestamp: float


# ---------------------------------------------------------------------------
# 1. transcript.created
# ---------------------------------------------------------------------------

class TranscriptCreatedEvent(_BaseEvent):
    event: Literal["transcript.created"] = "transcript.created"
    speaker_id: str
    text: str
    is_final: bool


# ---------------------------------------------------------------------------
# 2. wake.detected
# ---------------------------------------------------------------------------

class WakeDetectedEvent(_BaseEvent):
    event: Literal["wake.detected"] = "wake.detected"
    speaker_id: str
    command: str


# ---------------------------------------------------------------------------
# 3. ai.requested
# ---------------------------------------------------------------------------

class AIRequestedEvent(_BaseEvent):
    event: Literal["ai.requested"] = "ai.requested"
    request_id: str
    command: str


# ---------------------------------------------------------------------------
# 4. ai.responded
# ---------------------------------------------------------------------------

class AIRespondedEvent(_BaseEvent):
    event: Literal["ai.responded"] = "ai.responded"
    request_id: str
    response_text: str
    source_type: Literal["transcript", "document", "mixed"]


# ---------------------------------------------------------------------------
# 5. ai.state_changed
# ---------------------------------------------------------------------------

class AIStateChangedEvent(_BaseEvent):
    event: Literal["ai.state_changed"] = "ai.state_changed"
    state: Literal["idle", "listening", "processing", "speaking"]


# ---------------------------------------------------------------------------
# 6. fact.checked
# ---------------------------------------------------------------------------

class FactCheckedEvent(_BaseEvent):
    event: Literal["fact.checked"] = "fact.checked"
    speaker_id: str
    original_claim: str
    correction_text: str
    source_document: str
    source_excerpt: str
    confidence_score: float


# ---------------------------------------------------------------------------
# 7. meeting.started
# ---------------------------------------------------------------------------

class MeetingStartedEvent(_BaseEvent):
    event: Literal["meeting.started"] = "meeting.started"
    host_id: str


# ---------------------------------------------------------------------------
# 8. meeting.ended
# ---------------------------------------------------------------------------

class MeetingEndedEvent(_BaseEvent):
    event: Literal["meeting.ended"] = "meeting.ended"
    host_id: str


# ---------------------------------------------------------------------------
# 9. meeting.processed
# ---------------------------------------------------------------------------

class MeetingProcessedEvent(_BaseEvent):
    event: Literal["meeting.processed"] = "meeting.processed"


# ---------------------------------------------------------------------------
# 10. meeting.auto_ended
# ---------------------------------------------------------------------------

class MeetingAutoEndedEvent(_BaseEvent):
    event: Literal["meeting.auto_ended"] = "meeting.auto_ended"
    reason: Literal["host_timeout"]


# ---------------------------------------------------------------------------
# 11. summary.updated
# ---------------------------------------------------------------------------

class SummaryUpdatedEvent(_BaseEvent):
    event: Literal["summary.updated"] = "summary.updated"
    summary_text: str


# ---------------------------------------------------------------------------
# 12. document.uploaded
# ---------------------------------------------------------------------------

class DocumentUploadedEvent(_BaseEvent):
    event: Literal["document.uploaded"] = "document.uploaded"
    document_id: str
    filename: str
    status: Literal["processing", "ready", "error"]


# ---------------------------------------------------------------------------
# 13. participant.invited
# ---------------------------------------------------------------------------

class ParticipantInvitedEvent(_BaseEvent):
    event: Literal["participant.invited"] = "participant.invited"
    email: str
    invited_by: str


# ---------------------------------------------------------------------------
# 14. participant.admitted
# ---------------------------------------------------------------------------

class ParticipantAdmittedEvent(_BaseEvent):
    event: Literal["participant.admitted"] = "participant.admitted"
    user_id: str
    admitted_by: str


# ---------------------------------------------------------------------------
# 15. participant.removed
# ---------------------------------------------------------------------------

class ParticipantRemovedEvent(_BaseEvent):
    event: Literal["participant.removed"] = "participant.removed"
    user_id: str
    removed_by: str


# ---------------------------------------------------------------------------
# 16. participant.rejected
# ---------------------------------------------------------------------------

class ParticipantRejectedEvent(_BaseEvent):
    event: Literal["participant.rejected"] = "participant.rejected"
    user_id: str


# ---------------------------------------------------------------------------
# 17. host.transferred
# ---------------------------------------------------------------------------

class HostTransferredEvent(_BaseEvent):
    event: Literal["host.transferred"] = "host.transferred"
    old_host_id: str
    new_host_id: str
