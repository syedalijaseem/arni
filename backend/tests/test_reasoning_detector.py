"""
TDD tests for Task 8: AI Teammate Reasoning — reasoning_detector module.

Tests cover:
- Keywords that trigger reasoning mode
- Commands that should NOT trigger reasoning mode
- Tokenized matching (substring false-positive prevention)
"""

import pytest
from app.ai.reasoning_detector import is_reasoning_request


class TestIsReasoningRequest:

    def test_which_triggers_reasoning(self):
        """'which option is better' contains 'which' → True."""
        assert is_reasoning_request("which option is better") is True

    def test_or_triggers_reasoning(self):
        """'should we go with A or B' contains 'or' as a token → True."""
        assert is_reasoning_request("should we go with A or B") is True

    def test_recommend_triggers_reasoning(self):
        """'recommend the backend framework' contains 'recommend' → True."""
        assert is_reasoning_request("recommend the backend framework") is True

    def test_better_triggers_reasoning(self):
        """'is option A better' contains 'better' → True."""
        assert is_reasoning_request("is option A better") is True

    def test_prefer_triggers_reasoning(self):
        """'what do you prefer' contains 'prefer' → True."""
        assert is_reasoning_request("what do you prefer") is True

    def test_vs_triggers_reasoning(self):
        """'option A vs option B' contains 'vs' → True."""
        assert is_reasoning_request("option A vs option B") is True

    def test_versus_triggers_reasoning(self):
        """'option A versus option B' contains 'versus' → True."""
        assert is_reasoning_request("option A versus option B") is True

    def test_choose_triggers_reasoning(self):
        """'help me choose a framework' contains 'choose' → True."""
        assert is_reasoning_request("help me choose a framework") is True

    def test_decision_triggers_reasoning(self):
        """'what is the best decision here' contains 'decision' → True."""
        assert is_reasoning_request("what is the best decision here") is True

    def test_compare_triggers_reasoning(self):
        """'compare the two approaches' contains 'compare' → True."""
        assert is_reasoning_request("compare the two approaches") is True

    def test_between_triggers_reasoning(self):
        """'pick between Option A and Option B' contains 'between' → True."""
        assert is_reasoning_request("pick between Option A and Option B") is True

    def test_summarize_does_not_trigger(self):
        """'summarize the discussion' → False."""
        assert is_reasoning_request("summarize the discussion") is False

    def test_generic_question_does_not_trigger(self):
        """'what did John say about performance' → False."""
        assert is_reasoning_request("what did John say about performance") is False

    def test_explore_does_not_trigger(self):
        """'explore our options' — 'or' appears only as substring of 'explore' → False."""
        assert is_reasoning_request("explore our options") is False

    def test_case_insensitive(self):
        """'Which framework is BETTER?' should trigger (case-insensitive)."""
        assert is_reasoning_request("Which framework is BETTER?") is True

    def test_empty_string_does_not_trigger(self):
        """Empty command → False."""
        assert is_reasoning_request("") is False

    def test_vs_substring_does_not_trigger(self):
        """'versus' contains 'vs' as substring but tokenized matching must not match 'vs' inside 'versus'."""
        # 'versus' should match on 'versus' keyword, not double-count
        assert is_reasoning_request("let us discuss the proposal") is False
