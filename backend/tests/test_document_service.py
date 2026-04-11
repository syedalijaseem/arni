"""
Tests for document_service.py and document router validation.

RED phase: written before implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
import io


class TestFileValidation:
    """Tests for upload validation logic (type, size, count)."""

    @pytest.mark.asyncio
    async def test_rejects_unsupported_file_type(self):
        """upload_document raises ValueError for unsupported MIME types."""
        from app.documents.document_service import validate_upload

        with pytest.raises(ValueError, match="unsupported"):
            await validate_upload(
                filename="report.xlsx",
                content_type="application/vnd.ms-excel",
                file_size_bytes=1024,
                existing_doc_count=0,
            )

    @pytest.mark.asyncio
    async def test_rejects_file_over_size_limit(self):
        """upload_document raises ValueError when file exceeds 20 MB."""
        from app.documents.document_service import validate_upload

        twenty_one_mb = 21 * 1024 * 1024
        with pytest.raises(ValueError, match="size"):
            await validate_upload(
                filename="big.pdf",
                content_type="application/pdf",
                file_size_bytes=twenty_one_mb,
                existing_doc_count=0,
            )

    @pytest.mark.asyncio
    async def test_rejects_when_doc_count_at_limit(self):
        """upload_document raises ValueError when meeting already has 10 docs."""
        from app.documents.document_service import validate_upload

        with pytest.raises(ValueError, match="limit"):
            await validate_upload(
                filename="one_more.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                existing_doc_count=10,
            )

    @pytest.mark.asyncio
    async def test_accepts_valid_pdf(self):
        """validate_upload succeeds for a valid PDF within limits."""
        from app.documents.document_service import validate_upload

        # Should not raise
        await validate_upload(
            filename="brief.pdf",
            content_type="application/pdf",
            file_size_bytes=1024 * 1024,
            existing_doc_count=0,
        )

    @pytest.mark.asyncio
    async def test_accepts_valid_txt(self):
        """validate_upload succeeds for a valid TXT file."""
        from app.documents.document_service import validate_upload

        await validate_upload(
            filename="notes.txt",
            content_type="text/plain",
            file_size_bytes=500,
            existing_doc_count=5,
        )

    @pytest.mark.asyncio
    async def test_accepts_valid_docx(self):
        """validate_upload succeeds for a valid DOCX file."""
        from app.documents.document_service import validate_upload

        await validate_upload(
            filename="agenda.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size_bytes=2 * 1024 * 1024,
            existing_doc_count=3,
        )


class TestTextExtractor:
    def test_extract_txt(self):
        """extract() on TXT bytes returns decoded string."""
        from app.documents.text_extractor import extract

        text = "Hello, this is a plain text document."
        result = extract(text.encode("utf-8"), "text/plain")
        assert result == text

    def test_extract_unknown_type_raises(self):
        """extract() raises ValueError for unsupported content type."""
        from app.documents.text_extractor import extract

        with pytest.raises(ValueError, match="unsupported"):
            extract(b"data", "application/octet-stream")

    def test_extract_returns_string(self):
        """extract() always returns a str, not bytes."""
        from app.documents.text_extractor import extract

        result = extract(b"simple text", "text/plain")
        assert isinstance(result, str)


class TestDocumentModel:
    def test_document_status_enum(self):
        """DocumentStatus enum must have processing, ready, and error values."""
        from app.models.document import DocumentStatus

        assert DocumentStatus.PROCESSING == "processing"
        assert DocumentStatus.READY == "ready"
        assert DocumentStatus.ERROR == "error"

    def test_document_chunk_has_source_document(self):
        """DocumentChunk.source must default to 'document'."""
        from app.models.document import DocumentChunkCreate

        chunk = DocumentChunkCreate(
            meeting_id="m1",
            document_id="d1",
            filename="test.txt",
            chunk_index=0,
            text="some text",
            embedding=[0.1, 0.2, 0.3],
        )
        assert chunk.source == "document"
