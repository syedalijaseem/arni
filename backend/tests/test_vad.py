"""
TDD tests for Task 4: VAD interrupt handler (vad_handler.py).

Tests cover:
- VADInterruptHandler does NOT trigger interrupt when Arni is NOT in speaking state
- VADInterruptHandler DOES trigger interrupt when Arni IS in speaking state
- Arni's own speaker_id never triggers an interrupt (feedback loop prevention)
"""

import pytest
from unittest.mock import AsyncMock


class TestVADInterruptHandler:

    @pytest.mark.asyncio
    async def test_no_interrupt_when_not_speaking(self):
        """VAD does not trigger interrupt callback when Arni is in listening state."""
        callback = AsyncMock()

        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=callback)
        handler.set_state("listening")

        triggered = await handler.on_transcript("meet-1", "user-1", "Hello there")

        assert triggered is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_interrupt_when_speaking(self):
        """VAD triggers interrupt callback when Arni is in speaking state."""
        callback = AsyncMock()

        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=callback)
        handler.set_state("speaking")

        triggered = await handler.on_transcript("meet-1", "user-1", "Wait, I have a question")

        assert triggered is True
        callback.assert_called_once_with("meet-1", "user-1")

    @pytest.mark.asyncio
    async def test_arni_speaker_never_triggers_interrupt(self):
        """Arni's own speaker_id does not trigger an interrupt even when speaking."""
        callback = AsyncMock()

        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=callback)
        handler.set_state("speaking")

        triggered = await handler.on_transcript("meet-1", "arni", "I am responding...")

        assert triggered is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_interrupt_when_idle(self):
        """VAD does not trigger when Arni is idle."""
        callback = AsyncMock()

        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=callback)
        handler.set_state("idle")

        triggered = await handler.on_transcript("meet-1", "user-1", "Hello")

        assert triggered is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_interrupt_when_processing(self):
        """VAD does not trigger when Arni is processing (only speaking triggers interrupt)."""
        callback = AsyncMock()

        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=callback)
        handler.set_state("processing")

        triggered = await handler.on_transcript("meet-1", "user-1", "Hurry up")

        assert triggered is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_callback_registered_still_returns_true(self):
        """Even with no callback, on_transcript returns True when interrupt occurs."""
        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler(interrupt_callback=None)
        handler.set_state("speaking")

        triggered = await handler.on_transcript("meet-1", "user-1", "Interrupt")

        assert triggered is True

    def test_state_transitions(self):
        """VADInterruptHandler tracks state changes correctly."""
        from app.vad.vad_handler import VADInterruptHandler
        handler = VADInterruptHandler()
        assert handler.current_state == "idle"

        handler.set_state("listening")
        assert handler.current_state == "listening"

        handler.set_state("speaking")
        assert handler.current_state == "speaking"
