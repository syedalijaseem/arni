"""
ActionItem MongoDB model.

SRS references: §8.7 Action Item model, FR-041–FR-048.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ActionItemCreate(BaseModel):
    """Schema for creating a new action item."""
    meeting_id: str
    description: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    is_edited: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActionItemResponse(BaseModel):
    """Schema returned to clients for action item data."""
    id: str
    meeting_id: str
    description: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    is_edited: bool
    created_at: datetime


class ActionItemPatch(BaseModel):
    """Partial update schema for editing an action item (FR-046)."""
    description: Optional[str] = None
    assignee: Optional[str] = None
    deadline: Optional[str] = None
