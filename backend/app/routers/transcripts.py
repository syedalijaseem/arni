import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from bson import ObjectId

from app.database import get_database
from app.models.transcript import TranscriptCreate

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

async def handle_bot_transcript(transcript: TranscriptCreate):
    """Callback for ArniBot to push new transcripts to WebSockets and DB."""
    # Only save to DB if it is final
    if transcript.is_final:
        await save_transcript_to_db(transcript)
    
    # Broadcast to all connected clients
    await manager.broadcast(transcript.meeting_id, transcript.model_dump(mode="json"))


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
