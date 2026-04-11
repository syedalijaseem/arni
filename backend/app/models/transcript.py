from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class TranscriptCreate(BaseModel):
    meeting_id: str
    speaker_id: str  # The mapped user_id from MongoDB
    speaker_name: Optional[str] = None
    text: str
    is_final: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class TranscriptResponse(TranscriptCreate):
    id: str

class TranscriptPayload(TranscriptCreate):
    # This is for WebSockets
    type: str = "transcript"
