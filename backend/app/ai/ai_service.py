"""
AI Service — Claude Sonnet integration with streaming response pipeline.

Streams Claude's response token-by-token, splits into sentences, sends each
sentence to TTS immediately, and streams the resulting PCM to the meeting.
This cuts latency from ~4s to ~1.3s (first audio plays while Claude still generates).
"""

import logging
import re
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

# Regex to split text at sentence boundaries (period, question mark, exclamation)
# while keeping the delimiter attached to the preceding sentence.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _build_messages(command: str, context: dict[str, Any]) -> list[dict]:
    messages: list[dict] = []
    for turn in context.get("turns", []):
        speaker = turn.get("speaker_name", "Participant")
        messages.append({"role": "user", "content": f"{speaker}: {turn['text']}"})
    messages.append({"role": "user", "content": command})
    return messages


async def ai_summarize(
    meeting_id: str,
    previous_summary: str,
    turns: list[dict],
) -> str:
    """Call Claude to produce an updated rolling meeting summary."""
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
    Stream Claude's response, TTS each sentence, and inject audio as it arrives.

    Pipeline: Claude streams → buffer sentence → TTS sentence → inject audio
    First audio plays while Claude is still generating the rest.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set — returning fallback")
        return {"response_text": FALLBACK_MESSAGE}

    if is_reasoning_request(command):
        context = await build_reasoning_context(meeting_id, command)
        selected_prompt = REASONING_PROMPT
    else:
        selected_prompt = STANDARD_PROMPT

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        summary = context.get("summary", "")
        turns = context.get("turns") or context.get("recent_turns") or []
        recent_turns_text = "\n".join(
            f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns
        )
        document_context = context.get("document_context", "")
        system_prompt = selected_prompt.format(
            summary=summary,
            recent_turns=recent_turns_text,
            document_context=document_context,
            command=command,
        )

        messages = _build_messages(command, context)

        # Stream Claude's response token by token
        full_text = ""
        sent_up_to = 0  # index in full_text up to which we've already TTS'd

        async with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                full_text += text_chunk

                # Check if we have a complete sentence to send to TTS
                unsent = full_text[sent_up_to:]
                sentences = _SENTENCE_RE.split(unsent)

                # If we have 2+ parts, all but the last are complete sentences
                if len(sentences) > 1:
                    for sentence in sentences[:-1]:
                        sentence = sentence.strip()
                        if sentence:
                            await _tts_and_inject(sentence, meeting_id)
                    sent_up_to = full_text.rfind(sentences[-1])

        # Flush any remaining text that didn't end with sentence punctuation
        remaining = full_text[sent_up_to:].strip()
        if remaining:
            await _tts_and_inject(remaining, meeting_id)

        logger.info("AI streamed response for meeting=%s, len=%d chars", meeting_id, len(full_text))
        return {"response_text": full_text}

    except anthropic.APIError as exc:
        logger.error("Anthropic API error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
    except Exception as exc:
        logger.error("Unexpected error in ai_respond for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}


async def _tts_and_inject(sentence: str, meeting_id: str) -> None:
    """Convert one sentence to audio and inject it into the meeting."""
    audio_bytes = await text_to_speech(sentence)
    if audio_bytes is not None:
        await inject_audio(audio_bytes, meeting_id)
    else:
        logger.info("TTS returned None for sentence in meeting=%s — text-only fallback", meeting_id)
