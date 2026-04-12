"""
Text Chunker — splits extracted text into overlapping token windows.

Spec (SRS §4.4):
- Default chunk size: 300 tokens
- Default overlap: 100 tokens (increased from 50 for better boundary context)
- Min chunk size: 200 tokens (except for final chunk which may be smaller)
- Max chunk size: 400 tokens
- Tokenizer: cl100k_base (compatible with text-embedding-3-large)
"""

import tiktoken

_ENCODER = None


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def chunk(
    text: str,
    chunk_size_tokens: int = 300,
    overlap_tokens: int = 100,
) -> list[str]:
    """
    Split text into overlapping token windows.

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

    enc = _get_encoder()
    tokens = enc.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        return []

    if total_tokens <= chunk_size_tokens:
        return [enc.decode(tokens)]

    chunks: list[str] = []
    step = chunk_size_tokens - overlap_tokens
    if step <= 0:
        step = 1

    start = 0
    while start < total_tokens:
        end = min(start + chunk_size_tokens, total_tokens)
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        if end == total_tokens:
            break
        start += step

    return chunks
