"""
Wake word detector — detects wake phrases anywhere in an utterance,
strips them out, and returns the remaining text as the command.
"""

import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

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

        # Sort longest-first so "hey arni" matches before bare "arni"
        raw_phrases.sort(key=len, reverse=True)

        escaped = [re.escape(p) for p in raw_phrases]
        self._wake_re = re.compile(
            r"\b(?:" + "|".join(escaped) + r")\b",
            re.IGNORECASE,
        )
        self._strip_re = re.compile(
            r",?\s*\b(?:" + "|".join(escaped) + r")\b[,.\s!?]*",
            re.IGNORECASE,
        )

        self.last_trigger_time: float = 0.0
        logger.info("WakeWordDetector ready — %d phrases, cooldown=%ds", len(raw_phrases), self.cooldown_seconds)

    def detect(self, text: str, speaker_id: str, speaker_name: str) -> Optional[WakeWordResult]:
        """Returns WakeWordResult if text contains a wake phrase with a command, else None."""
        if not self._wake_re.search(text):
            return None

        command = self._strip_re.sub(" ", text).strip().strip(",.?!;:")
        if not command:
            return None

        now = time.time()
        if (now - self.last_trigger_time) < self.cooldown_seconds:
            return None

        self.last_trigger_time = now
        return WakeWordResult(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            command=command,
            timestamp=now,
        )
