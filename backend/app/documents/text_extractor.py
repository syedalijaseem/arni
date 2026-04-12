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


def _format_table_as_text(table: list) -> str:
    """Convert a pdfplumber table to explicit header-value pairs.

    Each data row is rendered as "Header1: value1, Header2: value2, ..."
    so that RAG retrieval can match metrics to their column names.
    """
    if not table or not table[0]:
        return ""

    headers = [str(h).strip() if h else "" for h in table[0]]

    rows: list[str] = []
    # Header row as pipe-delimited for readability
    rows.append(" | ".join(h for h in headers if h))
    rows.append("-" * 50)

    for row in table[1:]:
        if not row or not any(cell for cell in row):
            continue
        parts: list[str] = []
        for i, cell in enumerate(row):
            if cell and i < len(headers) and headers[i]:
                parts.append(f"{headers[i]}: {str(cell).strip()}")
        if parts:
            rows.append(", ".join(parts))

    return "\n".join(rows)


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF with table detection.

    Tables are extracted first per page and wrapped in [TABLE] markers
    so the chunker can keep them intact. Regular page text follows.
    """
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Extract tables first
            tables = page.extract_tables()
            for table in tables:
                if table:
                    table_text = _format_table_as_text(table)
                    if table_text.strip():
                        parts.append(
                            f"[TABLE on page {page_num + 1}]\n{table_text}\n[/TABLE]"
                        )

            # Then extract regular text
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)

    return "\n\n".join(parts)


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)
