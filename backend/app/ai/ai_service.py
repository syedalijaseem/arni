"""
AI Service — Claude Sonnet integration.

Calls the Anthropic Claude API with a fully-assembled prompt and returns
the text response. Implements the canned fallback defined in NFR-011.

Design:
- Stateless: receives pre-assembled context dict and command string.
- API key is always read from the environment via settings; never hardcoded.
- All exceptions are caught and mapped to a user-visible fallback message.
"""

import logging
from typing import Any

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "I'm sorry, I couldn't generate a response right now. "
    "Please try again in a moment."
)

CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 512


def _build_messages(command: str, context: dict[str, Any]) -> list[dict]:
    """
    Assemble the messages list for the Anthropic API.

    Includes:
    - An optional system context block with the rolling summary.
    - Each transcript turn as a user/assistant alternation (simplified).
    - The current user command as the final user message.
    """
    messages: list[dict] = []

    # Include recent turns as conversation history
    for turn in context.get("turns", []):
        speaker = turn.get("speaker_name", "Participant")
        messages.append({"role": "user", "content": f"{speaker}: {turn['text']}"})

    # The actual command that triggered this request
    messages.append({"role": "user", "content": command})

    return messages


def _build_system_prompt(context: dict[str, Any]) -> str:
    """Combine Arni persona with rolling summary for the system parameter."""
    base = context.get("system", "")
    summary = context.get("summary", "")
    if summary:
        return f"{base}\n\nMeeting summary so far:\n{summary}"
    return base


async def ai_respond(
    meeting_id: str,
    command: str,
    context: dict[str, Any],
) -> dict[str, str]:
    """
    Call Claude Sonnet and return the response text.

    Args:
        meeting_id: Used for logging only.
        command: The user's spoken command / question.
        context: Output of context_manager.build_context().

    Returns:
        {"response_text": str} — always returns this shape, never raises.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set — returning fallback")
        return {"response_text": FALLBACK_MESSAGE}

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        system_prompt = _build_system_prompt(context)
        messages = _build_messages(command, context)

        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )

        response_text: str = message.content[0].text
        logger.info(
            "AI responded for meeting=%s, tokens=%d",
            meeting_id,
            message.usage.output_tokens,
        )
        return {"response_text": response_text}

    except anthropic.APIError as exc:
        logger.error("Anthropic API error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
    except Exception as exc:
        logger.error("Unexpected error in ai_respond for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
