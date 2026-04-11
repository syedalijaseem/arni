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
from app.tts.elevenlabs_client import text_to_speech
from app.tts.audio_injection import inject_audio
from app.ai.reasoning_detector import is_reasoning_request
from app.ai.context_manager import build_context, build_reasoning_context
from app.ai.prompt_templates import STANDARD_PROMPT, REASONING_PROMPT

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = (
    "I'm sorry, I couldn't generate a response right now. "
    "Please try again in a moment."
)

CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 150


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


async def ai_summarize(
    meeting_id: str,
    previous_summary: str,
    turns: list[dict],
) -> str:
    """
    Call Claude to produce an updated rolling meeting summary.

    Args:
        meeting_id: Used for logging only.
        previous_summary: The last stored summary, or empty string.
        turns: Recent transcript turns as [{speaker_name, text}].

    Returns:
        Updated summary text string, or FALLBACK_MESSAGE on error.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — cannot summarize meeting=%s", meeting_id)
        return FALLBACK_MESSAGE

    turns_text = "\n".join(
        f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns
    )
    prompt = (
        "You are summarizing a business meeting in progress.\n"
        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
        f"New transcript turns:\n{turns_text}\n\n"
        "Write a concise updated meeting summary that includes the previous context "
        "and the new information. Keep it under 200 words."
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text: str = message.content[0].text
        logger.info("ai_summarize completed for meeting=%s, tokens=%d", meeting_id, message.usage.output_tokens)
        return summary_text
    except Exception as exc:
        logger.error("ai_summarize error for meeting=%s: %s", meeting_id, exc)
        return FALLBACK_MESSAGE


async def ai_respond(
    meeting_id: str,
    command: str,
    context: dict[str, Any],
) -> dict[str, str]:
    """
    Call Claude Sonnet and return the response text.

    Routes to REASONING_PROMPT when the command contains comparison/recommendation
    language (FR-085). Otherwise uses STANDARD_PROMPT.

    Args:
        meeting_id: Used for logging only.
        command: The user's spoken command / question.
        context: Output of context_manager.build_context() or build_reasoning_context().
                 Pass the pre-built context in; routing logic may override it.

    Returns:
        {"response_text": str} — always returns this shape, never raises.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set — returning fallback")
        return {"response_text": FALLBACK_MESSAGE}

    # Route to reasoning context/prompt when comparison language detected
    if is_reasoning_request(command):
        context = await build_reasoning_context(meeting_id, command)
        selected_prompt = REASONING_PROMPT
    else:
        selected_prompt = STANDARD_PROMPT

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build the full prompt from the selected template
        summary = context.get("summary", "")
        turns = context.get("turns") or context.get("recent_turns") or []
        recent_turns_text = "\n".join(
            f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns
        )
        document_context = context.get("document_context", "")
        full_system = selected_prompt.format(
            summary=summary,
            recent_turns=recent_turns_text,
            document_context=document_context,
            command=command,
        )

        system_prompt = full_system
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

        # Chain TTS → audio injection (NFR-010: failure is non-fatal)
        audio_bytes = await text_to_speech(response_text)
        if audio_bytes is not None:
            await inject_audio(audio_bytes, meeting_id)
        else:
            logger.info(
                "TTS returned None for meeting=%s — text-only fallback active",
                meeting_id,
            )

        return {"response_text": response_text}

    except anthropic.APIError as exc:
        logger.error("Anthropic API error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
    except Exception as exc:
        logger.error("Unexpected error in ai_respond for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
