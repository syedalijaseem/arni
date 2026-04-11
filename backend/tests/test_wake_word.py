"""
Unit tests for WakeWordDetector.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from app.bot.wake_word import WakeWordDetector, WakeWordResult


@pytest.fixture
def detector():
    """Create a WakeWordDetector with default settings."""
    with patch("app.bot.wake_word.get_settings") as mock_settings:
        settings = MagicMock()
        settings.WAKE_PHRASES = (
            "hey arni,hey arnie,hey ardy,hey ardie,hey r.d.,hey rd,hey r d,"
            "hey ani,hey ernie,hey arnee,hey are knee,"
            "arni,arnie,ardy,ardie,r.d.,rd,r d,ani,ernie,arnee,are knee,"
            "harney,marni"
        )
        settings.WAKE_COOLDOWN_SECONDS = 5
        mock_settings.return_value = settings
        return WakeWordDetector()


class TestWakeWordDetection:
    """Tests for basic wake word matching."""

    def test_exact_match(self, detector):
        result = detector.detect("hey arni what time is it", "user1", "Alice")
        assert result is not None
        assert result.command == "what time is it"
        assert result.speaker_id == "user1"
        assert result.speaker_name == "Alice"

    def test_case_insensitive(self, detector):
        result = detector.detect("Hey Arni summarize the meeting", "user1", "Alice")
        assert result is not None
        assert result.command == "summarize the meeting"

    def test_variant_arnie(self, detector):
        result = detector.detect("hey arnie what did we decide", "user1", "Alice")
        assert result is not None
        assert result.command == "what did we decide"

    def test_variant_ernie(self, detector):
        result = detector.detect("hey ernie list action items", "user1", "Alice")
        assert result is not None
        assert result.command == "list action items"

    def test_variant_bare_arni(self, detector):
        result = detector.detect("arni tell me the summary", "user1", "Alice")
        assert result is not None
        assert result.command == "tell me the summary"

    def test_variant_are_knee(self, detector):
        result = detector.detect("hey are knee what's the agenda", "user1", "Alice")
        assert result is not None
        assert result.command == "what's the agenda"

    def test_variant_arnee(self, detector):
        result = detector.detect("hey arnee help me with this", "user1", "Alice")
        assert result is not None
        assert result.command == "help me with this"

    def test_variant_ardy(self, detector):
        result = detector.detect("hey ardy what time is it", "user1", "Alice")
        assert result is not None
        assert result.command == "what time is it"

    def test_variant_rd(self, detector):
        result = detector.detect("hey rd summarize the meeting", "user1", "Alice")
        assert result is not None
        assert result.command == "summarize the meeting"

    def test_variant_ani(self, detector):
        result = detector.detect("ani what do you think", "user1", "Alice")
        assert result is not None
        assert result.command == "what do you think"

    def test_variant_harney(self, detector):
        result = detector.detect("harney tell me the status", "user1", "Alice")
        assert result is not None
        assert result.command == "tell me the status"

    def test_variant_ardie_at_end(self, detector):
        result = detector.detect("what is our revenue, ardie?", "user1", "Alice")
        assert result is not None
        assert result.command == "what is our revenue"

    def test_wake_phrase_mid_sentence(self, detector):
        """Wake phrase can appear anywhere — full utterance (minus wake phrase) is the command."""
        result = detector.detect("so I was thinking hey arni what do you think", "user1", "Alice")
        assert result is not None
        assert result.command == "so I was thinking what do you think"

    def test_wake_phrase_at_end(self, detector):
        """Wake phrase at end of utterance — context before it becomes the command."""
        result = detector.detect("Can you tell me about our Q4 revenue, Arnie?", "user1", "Alice")
        assert result is not None
        assert result.command == "Can you tell me about our Q4 revenue"

    def test_wake_phrase_at_start(self, detector):
        """Wake phrase at start — text after it is the command."""
        result = detector.detect("Arnie, what is our revenue?", "user1", "Alice")
        assert result is not None
        assert result.command == "what is our revenue"

    def test_no_wake_phrase(self, detector):
        result = detector.detect("just a normal sentence about the project", "user1", "Alice")
        assert result is None

    def test_similar_but_not_matching(self, detector):
        result = detector.detect("hey arnold how are you", "user1", "Alice")
        assert result is None


class TestEmptyCommandHandling:
    """Tests for the edge case: wake phrase with no command."""

    def test_empty_command_returns_none(self, detector):
        result = detector.detect("hey arni", "user1", "Alice")
        assert result is None

    def test_whitespace_only_command_returns_none(self, detector):
        result = detector.detect("hey arni   ", "user1", "Alice")
        assert result is None


class TestCooldown:
    """Tests for cooldown enforcement."""

    def test_cooldown_blocks_rapid_triggers(self, detector):
        # First trigger should succeed
        result1 = detector.detect("hey arni first command", "user1", "Alice")
        assert result1 is not None

        # Immediate second trigger should be blocked
        result2 = detector.detect("hey arni second command", "user1", "Alice")
        assert result2 is None

    def test_cooldown_expires(self, detector):
        # First trigger
        result1 = detector.detect("hey arni first command", "user1", "Alice")
        assert result1 is not None

        # Fast-forward past cooldown
        detector.last_trigger_time = time.time() - 6  # 6 seconds ago

        # Should work now
        result2 = detector.detect("hey arni second command", "user1", "Alice")
        assert result2 is not None
        assert result2.command == "second command"

    def test_cooldown_different_speakers_still_blocked(self, detector):
        """Cooldown is per-meeting, not per-speaker."""
        result1 = detector.detect("hey arni first question", "user1", "Alice")
        assert result1 is not None

        result2 = detector.detect("hey arni second question", "user2", "Bob")
        assert result2 is None


class TestWakeWordResult:
    """Tests for result data structure."""

    def test_result_has_timestamp(self, detector):
        result = detector.detect("hey arni do something", "user1", "Alice")
        assert result is not None
        assert isinstance(result.timestamp, float)
        assert result.timestamp > 0

    def test_result_fields(self, detector):
        result = detector.detect("hey arni tell me a joke", "user42", "Charlie")
        assert result is not None
        assert result.speaker_id == "user42"
        assert result.speaker_name == "Charlie"
        assert result.command == "tell me a joke"
