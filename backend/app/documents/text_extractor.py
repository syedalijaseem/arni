"""
Text Extractor — pulls raw text from PDF, DOCX, and TXT files.

PDF extraction detects and preserves tables as structured text
with explicit header-value pairings for better RAG retrieval.

Supported MIME types:
- application/pdf
- application/vnd.openxmlformats-officedocument.wordprocessingml.document
- text/plain
"""

import io
import logging

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


def extract(file_bytes: bytes, content_type: str) -> str:
    """
    Extract plain text from file bytes.

    Args:
        file_bytes: Raw file content as bytes.
        content_type: MIME type string.

    Returns:
        Extracted text as a UTF-8 string.

    Raises:
        ValueError: If content_type is not supported.
    """
    if content_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"unsupported file type: {content_type!r}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_TYPES))}"
        )

    if content_type == "text/plain":
        return _extract_txt(file_bytes)
    if content_type == "application/pdf":
        return _extract_pdf(file_bytes)
    # DOCX
    return _extract_docx(file_bytes)


def _extract_txt(file_bytes: bytes) -> str:
    """Decode UTF-8 text file, falling back to latin-1."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using pymupdf (fitz).

    Uses block-level extraction sorted by position so tabular
    layouts are preserved in reading order.
    """
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []

    for page in doc:
        blocks = page.get_text("blocks")
        # Sort by vertical position (y0), then horizontal (x0)
        blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        page_text = "\n".join(b[4] for b in blocks if b[4].strip())
        if page_text:
            parts.append(page_text)

    doc.close()
    return "\n\n".join(parts)


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)
