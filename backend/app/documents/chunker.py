"""
Text Chunker — splits extracted text into overlapping token windows.

Table-aware: text between [TABLE] and [/TABLE] markers is never split
mid-table. Tabular data (CSV/Excel output with "Row N:" lines) is
chunked by row groups with headers repeated in each chunk.

Spec (SRS §4.4):
- Default chunk size: 300 tokens
- Default overlap: 100 tokens
- Tokenizer: cl100k_base (compatible with text-embedding-3-large)
"""

import re
import tiktoken

_ENCODER = None

# Matches [TABLE ...] ... [/TABLE] blocks including newlines
_TABLE_RE = re.compile(r"(\[TABLE[^\]]*\].*?\[/TABLE\])", re.DOTALL)

# Detects tabular text produced by _dataframe_to_rag_text
_ROW_LINE_RE = re.compile(r"^Row \d+:", re.MULTILINE)


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _token_len(text: str) -> int:
    return len(_get_encoder().encode(text))


def _chunk_plain(
    text: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Chunk plain (non-table) text with overlapping token windows."""
    if not text or not text.strip():
        return []

    enc = _get_encoder()
    tokens = enc.encode(text)

    if len(tokens) <= chunk_size_tokens:
        return [enc.decode(tokens)]

    chunks: list[str] = []
    step = max(chunk_size_tokens - overlap_tokens, 1)
    start = 0

    while start < len(tokens):
        end = min(start + chunk_size_tokens, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += step

    return chunks


def _chunk_table(table_text: str, chunk_size_tokens: int) -> list[str]:
    """Split a large table into row-group chunks, each prefixed with headers.

    If the table fits in one chunk, return it as-is.
    Otherwise, split by rows and prepend the header + separator to each group.
    """
    if _token_len(table_text) <= chunk_size_tokens:
        return [table_text]

    lines = table_text.split("\n")

    # Find header: first line after [TABLE ...] marker, plus separator
    header_lines: list[str] = []
    data_lines: list[str] = []
    past_separator = False

    for line in lines:
        if line.startswith("[TABLE") or line.startswith("[/TABLE"):
            header_lines.append(line)
            continue
        if not past_separator:
            header_lines.append(line)
            if line.startswith("-"):
                past_separator = True
        else:
            data_lines.append(line)

    header_text = "\n".join(header_lines)
    header_tokens = _token_len(header_text)
    budget = chunk_size_tokens - header_tokens - 5  # margin

    if budget <= 0:
        # Header alone fills the chunk — just return the whole table
        return [table_text]

    chunks: list[str] = []
    current_rows: list[str] = []
    current_tokens = 0

    for row in data_lines:
        row_tokens = _token_len(row)
        if current_rows and current_tokens + row_tokens > budget:
            chunk = header_text + "\n" + "\n".join(current_rows)
            # Close the table marker if the header had an opening one
            if "[TABLE" in header_text and "[/TABLE]" not in chunk:
                chunk += "\n[/TABLE]"
            chunks.append(chunk)
            current_rows = []
            current_tokens = 0
        current_rows.append(row)
        current_tokens += row_tokens

    if current_rows:
        chunk = header_text + "\n" + "\n".join(current_rows)
        if "[TABLE" in header_text and "[/TABLE]" not in chunk:
            chunk += "\n[/TABLE]"
        chunks.append(chunk)

    return chunks if chunks else [table_text]


def _chunk_tabular(text: str, rows_per_chunk: int = 50) -> list[str]:
    """Chunk tabular text (CSV/Excel output) by row groups.

    The summary line becomes its own chunk. Data rows are grouped with
    headers prepended to each group. Column summaries go in a final chunk.
    """
    lines = text.split("\n")

    header_lines: list[str] = []
    row_lines: list[str] = []
    summary_lines: list[str] = []
    in_summary = False

    for line in lines:
        if line.startswith("Column Summaries:"):
            in_summary = True
            summary_lines.append(line)
        elif in_summary:
            summary_lines.append(line)
        elif _ROW_LINE_RE.match(line):
            row_lines.append(line)
        else:
            header_lines.append(line)

    chunks: list[str] = []

    # Header / summary line as its own chunk
    header_text = "\n".join(l for l in header_lines if l.strip())
    if header_text:
        chunks.append(header_text)

    # Group data rows, prepend column context
    for i in range(0, len(row_lines), rows_per_chunk):
        batch = row_lines[i:i + rows_per_chunk]
        chunk_text = header_text + "\n\n" + "\n".join(batch) if header_text else "\n".join(batch)
        chunks.append(chunk_text)

    # Column summaries as final chunk
    if summary_lines:
        chunks.append("\n".join(summary_lines))

    return chunks if chunks else _chunk_plain(text, 300, 100)


def _is_tabular(text: str) -> bool:
    """Return True if text looks like CSV/Excel output from our extractor."""
    return bool(_ROW_LINE_RE.search(text)) and "Data from " in text[:200]


def chunk(
    text: str,
    chunk_size_tokens: int = 300,
    overlap_tokens: int = 100,
) -> list[str]:
    """
    Split text into overlapping token windows, preserving table blocks.

    Table blocks (wrapped in [TABLE]...[/TABLE]) are never split mid-row.
    Tabular data (CSV/Excel) is chunked by row groups with headers repeated.
    Plain text between tables is chunked with the standard overlap strategy.

    Args:
        text: The full extracted document text.
        chunk_size_tokens: Target number of tokens per chunk (default 300).
        overlap_tokens: Number of tokens to repeat at the start of the next
                        chunk for context continuity (default 100).

    Returns:
        List of text chunk strings. Empty list if text is empty.
    """
    if not text or not text.strip():
        return []

    # Tabular text (CSV/Excel) gets special row-group chunking
    if _is_tabular(text):
        return _chunk_tabular(text)

    # Split text into alternating plain / table segments
    segments = _TABLE_RE.split(text)

    all_chunks: list[str] = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        if segment.startswith("[TABLE"):
            all_chunks.extend(_chunk_table(segment, chunk_size_tokens))
        else:
            all_chunks.extend(
                _chunk_plain(segment, chunk_size_tokens, overlap_tokens)
            )

    return all_chunks
