"""
Transcript WebSocket gateway, persistence, and AI pipeline trigger.

Passive Mode: all transcripts broadcast + saved.
Active Mode: wake word callback triggers Claude → TTS pipeline.
"""

import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import get_database
from app.models.transcript import TranscriptCreate
from app.bot.wake_word import WakeWordResult

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, meeting_id: str):
        await websocket.accept()
        if meeting_id not in self.active_connections:
            self.active_connections[meeting_id] = []
        self.active_connections[meeting_id].append(websocket)

    def disconnect(self, websocket: WebSocket, meeting_id: str):
        if meeting_id in self.active_connections:
            if websocket in self.active_connections[meeting_id]:
                self.active_connections[meeting_id].remove(websocket)
            if not self.active_connections[meeting_id]:
                del self.active_connections[meeting_id]

    async def broadcast(self, meeting_id: str, message: dict):
        for conn in self.active_connections.get(meeting_id, []):
            try:
                await conn.send_json(message)
            except Exception as e:
                logger.error("WS send failed: %s", e)


manager = ConnectionManager()

ARNI_SPEAKER_ID = "arni"


async def save_transcript_to_db(transcript: TranscriptCreate):
    db = get_database()
    await db.transcripts.insert_one(transcript.model_dump())


async def handle_bot_transcript(transcript: TranscriptCreate):
    """PASSIVE MODE: broadcast all transcripts + save final non-Arni ones."""
    if transcript.is_final and transcript.speaker_id != ARNI_SPEAKER_ID:
        await save_transcript_to_db(transcript)
    await manager.broadcast(transcript.meeting_id, transcript.model_dump(mode="json"))


async def handle_wake_word(meeting_id: str, result: WakeWordResult):
    """ACTIVE MODE: wake word detected → Claude → TTS → audio."""
    logger.info(
        "WAKE WORD DETECTED: meeting=%s speaker=%s command=%r",
        meeting_id, result.speaker_name, result.command,
    )

    # Check bot presence before starting the pipeline
    from app.bot.bot_manager import bot_manager
    bot = bot_manager.active_bots.get(meeting_id)
    logger.info(
        "Bot status check: meeting=%s bot_present=%s active_bots_keys=%s",
        meeting_id, bot is not None, list(bot_manager.active_bots.keys()),
    )

    await manager.broadcast(meeting_id, {
        "type": "wake_word",
        "speaker_id": result.speaker_id,
        "speaker_name": result.speaker_name,
        "command": result.command,
        "timestamp": result.timestamp,
    })

    try:
        from app.ai.ai_service import ai_respond
        from app.ai.context_manager import build_context

        logger.info("Building context for meeting=%s", meeting_id)
        context = await build_context(meeting_id, command=result.command)
        logger.info(
            "Context built: meeting=%s summary=%d chars, turns=%d, doc_ctx=%d chars",
            meeting_id,
            len(context.get("summary", "")),
            len(context.get("turns", [])),
            len(context.get("document_context", "")),
        )

        logger.info("Calling ai_respond for meeting=%s command=%r", meeting_id, result.command[:50])
        response = await ai_respond(meeting_id, result.command, context)
        response_text = response.get("response_text", "")
        logger.info(
            "ai_respond returned: meeting=%s text=%d chars, first50=%r",
            meeting_id, len(response_text), response_text[:50],
        )

        await manager.broadcast(meeting_id, {
            "type": "ai_response",
            "text": response_text,
            "triggered_by": result.speaker_name,
            "command": result.command,
        })
        logger.info("ai_response broadcast done for meeting=%s", meeting_id)
    except Exception as exc:
        logger.error("AI pipeline FAILED for %s: %s", meeting_id, exc, exc_info=True)


@router.websocket("/{meeting_id}/ws")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    await manager.connect(websocket, meeting_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, meeting_id)


@router.get("/{meeting_id}")
async def get_historical_transcripts(meeting_id: str):
    db = get_database()
    cursor = db.transcripts.find({"meeting_id": meeting_id}).sort("timestamp", 1)
    transcripts = await cursor.to_list(length=1000)
    for t in transcripts:
        t["id"] = str(t["_id"])
        del t["_id"]
    return transcripts
