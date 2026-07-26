"""Sentence / clause boundary chunker — stub for step 6."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator


class SentenceChunker:
    """Split a token stream into speakable clauses as boundaries appear.

    Implemented in build step 6.
    """

    def feed(self, token: str) -> Iterator[str]:
        """Yield zero or more complete sentences from a new token."""
        raise NotImplementedError("SentenceChunker.feed — implement in step 6")
        yield  # pragma: no cover

    def flush(self) -> Iterator[str]:
        """Yield any remaining buffered text at end-of-stream."""
        raise NotImplementedError("SentenceChunker.flush — implement in step 6")
        yield  # pragma: no cover

    async def stream(self, tokens: AsyncIterator[str]) -> AsyncIterator[str]:
        raise NotImplementedError("SentenceChunker.stream — implement in step 6")
        yield  # pragma: no cover
