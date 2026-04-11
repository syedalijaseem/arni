"""
Tests for documents/chunker.py

RED phase: tests written before implementation.
"""

import pytest


class TestChunker:
    def test_empty_text_returns_empty_list(self):
        """chunk() on empty string returns empty list."""
        from app.documents.chunker import chunk

        result = chunk("", chunk_size_tokens=300, overlap_tokens=50)
        assert result == []

    def test_short_text_returns_single_chunk(self):
        """Text shorter than chunk_size should return a single chunk."""
        from app.documents.chunker import chunk

        short_text = "Hello world, this is a brief test."
        result = chunk(short_text, chunk_size_tokens=300, overlap_tokens=50)
        assert len(result) == 1
        assert result[0] == short_text

    def test_each_chunk_within_token_bounds(self):
        """Every chunk must have between 1 and max_tokens tokens."""
        from app.documents.chunker import chunk
        import tiktoken

        long_text = " ".join(["word"] * 1000)
        chunks = chunk(long_text, chunk_size_tokens=300, overlap_tokens=50)

        enc = tiktoken.get_encoding("cl100k_base")
        for c in chunks:
            token_count = len(enc.encode(c))
            assert 1 <= token_count <= 350  # Allow slight overshoot from words

    def test_multiple_chunks_produced_for_long_text(self):
        """Long text must produce more than one chunk."""
        from app.documents.chunker import chunk

        long_text = " ".join(["sentence word"] * 500)
        result = chunk(long_text, chunk_size_tokens=300, overlap_tokens=50)
        assert len(result) > 1

    def test_overlap_is_present_between_chunks(self):
        """Consecutive chunks must share tokens at the boundary (overlap)."""
        from app.documents.chunker import chunk

        words = ["word" + str(i) for i in range(800)]
        text = " ".join(words)
        chunks = chunk(text, chunk_size_tokens=100, overlap_tokens=20)

        if len(chunks) > 1:
            # The end of chunk[0] and start of chunk[1] must share some words
            end_of_first = chunks[0].split()[-20:]
            start_of_second = chunks[1].split()[:20]
            # There should be at least some overlap words
            overlap_words = set(end_of_first) & set(start_of_second)
            assert len(overlap_words) > 0

    def test_all_text_covered_by_chunks(self):
        """The union of chunks must contain all original words."""
        from app.documents.chunker import chunk

        words = ["unique" + str(i) for i in range(500)]
        text = " ".join(words)
        chunks = chunk(text, chunk_size_tokens=100, overlap_tokens=20)

        combined = " ".join(chunks)
        for word in words:
            assert word in combined

    def test_chunk_size_default_is_300(self):
        """Default chunk_size_tokens must be 300."""
        import inspect
        from app.documents.chunker import chunk

        sig = inspect.signature(chunk)
        assert sig.parameters["chunk_size_tokens"].default == 300

    def test_overlap_default_is_50(self):
        """Default overlap_tokens must be 50."""
        import inspect
        from app.documents.chunker import chunk

        sig = inspect.signature(chunk)
        assert sig.parameters["overlap_tokens"].default == 50
