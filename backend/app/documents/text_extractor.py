"""
Text Extractor — pulls raw text from PDF, DOCX, TXT, CSV, and Excel files.

Supported MIME types:
- application/pdf
- application/vnd.openxmlformats-officedocument.wordprocessingml.document
- text/plain
- text/csv, application/csv
- application/vnd.ms-excel
- application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
"""

import io
import logging

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_CSV_TYPES = {"text/csv", "application/csv"}
_EXCEL_TYPES = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def extract(file_bytes: bytes, content_type: str) -> str:
    if content_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"unsupported file type: {content_type!r}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_TYPES))}"
        )

    if content_type == "text/plain":
        return _extract_txt(file_bytes)
    if content_type == "application/pdf":
        return _extract_pdf(file_bytes)
    if content_type in _CSV_TYPES:
        return _extract_csv(file_bytes)
    if content_type in _EXCEL_TYPES:
        return _extract_excel(file_bytes)
    # DOCX
    return _extract_docx(file_bytes)


def _extract_txt(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def _extract_pdf(file_bytes: bytes) -> str:
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []

    for page in doc:
        blocks = page.get_text("blocks")
        blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        page_text = "\n".join(b[4] for b in blocks if b[4].strip())
        if page_text:
            parts.append(page_text)

    doc.close()
    return "\n\n".join(parts)


def _extract_docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _dataframe_to_rag_text(df, name: str) -> str:
    """Convert a pandas DataFrame to explicit key-value rows for RAG.

    Each row becomes "Row N: Col1: val1, Col2: val2, ..."
    so column headers stay with values in every chunk.
    Numeric columns get a summary block at the end.
    """
    import pandas as pd

    headers = list(df.columns)
    lines: list[str] = []

    lines.append(
        f"Data from {name}: {len(df)} rows, "
        f"columns: {', '.join(str(h) for h in headers)}"
    )
    lines.append("")

    for idx, row in df.iterrows():
        pairs = []
        for col in headers:
            val = row[col]
            if pd.notna(val):
                pairs.append(f"{col}: {val}")
        if pairs:
            lines.append(f"Row {idx + 1}: {', '.join(pairs)}")

    # Numeric column summaries
    numeric_summaries: list[str] = []
    for col in headers:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_summaries.append(
                f"{col} — "
                f"Total: {df[col].sum():.2f}, "
                f"Average: {df[col].mean():.2f}, "
                f"Min: {df[col].min():.2f}, "
                f"Max: {df[col].max():.2f}"
            )
    if numeric_summaries:
        lines.append("")
        lines.append("Column Summaries:")
        lines.extend(numeric_summaries)

    return "\n".join(lines)


def _extract_csv(file_bytes: bytes) -> str:
    import pandas as pd

    df = pd.read_csv(io.BytesIO(file_bytes))
    return _dataframe_to_rag_text(df, "CSV")


def _extract_excel(file_bytes: bytes) -> str:
    import pandas as pd

    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    parts: list[str] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet)
        parts.append(f"Sheet: {sheet}")
        parts.append(_dataframe_to_rag_text(df, sheet))
    return "\n\n".join(parts)
