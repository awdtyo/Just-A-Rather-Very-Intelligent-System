"""Sentence / clause boundary chunker for streaming TTS."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator

# Prefer strong sentence ends; also split on clause boundaries when the buffer
# is getting long so TTS can start sooner.
_SENTENCE_END = re.compile(r"([.!?]+)(\s+|$)")
_CLAUSE_BREAK = re.compile(r"([,;:])(\s+)")
_MAX_CLAUSE_CHARS = 120


class SentenceChunker:
    """Split a token stream into speakable clauses as boundaries appear."""

    def __init__(self, max_clause_chars: int = _MAX_CLAUSE_CHARS) -> None:
        self._buf = ""
        self.max_clause_chars = max_clause_chars

    def reset(self) -> None:
        self._buf = ""

    def feed(self, token: str) -> Iterator[str]:
        self._buf += token
        yield from self._emit_ready(flush=False)

    def flush(self) -> Iterator[str]:
        yield from self._emit_ready(flush=True)

    def _emit_ready(self, *, flush: bool) -> Iterator[str]:
        while True:
            match = _SENTENCE_END.search(self._buf)
            if match:
                end = match.end()
                piece = self._buf[:end].strip()
                self._buf = self._buf[end:]
                if piece:
                    yield piece
                continue

            # Soft clause split only when buffer is long enough
            if len(self._buf) >= self.max_clause_chars:
                match = _CLAUSE_BREAK.search(self._buf)
                if match and match.end() > 20:
                    end = match.end()
                    piece = self._buf[:end].strip()
                    self._buf = self._buf[end:]
                    if piece:
                        yield piece
                    continue

            if flush:
                leftover = self._buf.strip()
                self._buf = ""
                if leftover:
                    yield leftover
            break

    async def stream(self, tokens: AsyncIterator[str]) -> AsyncIterator[str]:
        async for token in tokens:
            for sentence in self.feed(token):
                yield sentence
        for sentence in self.flush():
            yield sentence
