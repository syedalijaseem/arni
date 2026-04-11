"""
Tests for response_queue module.

RED phase: tests written first, will fail until implementation exists.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestResponseQueue:
    @pytest.mark.asyncio
    async def test_enqueue_returns_request_id(self):
        """enqueue() must return a request_id string."""
        from app.ai.response_queue import MeetingQueue

        queue = MeetingQueue("meet_001")
        request_id = await queue.enqueue("meet_001", "What is the budget?", "user_1")
        assert isinstance(request_id, str)
        assert len(request_id) > 0

    @pytest.mark.asyncio
    async def test_enqueue_within_cooldown_returns_none(self):
        """Second enqueue within 10-second cooldown window must return None (dropped)."""
        from app.ai.response_queue import MeetingQueue
        import time

        queue = MeetingQueue("meet_001")
        # First enqueue should work
        r1 = await queue.enqueue("meet_001", "First question?", "user_1")
        assert r1 is not None

        # Second within cooldown should be dropped
        r2 = await queue.enqueue("meet_001", "Same again?", "user_1")
        assert r2 is None

    @pytest.mark.asyncio
    async def test_enqueue_after_cooldown_is_accepted(self):
        """Enqueue after cooldown window elapses must succeed."""
        from app.ai.response_queue import MeetingQueue

        queue = MeetingQueue("meet_001")
        queue._cooldown_seconds = 0  # Override for test speed
        r1 = await queue.enqueue("meet_001", "First?", "user_1")
        r2 = await queue.enqueue("meet_001", "Second?", "user_1")
        assert r1 is not None
        assert r2 is not None

    @pytest.mark.asyncio
    async def test_rate_limit_at_30_responses(self):
        """31st enqueue must return rate-limit sentinel, not a real request_id."""
        from app.ai.response_queue import MeetingQueue, RATE_LIMIT_SENTINEL

        queue = MeetingQueue("meet_001")
        queue._cooldown_seconds = 0  # Bypass cooldown for this test
        queue._response_count = 30  # Simulate 30 already used

        result = await queue.enqueue("meet_001", "One more?", "user_1")
        assert result == RATE_LIMIT_SENTINEL

    @pytest.mark.asyncio
    async def test_fifo_ordering(self):
        """Requests must be processed in FIFO order."""
        from app.ai.response_queue import MeetingQueue

        processed_order = []

        async def fake_respond(meeting_id, command, context):
            processed_order.append(command)
            return {"response_text": f"Answer to: {command}"}

        queue = MeetingQueue("meet_001")
        queue._cooldown_seconds = 0

        with patch("app.ai.response_queue.ai_respond", fake_respond):
            with patch("app.ai.response_queue.build_context", AsyncMock(return_value={
                "system": "sys", "summary": "", "turns": []
            })):
                await queue.enqueue("meet_001", "Q1", "user_1")
                await queue.enqueue("meet_001", "Q2", "user_1")
                await queue.enqueue("meet_001", "Q3", "user_1")
                await queue.process_all()

        assert processed_order == ["Q1", "Q2", "Q3"]

    @pytest.mark.asyncio
    async def test_response_count_increments(self):
        """_response_count must increment with each successful response."""
        from app.ai.response_queue import MeetingQueue

        async def fake_respond(meeting_id, command, context):
            return {"response_text": "OK"}

        queue = MeetingQueue("meet_001")
        queue._cooldown_seconds = 0
        initial_count = queue._response_count

        with patch("app.ai.response_queue.ai_respond", fake_respond):
            with patch("app.ai.response_queue.build_context", AsyncMock(return_value={
                "system": "sys", "summary": "", "turns": []
            })):
                await queue.enqueue("meet_001", "Q?", "user_1")
                await queue.process_all()

        assert queue._response_count == initial_count + 1


class TestQueueRegistry:
    @pytest.mark.asyncio
    async def test_get_or_create_returns_same_instance(self):
        """get_or_create_queue must return the same MeetingQueue for the same meeting_id."""
        from app.ai.response_queue import get_or_create_queue

        q1 = get_or_create_queue("meet_abc")
        q2 = get_or_create_queue("meet_abc")
        assert q1 is q2

    @pytest.mark.asyncio
    async def test_different_meetings_get_different_queues(self):
        """Different meeting IDs must produce distinct MeetingQueue instances."""
        from app.ai.response_queue import get_or_create_queue

        q1 = get_or_create_queue("meet_x")
        q2 = get_or_create_queue("meet_y")
        assert q1 is not q2
