"""
Centralized LLM Client — single source of truth for all AI model calls.

To switch providers, only update this file:
  - LLM_BASE_URL
  - LLM_MODEL / LLM_FAST_MODEL
  - The API key field in config.py / .env

Currently configured for: DeepSeek (OpenAI-compatible API).
"""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider configuration — change these to switch LLM providers
# ---------------------------------------------------------------------------
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"           # Main model (DeepSeek-V3)
LLM_FAST_MODEL = "deepseek-chat"      # Fast/cheap model for reranking etc.

FALLBACK_MESSAGE = "Sorry, I couldn't respond right now. Try again in a moment."


def _get_api_key() -> str:
    """Return the configured LLM API key."""
    return get_settings().DEEPSEEK_API_KEY


def get_client() -> AsyncOpenAI:
    """Return an async OpenAI-compatible client pointed at the configured provider."""
    return AsyncOpenAI(
        api_key=_get_api_key(),
        base_url=LLM_BASE_URL,
    )


def is_configured() -> bool:
    """Check whether the LLM API key is set."""
    return bool(_get_api_key())


async def chat(
    *,
    messages: list[dict[str, str]],
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    timeout: float | None = None,
) -> str | None:
    """
    Make a single LLM chat completion call.

    Args:
        messages:   List of {"role": ..., "content": ...} dicts.
        system:     Optional system prompt (prepended as a system message).
        model:      Override the default model.
        max_tokens: Max tokens to generate.
        timeout:    Optional timeout in seconds.

    Returns:
        The assistant's response text, or None on error.
    """
    if not is_configured():
        logger.error("LLM API key not set — cannot make AI call")
        return None

    model = model or LLM_MODEL
    client = get_client()

    full_messages: list[dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    try:
        coro = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        if timeout:
            response = await asyncio.wait_for(coro, timeout=timeout)
        else:
            response = await coro

        return response.choices[0].message.content

    except asyncio.TimeoutError:
        logger.error("LLM call timed out (%.0fs)", timeout)
        return None
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return None


async def chat_stream(
    *,
    messages: list[dict[str, str]],
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
):
    """
    Stream an LLM chat completion. Yields text chunks as they arrive.

    Usage:
        async for chunk in chat_stream(messages=[...], system="..."):
            print(chunk, end="")
    """
    if not is_configured():
        logger.error("LLM API key not set — cannot stream AI call")
        return

    model = model or LLM_MODEL
    client = get_client()

    full_messages: list[dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    try:
        stream = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except Exception as exc:
        logger.error("LLM streaming failed: %s", exc)
