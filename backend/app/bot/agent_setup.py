"""
ElevenLabs Conversational AI agent setup.

Creates or updates the Arni agent configuration. The agent handles
STT, wake detection, LLM reasoning, and TTS internally — replacing
the entire custom pipeline.
"""

import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

ARNI_PROMPT = """\
You are Arni, a voice AI assistant participating in a live meeting.
Keep every response to 1-2 sentences maximum. Be direct.
No filler phrases. No introductions. Answer the question immediately.
Never use bullet points, lists, or markdown. Speak naturally.
If you cannot answer in 2 sentences, give the most important point
and offer to elaborate if asked.
"""


def ensure_agent() -> str:
    """Return the agent_id, creating the agent if needed."""
    settings = get_settings()

    if not settings.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is required")

    if settings.ELEVENLABS_AGENT_ID:
        logger.info("Using existing ElevenLabs agent: %s", settings.ELEVENLABS_AGENT_ID)
        return settings.ELEVENLABS_AGENT_ID

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

    voice_id = settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"

    response = client.conversational_ai.agents.create(
        name="Arni Meeting Assistant",
        conversation_config={
            "tts": {
                "voice_id": voice_id,
                "model_id": "eleven_flash_v2_5",
                "agent_output_audio_format": "pcm_16000",
            },
            "agent": {
                "prompt": {
                    "prompt": ARNI_PROMPT,
                },
                "first_message": "",
            },
        },
    )

    agent_id = response.agent_id
    logger.info("Created ElevenLabs agent: %s", agent_id)
    return agent_id


def update_agent_context(agent_id: str, meeting_title: str = "",
                         participants: list[str] | None = None,
                         summary: str = "") -> None:
    """Update the agent's system prompt with meeting context."""
    settings = get_settings()
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

    context_parts = [ARNI_PROMPT]
    if meeting_title:
        context_parts.append(f"\nCurrent meeting: {meeting_title}")
    if participants:
        context_parts.append(f"Participants: {', '.join(participants)}")
    if summary:
        context_parts.append(f"\nMeeting summary so far:\n{summary}")

    full_prompt = "\n".join(context_parts)

    try:
        client.conversational_ai.agents.update(
            agent_id=agent_id,
            conversation_config={
                "agent": {
                    "prompt": {
                        "prompt": full_prompt,
                    },
                },
            },
        )
        logger.info("Updated agent %s context", agent_id)
    except Exception as exc:
        logger.error("Failed to update agent context: %s", exc)
