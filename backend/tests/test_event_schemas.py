"""
TDD tests for Task 4: Event Bus schemas and publisher.

Tests cover:
- All 17 Pydantic event schemas: valid payload passes; missing required field raises
  ValidationError; extra undocumented field raises ValidationError (extra="forbid")
- publisher.py: typed publish function validates and serialises to Redis correctly
"""

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Event schema tests
# ---------------------------------------------------------------------------

class TestTranscriptCreatedSchema:
    def test_valid_payload(self):
        from app.events.schemas import TranscriptCreatedEvent
        e = TranscriptCreatedEvent(
            event="transcript.created",
            meeting_id="m1",
            speaker_id="u1",
            text="Hello there",
            timestamp=1700000000.0,
            is_final=True,
        )
        assert e.event == "transcript.created"

    def test_missing_field_raises(self):
        from app.events.schemas import TranscriptCreatedEvent
        with pytest.raises(ValidationError):
            TranscriptCreatedEvent(
                event="transcript.created",
                meeting_id="m1",
                speaker_id="u1",
                # text missing
                timestamp=1700000000.0,
                is_final=True,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import TranscriptCreatedEvent
        with pytest.raises(ValidationError):
            TranscriptCreatedEvent(
                event="transcript.created",
                meeting_id="m1",
                speaker_id="u1",
                text="Hi",
                timestamp=1700000000.0,
                is_final=True,
                unexpected_field="oops",
            )


class TestWakeDetectedSchema:
    def test_valid_payload(self):
        from app.events.schemas import WakeDetectedEvent
        e = WakeDetectedEvent(
            event="wake.detected",
            meeting_id="m1",
            speaker_id="u1",
            command="What is the agenda?",
            timestamp=1700000001.0,
        )
        assert e.event == "wake.detected"

    def test_missing_command_raises(self):
        from app.events.schemas import WakeDetectedEvent
        with pytest.raises(ValidationError):
            WakeDetectedEvent(
                event="wake.detected",
                meeting_id="m1",
                speaker_id="u1",
                timestamp=1700000001.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import WakeDetectedEvent
        with pytest.raises(ValidationError):
            WakeDetectedEvent(
                event="wake.detected",
                meeting_id="m1",
                speaker_id="u1",
                command="cmd",
                timestamp=1700000001.0,
                extra="no",
            )


class TestAiRequestedSchema:
    def test_valid_payload(self):
        from app.events.schemas import AIRequestedEvent
        e = AIRequestedEvent(
            event="ai.requested",
            meeting_id="m1",
            request_id="req-1",
            command="Summarise",
            timestamp=1700000002.0,
        )
        assert e.request_id == "req-1"

    def test_extra_field_raises(self):
        from app.events.schemas import AIRequestedEvent
        with pytest.raises(ValidationError):
            AIRequestedEvent(
                event="ai.requested",
                meeting_id="m1",
                request_id="req-1",
                command="cmd",
                timestamp=1700000002.0,
                extra="no",
            )


class TestAiRespondedSchema:
    def test_valid_payload(self):
        from app.events.schemas import AIRespondedEvent
        e = AIRespondedEvent(
            event="ai.responded",
            meeting_id="m1",
            request_id="req-1",
            response_text="The answer is 42.",
            source_type="transcript",
            timestamp=1700000003.0,
        )
        assert e.source_type == "transcript"

    def test_invalid_source_type_raises(self):
        from app.events.schemas import AIRespondedEvent
        with pytest.raises(ValidationError):
            AIRespondedEvent(
                event="ai.responded",
                meeting_id="m1",
                request_id="req-1",
                response_text="answer",
                source_type="unknown_type",  # invalid literal
                timestamp=1700000003.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import AIRespondedEvent
        with pytest.raises(ValidationError):
            AIRespondedEvent(
                event="ai.responded",
                meeting_id="m1",
                request_id="req-1",
                response_text="answer",
                source_type="document",
                timestamp=1700000003.0,
                extra="no",
            )


class TestAiStateChangedSchema:
    def test_valid_listening(self):
        from app.events.schemas import AIStateChangedEvent
        e = AIStateChangedEvent(
            event="ai.state_changed",
            meeting_id="m1",
            state="listening",
            timestamp=1700000004.0,
        )
        assert e.state == "listening"

    def test_invalid_state_raises(self):
        from app.events.schemas import AIStateChangedEvent
        with pytest.raises(ValidationError):
            AIStateChangedEvent(
                event="ai.state_changed",
                meeting_id="m1",
                state="unknown_state",
                timestamp=1700000004.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import AIStateChangedEvent
        with pytest.raises(ValidationError):
            AIStateChangedEvent(
                event="ai.state_changed",
                meeting_id="m1",
                state="speaking",
                timestamp=1700000004.0,
                extra="no",
            )


class TestFactCheckedSchema:
    def test_valid_payload(self):
        from app.events.schemas import FactCheckedEvent
        e = FactCheckedEvent(
            event="fact.checked",
            meeting_id="m1",
            speaker_id="u1",
            original_claim="The Earth is flat",
            correction_text="The Earth is an oblate spheroid",
            source_document="NASA Report 2023",
            source_excerpt="The Earth is approximately spherical...",
            confidence_score=0.97,
            timestamp=1700000005.0,
        )
        assert e.confidence_score == 0.97

    def test_missing_confidence_raises(self):
        from app.events.schemas import FactCheckedEvent
        with pytest.raises(ValidationError):
            FactCheckedEvent(
                event="fact.checked",
                meeting_id="m1",
                speaker_id="u1",
                original_claim="claim",
                correction_text="correction",
                source_document="doc",
                source_excerpt="excerpt",
                timestamp=1700000005.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import FactCheckedEvent
        with pytest.raises(ValidationError):
            FactCheckedEvent(
                event="fact.checked",
                meeting_id="m1",
                speaker_id="u1",
                original_claim="claim",
                correction_text="correction",
                source_document="doc",
                source_excerpt="excerpt",
                confidence_score=0.9,
                timestamp=1700000005.0,
                extra="no",
            )


class TestMeetingStartedSchema:
    def test_valid_payload(self):
        from app.events.schemas import MeetingStartedEvent
        e = MeetingStartedEvent(
            event="meeting.started",
            meeting_id="m1",
            host_id="h1",
            timestamp=1700000006.0,
        )
        assert e.host_id == "h1"

    def test_extra_field_raises(self):
        from app.events.schemas import MeetingStartedEvent
        with pytest.raises(ValidationError):
            MeetingStartedEvent(
                event="meeting.started",
                meeting_id="m1",
                host_id="h1",
                timestamp=1700000006.0,
                extra="no",
            )


class TestMeetingEndedSchema:
    def test_valid_payload(self):
        from app.events.schemas import MeetingEndedEvent
        e = MeetingEndedEvent(
            event="meeting.ended",
            meeting_id="m1",
            host_id="h1",
            timestamp=1700000007.0,
        )
        assert e.event == "meeting.ended"

    def test_extra_field_raises(self):
        from app.events.schemas import MeetingEndedEvent
        with pytest.raises(ValidationError):
            MeetingEndedEvent(
                event="meeting.ended",
                meeting_id="m1",
                host_id="h1",
                timestamp=1700000007.0,
                extra="no",
            )


class TestMeetingProcessedSchema:
    def test_valid_payload(self):
        from app.events.schemas import MeetingProcessedEvent
        e = MeetingProcessedEvent(
            event="meeting.processed",
            meeting_id="m1",
            timestamp=1700000008.0,
        )
        assert e.event == "meeting.processed"

    def test_extra_field_raises(self):
        from app.events.schemas import MeetingProcessedEvent
        with pytest.raises(ValidationError):
            MeetingProcessedEvent(
                event="meeting.processed",
                meeting_id="m1",
                timestamp=1700000008.0,
                extra="no",
            )


class TestMeetingAutoEndedSchema:
    def test_valid_payload(self):
        from app.events.schemas import MeetingAutoEndedEvent
        e = MeetingAutoEndedEvent(
            event="meeting.auto_ended",
            meeting_id="m1",
            reason="host_timeout",
            timestamp=1700000009.0,
        )
        assert e.reason == "host_timeout"

    def test_invalid_reason_raises(self):
        from app.events.schemas import MeetingAutoEndedEvent
        with pytest.raises(ValidationError):
            MeetingAutoEndedEvent(
                event="meeting.auto_ended",
                meeting_id="m1",
                reason="other_reason",
                timestamp=1700000009.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import MeetingAutoEndedEvent
        with pytest.raises(ValidationError):
            MeetingAutoEndedEvent(
                event="meeting.auto_ended",
                meeting_id="m1",
                reason="host_timeout",
                timestamp=1700000009.0,
                extra="no",
            )


class TestSummaryUpdatedSchema:
    def test_valid_payload(self):
        from app.events.schemas import SummaryUpdatedEvent
        e = SummaryUpdatedEvent(
            event="summary.updated",
            meeting_id="m1",
            summary_text="Discussed Q1 revenue.",
            timestamp=1700000010.0,
        )
        assert e.summary_text == "Discussed Q1 revenue."

    def test_extra_field_raises(self):
        from app.events.schemas import SummaryUpdatedEvent
        with pytest.raises(ValidationError):
            SummaryUpdatedEvent(
                event="summary.updated",
                meeting_id="m1",
                summary_text="text",
                timestamp=1700000010.0,
                extra="no",
            )


class TestDocumentUploadedSchema:
    def test_valid_processing(self):
        from app.events.schemas import DocumentUploadedEvent
        e = DocumentUploadedEvent(
            event="document.uploaded",
            meeting_id="m1",
            document_id="doc-1",
            filename="report.pdf",
            status="processing",
            timestamp=1700000011.0,
        )
        assert e.status == "processing"

    def test_invalid_status_raises(self):
        from app.events.schemas import DocumentUploadedEvent
        with pytest.raises(ValidationError):
            DocumentUploadedEvent(
                event="document.uploaded",
                meeting_id="m1",
                document_id="doc-1",
                filename="report.pdf",
                status="pending",  # not a valid literal
                timestamp=1700000011.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import DocumentUploadedEvent
        with pytest.raises(ValidationError):
            DocumentUploadedEvent(
                event="document.uploaded",
                meeting_id="m1",
                document_id="doc-1",
                filename="report.pdf",
                status="ready",
                timestamp=1700000011.0,
                extra="no",
            )


class TestParticipantInvitedSchema:
    def test_valid_payload(self):
        from app.events.schemas import ParticipantInvitedEvent
        e = ParticipantInvitedEvent(
            event="participant.invited",
            meeting_id="m1",
            email="alice@example.com",
            invited_by="host-1",
            timestamp=1700000012.0,
        )
        assert e.invited_by == "host-1"

    def test_extra_field_raises(self):
        from app.events.schemas import ParticipantInvitedEvent
        with pytest.raises(ValidationError):
            ParticipantInvitedEvent(
                event="participant.invited",
                meeting_id="m1",
                email="alice@example.com",
                invited_by="host-1",
                timestamp=1700000012.0,
                extra="no",
            )


class TestParticipantAdmittedSchema:
    def test_valid_payload_with_admitted_by(self):
        from app.events.schemas import ParticipantAdmittedEvent
        e = ParticipantAdmittedEvent(
            event="participant.admitted",
            meeting_id="m1",
            user_id="u1",
            admitted_by="host-1",
            timestamp=1700000013.0,
        )
        assert e.admitted_by == "host-1"

    def test_missing_admitted_by_raises(self):
        from app.events.schemas import ParticipantAdmittedEvent
        with pytest.raises(ValidationError):
            ParticipantAdmittedEvent(
                event="participant.admitted",
                meeting_id="m1",
                user_id="u1",
                # admitted_by missing
                timestamp=1700000013.0,
            )

    def test_extra_field_raises(self):
        from app.events.schemas import ParticipantAdmittedEvent
        with pytest.raises(ValidationError):
            ParticipantAdmittedEvent(
                event="participant.admitted",
                meeting_id="m1",
                user_id="u1",
                admitted_by="host-1",
                timestamp=1700000013.0,
                extra="no",
            )


class TestParticipantRemovedSchema:
    def test_valid_payload(self):
        from app.events.schemas import ParticipantRemovedEvent
        e = ParticipantRemovedEvent(
            event="participant.removed",
            meeting_id="m1",
            user_id="u1",
            removed_by="host-1",
            timestamp=1700000014.0,
        )
        assert e.removed_by == "host-1"

    def test_extra_field_raises(self):
        from app.events.schemas import ParticipantRemovedEvent
        with pytest.raises(ValidationError):
            ParticipantRemovedEvent(
                event="participant.removed",
                meeting_id="m1",
                user_id="u1",
                removed_by="host-1",
                timestamp=1700000014.0,
                extra="no",
            )


class TestParticipantRejectedSchema:
    def test_valid_payload(self):
        from app.events.schemas import ParticipantRejectedEvent
        e = ParticipantRejectedEvent(
            event="participant.rejected",
            meeting_id="m1",
            user_id="u1",
            timestamp=1700000015.0,
        )
        assert e.user_id == "u1"

    def test_extra_field_raises(self):
        from app.events.schemas import ParticipantRejectedEvent
        with pytest.raises(ValidationError):
            ParticipantRejectedEvent(
                event="participant.rejected",
                meeting_id="m1",
                user_id="u1",
                timestamp=1700000015.0,
                extra="no",
            )


class TestHostTransferredSchema:
    def test_valid_payload(self):
        from app.events.schemas import HostTransferredEvent
        e = HostTransferredEvent(
            event="host.transferred",
            meeting_id="m1",
            old_host_id="h1",
            new_host_id="h2",
            timestamp=1700000016.0,
        )
        assert e.new_host_id == "h2"

    def test_extra_field_raises(self):
        from app.events.schemas import HostTransferredEvent
        with pytest.raises(ValidationError):
            HostTransferredEvent(
                event="host.transferred",
                meeting_id="m1",
                old_host_id="h1",
                new_host_id="h2",
                timestamp=1700000016.0,
                extra="no",
            )


# ---------------------------------------------------------------------------
# Publisher tests
# ---------------------------------------------------------------------------

class TestPublisher:
    @pytest.mark.asyncio
    async def test_publish_transcript_created_calls_redis(self):
        """publish_transcript_created validates and publishes to Redis."""
        import time

        mock_redis = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()
        mock_redis.publish = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()

        from app.events.publisher import publish_transcript_created
        await publish_transcript_created(
            redis=mock_redis,
            meeting_id="m1",
            speaker_id="u1",
            text="Hello",
            timestamp=time.time(),
            is_final=True,
        )

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        assert channel == "arni:m1:transcript.created"

    @pytest.mark.asyncio
    async def test_publish_wake_detected_calls_redis(self):
        """publish_wake_detected validates and publishes to Redis."""
        import time

        mock_redis = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()
        mock_redis.publish = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()

        from app.events.publisher import publish_wake_detected
        await publish_wake_detected(
            redis=mock_redis,
            meeting_id="m1",
            speaker_id="u1",
            command="What is the Q1 revenue?",
            timestamp=time.time(),
        )

        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == "arni:m1:wake.detected"

    @pytest.mark.asyncio
    async def test_publish_ai_state_changed_calls_redis(self):
        """publish_ai_state_changed validates and publishes to Redis."""
        import time

        mock_redis = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()
        mock_redis.publish = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock()

        from app.events.publisher import publish_ai_state_changed
        await publish_ai_state_changed(
            redis=mock_redis,
            meeting_id="m1",
            state="processing",
            timestamp=time.time(),
        )

        mock_redis.publish.assert_called_once()
        channel = mock_redis.publish.call_args[0][0]
        assert channel == "arni:m1:ai.state_changed"
