"""
Transcript WebSocket gateway and persistence.

With ElevenLabs Conversational AI, the bot handles STT/LLM/TTS internally.
This module only handles:
  - WebSocket broadcast for live transcript display
  - MongoDB persistence for final transcripts
  - Historical transcript retrieval API
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
    """Broadcast transcript to WebSocket. Save to DB if final and not from Arni."""
    if transcript.is_final and transcript.speaker_id != ARNI_SPEAKER_ID:
        await save_transcript_to_db(transcript)
    await manager.broadcast(transcript.meeting_id, transcript.model_dump(mode="json"))


async def handle_wake_word(meeting_id: str, result: WakeWordResult):
    """Legacy callback — kept for API compatibility.

    With ElevenLabs Conversational AI, wake detection and response
    are handled internally by the agent. This is a no-op.
    """
    pass


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
