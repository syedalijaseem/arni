"""
VAD (Voice Activity Detection) interrupt handler.

Detects when a human participant speaks while Arni is in the "speaking" state
and signals an interrupt so Arni stops playback immediately (FR-028–FR-030).

Interrupt detection logic:
- Arni's current state is tracked via the ai.state_changed event.
- When state == "speaking" and a non-arni transcript arrives, an interrupt
  is triggered by invoking the registered interrupt_callback.
- The interrupt_callback is responsible for stopping audio playback and
  transitioning Arni back to the "listening" state.
"""

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

InterruptCallback = Callable[[str, str], Awaitable[None]]
"""Async callback(meeting_id, speaker_id) invoked when an interrupt is detected."""

ARNI_SPEAKER_ID = "arni"


class VADInterruptHandler:
    """
    Stateful handler that detects human-speech interrupts during AI playback.

    Thread-safety: single-meeting, single-event-loop usage assumed.
    """

    def __init__(self, interrupt_callback: Optional[InterruptCallback] = None) -> None:
        self._state: str = "idle"
        self._interrupt_callback = interrupt_callback

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Update Arni's current AI state (idle | listening | processing | speaking)."""
        self._state = state
        logger.debug("VADInterruptHandler state → %s", state)

    @property
    def current_state(self) -> str:
        return self._state

    # ------------------------------------------------------------------
    # Interrupt detection
    # ------------------------------------------------------------------

    async def on_transcript(self, meeting_id: str, speaker_id: str, text: str) -> bool:
        """
        Called whenever a transcript chunk arrives.

        Returns True if an interrupt was triggered, False otherwise.
        The caller is responsible for wiring this into the transcript pipeline.
        """
        if speaker_id == ARNI_SPEAKER_ID:
            return False

        if self._state != "speaking":
            return False

        logger.info(
            "VAD interrupt: speaker=%s interrupted Arni in meeting=%s", speaker_id, meeting_id
        )

        if self._interrupt_callback is not None:
            try:
                await self._interrupt_callback(meeting_id, speaker_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("VAD interrupt_callback error: %s", exc)

        return True
