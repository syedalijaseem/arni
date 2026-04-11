"""
Reasoning intent detector for AI Teammate Routing (FR-085).

is_reasoning_request() uses tokenized keyword matching to avoid false positives
like 'or' appearing as a substring inside 'explore'.
"""

import re

# Keywords that indicate a comparison/recommendation request
_REASONING_KEYWORDS = frozenset({
    "which",
    "better",
    "prefer",
    "recommend",
    "vs",
    "versus",
    "or",
    "choose",
    "decision",
    "compare",
    "between",
})


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    return re.findall(r"[a-z]+", text.lower())


def is_reasoning_request(command: str) -> bool:
    """
    Return True if `command` contains any reasoning/comparison keyword.

    Uses tokenized matching so that 'or' inside 'explore' is not matched.

    Args:
        command: The wake-word command text from the transcript.

    Returns:
        True if the command should use the reasoning prompt template.
    """
    if not command:
        return False
    tokens = set(_tokenize(command))
    return bool(tokens & _REASONING_KEYWORDS)
