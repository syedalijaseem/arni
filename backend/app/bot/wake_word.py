"""
Wake Word Detector for Arni Bot.

Scans finalized Deepgram transcripts for configurable wake phrases
(e.g. "Hey Arni") and extracts the command that follows.

Design decisions:
- Only operates on is_final=True transcripts (interim is too noisy).
- Per-meeting cooldown to prevent duplicate triggers.
- Empty commands (just "Hey Arni" with nothing after) are ignored.
"""

import re
import time
import logging
from dataclasses import dataclass
from typing import Optional, List

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class WakeWordResult:
    speaker_id: str
    speaker_name: str
    command: str
    timestamp: float


class WakeWordDetector:
    def __init__(self):
        settings = get_settings()
        raw_phrases = [p.strip().lower() for p in settings.WAKE_PHRASES.split(",") if p.strip()]
        self.cooldown_seconds = settings.WAKE_COOLDOWN_SECONDS

        # Sort phrases longest-first so "hey arni" matches before bare "arni"
        raw_phrases.sort(key=len, reverse=True)

        # Build a regex that detects the wake phrase anywhere in the utterance.
        # We don't use a capturing group for the "command" part because the
        # command is the full utterance with the wake phrase stripped out.
        escaped = [re.escape(p) for p in raw_phrases]
        self._wake_re = re.compile(
            r"\b(?:" + "|".join(escaped) + r")\b",
            re.IGNORECASE,
        )
        # Secondary pattern to strip the wake phrase plus surrounding punctuation/whitespace
        self._strip_re = re.compile(
            r",?\s*\b(?:" + "|".join(escaped) + r")\b[,.\s!?]*",
            re.IGNORECASE,
        )

        self.last_trigger_time: float = 0.0

        logger.info(
            f"WakeWordDetector initialized — phrases={raw_phrases}, "
            f"cooldown={self.cooldown_seconds}s"
        )

    def detect(
        self,
        text: str,
        speaker_id: str,
        speaker_name: str,
    ) -> Optional[WakeWordResult]:
        """
        Check if `text` contains a wake phrase followed by a command.

        Returns a WakeWordResult if triggered, or None if:
        - No wake phrase found
        - Command is empty (just "Hey Arni" with no follow-up)
        - Cooldown period hasn't elapsed
        """
        if not self._wake_re.search(text):
            return None

        # Strip the wake phrase (and surrounding punctuation) from the full utterance
        command = self._strip_re.sub(" ", text).strip().strip(",.?!;:")

        # Ignore empty commands — user said "Hey Arni" but nothing after
        if not command:
            logger.debug(f"Wake phrase detected but no command from {speaker_name}, ignoring")
            return None

        # Enforce cooldown
        now = time.time()
        elapsed = now - self.last_trigger_time
        if elapsed < self.cooldown_seconds:
            logger.info(
                f"Wake word cooldown active ({elapsed:.1f}s < {self.cooldown_seconds}s), "
                f"ignoring trigger from {speaker_name}"
            )
            return None

        self.last_trigger_time = now

        result = WakeWordResult(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            command=command,
            timestamp=now,
        )
        logger.info(f"🔊 Wake word detected! speaker={speaker_name}, command={command!r}")
        return result
