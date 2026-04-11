"""
AI Service — Claude Sonnet streaming integration.

Streams Claude's response, splits into sentences, TTS each sentence,
plays audio while Claude still generates the rest.
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

FALLBACK_MESSAGE = "Sorry, I couldn't respond right now. Try again in a moment."
CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 80

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _build_messages(command: str, context: dict[str, Any]) -> list[dict]:
    messages: list[dict] = []
    for turn in context.get("turns", []):
        speaker = turn.get("speaker_name", "Participant")
        messages.append({"role": "user", "content": f"{speaker}: {turn['text']}"})
    messages.append({"role": "user", "content": command})
    return messages


async def ai_summarize(meeting_id: str, previous_summary: str, turns: list[dict]) -> str:
    """Produce an updated rolling meeting summary."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return FALLBACK_MESSAGE

    turns_text = "\n".join(f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns)
    prompt = (
        "You are summarizing a business meeting in progress.\n"
        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
        f"New transcript turns:\n{turns_text}\n\n"
        "Write a concise updated meeting summary. Keep it under 200 words."
    )
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=CLAUDE_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as exc:
        logger.error("ai_summarize error: %s", exc)
        return FALLBACK_MESSAGE


async def ai_respond(meeting_id: str, command: str, context: dict[str, Any]) -> dict[str, str]:
    """Stream Claude → sentence-split → TTS → inject audio per sentence."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"response_text": FALLBACK_MESSAGE}

    # Enrich with document context if caller didn't already provide it
    if not context.get("document_context") and command:
        try:
            from app.ai.context_manager import _retrieve_document_context
            doc_ctx = await _retrieve_document_context(meeting_id, command)
            if doc_ctx:
                context = {**context, "document_context": doc_ctx}
        except Exception as exc:
            logger.warning("Document context retrieval failed: %s", exc)

    if is_reasoning_request(command):
        selected_prompt = REASONING_PROMPT
    else:
        selected_prompt = STANDARD_PROMPT

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        summary = context.get("summary", "")
        turns = context.get("turns") or context.get("recent_turns") or []
        recent = "\n".join(f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns)
        doc_ctx = context.get("document_context", "")
        system_prompt = selected_prompt.format(
            summary=summary, recent_turns=recent,
            document_context=doc_ctx, command=command,
        )
        messages = _build_messages(command, context)

        full_text = ""
        sent_up_to = 0

        async with client.messages.stream(
            model=CLAUDE_MODEL, max_tokens=MAX_TOKENS,
            system=system_prompt, messages=messages,
        ) as stream:
            async for chunk in stream.text_stream:
                full_text += chunk
                unsent = full_text[sent_up_to:]
                parts = _SENTENCE_RE.split(unsent)
                if len(parts) > 1:
                    for sentence in parts[:-1]:
                        s = sentence.strip()
                        if s:
                            await _tts_and_inject(s, meeting_id)
                    sent_up_to = full_text.rfind(parts[-1])

        remaining = full_text[sent_up_to:].strip()
        if remaining:
            await _tts_and_inject(remaining, meeting_id)

        logger.info("AI response for meeting=%s: %d chars", meeting_id, len(full_text))
        return {"response_text": full_text}

    except anthropic.APIError as exc:
        logger.error("Anthropic error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}
    except Exception as exc:
        logger.error("ai_respond error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}


async def _tts_and_inject(sentence: str, meeting_id: str) -> None:
    audio = await text_to_speech(sentence)
    if audio:
        await inject_audio(audio, meeting_id)
