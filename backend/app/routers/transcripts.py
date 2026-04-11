import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from bson import ObjectId

from app.database import get_database
from app.models.transcript import TranscriptCreate
from app.bot.wake_word import WakeWordResult

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # meeting_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, meeting_id: str):
        await websocket.accept()
        if meeting_id not in self.active_connections:
            self.active_connections[meeting_id] = []
        self.active_connections[meeting_id].append(websocket)
        logger.info(f"Client connected to meeting {meeting_id} transcripts. Total: {len(self.active_connections[meeting_id])}")

    def disconnect(self, websocket: WebSocket, meeting_id: str):
        if meeting_id in self.active_connections:
            if websocket in self.active_connections[meeting_id]:
                self.active_connections[meeting_id].remove(websocket)
            if not self.active_connections[meeting_id]:
                del self.active_connections[meeting_id]
        logger.info(f"Client disconnected from meeting {meeting_id} transcripts.")

    async def broadcast(self, meeting_id: str, message: dict):
        if meeting_id in self.active_connections:
            for connection in self.active_connections[meeting_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed sending to WS client: {e}")

manager = ConnectionManager()

async def save_transcript_to_db(transcript: TranscriptCreate):
    db = get_database()
    doc = transcript.model_dump()
    await db.transcripts.insert_one(doc)

ARNI_SPEAKER_ID = "arni"


async def handle_bot_transcript(transcript: TranscriptCreate):
    """Callback for ArniBot to push new transcripts to WebSockets and DB.

    Arni's own speech (speaker_id == 'arni') is broadcast to the frontend
    for display but NEVER saved to MongoDB — this prevents Arni from
    transcribing its own responses (FR-035).
    """
    is_arni = transcript.speaker_id == ARNI_SPEAKER_ID

    # Only save to DB if it is final and NOT from Arni
    if transcript.is_final and not is_arni:
        await save_transcript_to_db(transcript)

    # Broadcast to all connected clients (including Arni's text for UI display)
    await manager.broadcast(transcript.meeting_id, transcript.model_dump(mode="json"))


async def handle_wake_word(meeting_id: str, result: WakeWordResult):
    """Callback for ArniBot when a wake word is detected."""
    logger.info(
        f"Wake word triggered in meeting {meeting_id} by {result.speaker_name}: "
        f"{result.command!r}"
    )

    # Broadcast wake_word event to frontend
    await manager.broadcast(meeting_id, {
        "type": "wake_word",
        "speaker_id": result.speaker_id,
        "speaker_name": result.speaker_name,
        "command": result.command,
        "timestamp": result.timestamp,
    })

    # TODO (Day 7): Trigger AI response pipeline here
    # e.g. await ai_pipeline.process(meeting_id, result.command, result.speaker_name)


@router.websocket("/{meeting_id}/ws")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    # In a real app we would verify token from query param or header
    # For now, just accept connection
    await manager.connect(websocket, meeting_id)
    try:
        while True:
            # We don't expect frontend to send transcripts, only receive
            # but we need to keep connection open
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, meeting_id)

@router.get("/{meeting_id}")
async def get_historical_transcripts(meeting_id: str):
    db = get_database()
    cursor = db.transcripts.find({"meeting_id": meeting_id}).sort("timestamp", 1)
    transcripts = await cursor.to_list(length=1000)
    
    # Convert ObjectId to string
    for t in transcripts:
        t["id"] = str(t["_id"])
        del t["_id"]
        
    return transcripts
