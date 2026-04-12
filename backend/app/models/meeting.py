from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class MeetingState(str, Enum):
    """Meeting lifecycle states."""
    CREATED = "created"
    ACTIVE = "active"
    ENDED = "ended"
    PROCESSED = "processed"


class MeetingCreate(BaseModel):
    """Schema for creating a new meeting."""
    title: Optional[str] = Field(None, max_length=200)


class MeetingResponse(BaseModel):
    """Schema for meeting data returned to the client."""
    id: str
    title: Optional[str]
    host_id: str
    participant_ids: List[str] = []
    state: MeetingState
    invite_link: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    created_at: datetime

    # Daily.co room info
    daily_room_name: Optional[str] = None
    daily_room_url: Optional[str] = None

    # Post-meeting fields (populated later)
    summary: Optional[str] = None
    decisions: List[str] = []
    action_item_ids: List[str] = []
    timeline: List[dict] = []

    # Reconvene fields
    parent_meeting_id: Optional[str] = None
    context_summary: Optional[str] = None


class MeetingListResponse(BaseModel):
    """Schema for meeting list item (lighter response for dashboard)."""
    id: str
    title: Optional[str]
    host_id: str = ""
    state: MeetingState
    invite_code: str
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    participant_count: int
    action_item_count: int


class JoinMeetingResponse(BaseModel):
    """Schema for join meeting response with Daily.co token."""
    meeting: MeetingResponse
    daily_token: str
    daily_room_url: str
