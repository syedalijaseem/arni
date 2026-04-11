"""
Typed publish functions for the Arni event bus.

Each function constructs the appropriate Pydantic schema (which validates all
fields and forbids extras), then serialises to JSON and publishes to the
Redis channel:  arni:{meeting_id}:{event_type}

The ``redis`` parameter accepts any object with an async ``publish(channel, message)``
method, making the functions trivially testable with an AsyncMock.
"""

import json
import logging
from typing import Any

from app.events.schemas import (
    AIRequestedEvent,
    AIRespondedEvent,
    AIStateChangedEvent,
    DocumentUploadedEvent,
    FactCheckedEvent,
    HostTransferredEvent,
    MeetingAutoEndedEvent,
    MeetingEndedEvent,
    MeetingProcessedEvent,
    MeetingStartedEvent,
    ParticipantAdmittedEvent,
    ParticipantInvitedEvent,
    ParticipantRejectedEvent,
    ParticipantRemovedEvent,
    SummaryUpdatedEvent,
    TranscriptCreatedEvent,
    WakeDetectedEvent,
)

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "arni"


def _channel(meeting_id: str, event_type: str) -> str:
    return f"{_CHANNEL_PREFIX}:{meeting_id}:{event_type}"


async def _publish(redis: Any, event: Any) -> None:
    channel = _channel(event.meeting_id, event.event)
    payload = event.model_dump_json()
    await redis.publish(channel, payload)
    logger.debug("Published %s to %s", event.event, channel)


# ---------------------------------------------------------------------------
# Public typed publish helpers
# ---------------------------------------------------------------------------

async def publish_transcript_created(
    redis: Any,
    *,
    meeting_id: str,
    speaker_id: str,
    text: str,
    timestamp: float,
    is_final: bool,
) -> None:
    event = TranscriptCreatedEvent(
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        text=text,
        timestamp=timestamp,
        is_final=is_final,
    )
    await _publish(redis, event)


async def publish_wake_detected(
    redis: Any,
    *,
    meeting_id: str,
    speaker_id: str,
    command: str,
    timestamp: float,
) -> None:
    event = WakeDetectedEvent(
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        command=command,
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_ai_requested(
    redis: Any,
    *,
    meeting_id: str,
    request_id: str,
    command: str,
    timestamp: float,
) -> None:
    event = AIRequestedEvent(
        meeting_id=meeting_id,
        request_id=request_id,
        command=command,
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_ai_responded(
    redis: Any,
    *,
    meeting_id: str,
    request_id: str,
    response_text: str,
    source_type: str,
    timestamp: float,
) -> None:
    event = AIRespondedEvent(
        meeting_id=meeting_id,
        request_id=request_id,
        response_text=response_text,
        source_type=source_type,  # type: ignore[arg-type]
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_ai_state_changed(
    redis: Any,
    *,
    meeting_id: str,
    state: str,
    timestamp: float,
) -> None:
    event = AIStateChangedEvent(
        meeting_id=meeting_id,
        state=state,  # type: ignore[arg-type]
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_fact_checked(
    redis: Any,
    *,
    meeting_id: str,
    speaker_id: str,
    original_claim: str,
    correction_text: str,
    source_document: str,
    source_excerpt: str,
    confidence_score: float,
    timestamp: float,
) -> None:
    event = FactCheckedEvent(
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        original_claim=original_claim,
        correction_text=correction_text,
        source_document=source_document,
        source_excerpt=source_excerpt,
        confidence_score=confidence_score,
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_meeting_started(
    redis: Any,
    *,
    meeting_id: str,
    host_id: str,
    timestamp: float,
) -> None:
    await _publish(redis, MeetingStartedEvent(meeting_id=meeting_id, host_id=host_id, timestamp=timestamp))


async def publish_meeting_ended(
    redis: Any,
    *,
    meeting_id: str,
    host_id: str,
    timestamp: float,
) -> None:
    await _publish(redis, MeetingEndedEvent(meeting_id=meeting_id, host_id=host_id, timestamp=timestamp))


async def publish_meeting_processed(
    redis: Any,
    *,
    meeting_id: str,
    timestamp: float,
) -> None:
    await _publish(redis, MeetingProcessedEvent(meeting_id=meeting_id, timestamp=timestamp))


async def publish_meeting_auto_ended(
    redis: Any,
    *,
    meeting_id: str,
    reason: str,
    timestamp: float,
) -> None:
    event = MeetingAutoEndedEvent(
        meeting_id=meeting_id,
        reason=reason,  # type: ignore[arg-type]
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_summary_updated(
    redis: Any,
    *,
    meeting_id: str,
    summary_text: str,
    timestamp: float,
) -> None:
    await _publish(redis, SummaryUpdatedEvent(meeting_id=meeting_id, summary_text=summary_text, timestamp=timestamp))


async def publish_document_uploaded(
    redis: Any,
    *,
    meeting_id: str,
    document_id: str,
    filename: str,
    status: str,
    timestamp: float,
) -> None:
    event = DocumentUploadedEvent(
        meeting_id=meeting_id,
        document_id=document_id,
        filename=filename,
        status=status,  # type: ignore[arg-type]
        timestamp=timestamp,
    )
    await _publish(redis, event)


async def publish_participant_invited(
    redis: Any,
    *,
    meeting_id: str,
    email: str,
    invited_by: str,
    timestamp: float,
) -> None:
    await _publish(redis, ParticipantInvitedEvent(meeting_id=meeting_id, email=email, invited_by=invited_by, timestamp=timestamp))


async def publish_participant_admitted(
    redis: Any,
    *,
    meeting_id: str,
    user_id: str,
    admitted_by: str,
    timestamp: float,
) -> None:
    await _publish(redis, ParticipantAdmittedEvent(meeting_id=meeting_id, user_id=user_id, admitted_by=admitted_by, timestamp=timestamp))


async def publish_participant_removed(
    redis: Any,
    *,
    meeting_id: str,
    user_id: str,
    removed_by: str,
    timestamp: float,
) -> None:
    await _publish(redis, ParticipantRemovedEvent(meeting_id=meeting_id, user_id=user_id, removed_by=removed_by, timestamp=timestamp))


async def publish_participant_rejected(
    redis: Any,
    *,
    meeting_id: str,
    user_id: str,
    timestamp: float,
) -> None:
    await _publish(redis, ParticipantRejectedEvent(meeting_id=meeting_id, user_id=user_id, timestamp=timestamp))


async def publish_host_transferred(
    redis: Any,
    *,
    meeting_id: str,
    old_host_id: str,
    new_host_id: str,
    timestamp: float,
) -> None:
    await _publish(redis, HostTransferredEvent(meeting_id=meeting_id, old_host_id=old_host_id, new_host_id=new_host_id, timestamp=timestamp))
