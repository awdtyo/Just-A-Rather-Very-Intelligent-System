"""Groq streaming LLM client — stub for step 5."""

from __future__ import annotations

from collections.abc import AsyncIterator

from jarvis.config import Settings


class GroqBrain:
    """Streaming chat completions with short conversation history.

    Implemented in build step 5.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        raise NotImplementedError("GroqBrain.stream_reply — implement in step 5")
        yield  # pragma: no cover — makes this an async generator for type checkers
