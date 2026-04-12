"""
MongoDB models for Document and DocumentChunk.

SRS references: §8.4 Document model, §8.5 Document Chunk model.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class DocumentCreate(BaseModel):
    """Schema for inserting a new Document record."""
    meeting_id: str
    uploaded_by: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus = DocumentStatus.PROCESSING
    chunk_count: int = 0
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentResponse(BaseModel):
    """Schema returned to clients after upload."""
    id: str
    meeting_id: str
    uploaded_by: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    chunk_count: int
    uploaded_at: datetime


class DocumentChunkCreate(BaseModel):
    """Schema for inserting a single vector chunk."""
    meeting_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    embedding: list[float]
    source: str = "document"
    has_table: bool = False


class DocumentChunkResponse(BaseModel):
    """Lightweight read model for a single chunk."""
    id: str
    meeting_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    source: str
