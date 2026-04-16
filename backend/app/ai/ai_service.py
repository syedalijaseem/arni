"""
AI Service — DeepSeek streaming integration via centralized LLM client.

Streams LLM response, splits into sentences, TTS each sentence,
plays audio while the model still generates the rest.
"""

import logging
import re
from typing import Any

from app.config import get_settings
from app.tts.elevenlabs_client import text_to_speech
from app.tts.audio_injection import inject_audio
from app.ai.reasoning_detector import is_reasoning_request
from app.ai.context_manager import build_context, build_reasoning_context
from app.ai.prompt_templates import (
    STANDARD_PROMPT,
    REASONING_PROMPT,
)
from app.ai.llm_client import (
    chat,
    chat_stream,
    is_configured,
    FALLBACK_MESSAGE,
    LLM_MODEL,
)

logger = logging.getLogger(__name__)

MAX_TOKENS_DEFAULT = 120
MAX_TOKENS_WITH_DOCS = 120

_DOC_LIST_TRIGGERS = [
    "what documents", "which documents", "list documents",
    "any documents", "files uploaded", "what files",
    "documents uploaded", "uploaded documents",
    "what is uploaded", "any files", "what's uploaded",
]

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
    if not is_configured():
        return FALLBACK_MESSAGE

    turns_text = "\n".join(f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns)
    prompt = (
        "You are summarizing a business meeting in progress.\n"
        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
        f"New transcript turns:\n{turns_text}\n\n"
        "Write a concise updated meeting summary. Keep it under 200 words."
    )
    try:
        result = await chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return result or FALLBACK_MESSAGE
    except Exception as exc:
        logger.error("ai_summarize error: %s", exc)
        return FALLBACK_MESSAGE


async def ai_respond(
    meeting_id: str,
    command: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Stream LLM -> sentence-split -> TTS -> inject audio per sentence.

    Returns dict with:
      - response_text: the full AI response
    """
    if not is_configured():
        return {"response_text": FALLBACK_MESSAGE}

    # Fast-path: answer document listing queries directly from DB
    cmd_lower = command.lower()
    if any(trigger in cmd_lower for trigger in _DOC_LIST_TRIGGERS):
        try:
            from app.database import get_database
            db = get_database()
            docs = await db.documents.find(
                {"meeting_id": meeting_id, "status": "ready"},
            ).to_list(20)
            if not docs:
                response = "No documents have been uploaded to this meeting yet."
            else:
                names = [d.get("filename", "Unknown") for d in docs]
                if len(names) == 1:
                    response = f"There is one document uploaded: {names[0]}."
                else:
                    listed = ", ".join(names[:-1]) + f" and {names[-1]}"
                    response = f"There are {len(names)} documents uploaded: {listed}."
            logger.info("Doc listing query for meeting=%s: %s", meeting_id, response)
            return {"response_text": response}
        except Exception as exc:
            logger.warning("Doc listing query failed: %s", exc)

    # Enrich with document context if caller didn't already provide it
    if not context.get("document_context") and command:
        logger.info("ai_respond: no doc context from caller, retrieving for meeting=%s", meeting_id)
        try:
            from app.ai.context_manager import _retrieve_document_context
            doc_ctx_text, doc_scores = await _retrieve_document_context(meeting_id, command)
            if doc_ctx_text:
                context = {**context, "document_context": doc_ctx_text, "rag_scores": doc_scores}
                logger.info("ai_respond: enriched with %d chars of doc context", len(doc_ctx_text))
            else:
                logger.info("ai_respond: secondary retrieval returned empty")
        except Exception as exc:
            logger.warning("Document context retrieval failed: %s", exc)
    else:
        logger.info("ai_respond: caller provided doc_context=%d chars",
                     len(context.get("document_context", "")))

    if is_reasoning_request(command):
        selected_prompt = REASONING_PROMPT
    else:
        selected_prompt = STANDARD_PROMPT

    try:
        summary = context.get("summary", "")
        turns = context.get("turns") or context.get("recent_turns") or []
        recent = "\n".join(f"{t.get('speaker_name', 'Participant')}: {t['text']}" for t in turns)
        doc_ctx = context.get("document_context", "")

        system_prompt = selected_prompt.format(
            summary=summary,
            recent_turns=recent,
            document_context=doc_ctx,
            command=command,
        )
        messages = _build_messages(command, context)

        logger.info(
            "ai_respond: sending to LLM — doc_ctx=%d chars, turns=%d, system_prompt=%d chars, command=%r",
            len(doc_ctx), len(turns), len(system_prompt), command[:80],
        )

        # Use higher token limit when document context is available
        max_tokens = MAX_TOKENS_WITH_DOCS if doc_ctx else MAX_TOKENS_DEFAULT

        full_text = ""
        sent_up_to = 0

        async for chunk in chat_stream(
            messages=messages, system=system_prompt, max_tokens=max_tokens,
        ):
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

    except Exception as exc:
        logger.error("ai_respond error for meeting=%s: %s", meeting_id, exc)
        return {"response_text": FALLBACK_MESSAGE}


async def _tts_and_inject(sentence: str, meeting_id: str) -> None:
    audio = await text_to_speech(sentence)
    if audio:
        await inject_audio(audio, meeting_id)
