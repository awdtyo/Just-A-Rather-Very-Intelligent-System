"""Groq streaming LLM client (hybrid brain)."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from groq import AsyncGroq

from jarvis.config import Settings

logger = logging.getLogger("jarvis.llm")


class GroqBrain:
    """Streaming chat completions with a short rolling history."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._history: deque[dict[str, str]] = deque(maxlen=settings.history_turns)

    def clear_history(self) -> None:
        self._history.clear()

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.settings.system_prompt},
            *list(self._history),
            {"role": "user", "content": user_text},
        ]
        logger.info(
            "llm_request model=%s user=%r history=%d",
            self.settings.groq_model,
            user_text[:80],
            len(self._history),
        )
        stream = await self._client.chat.completions.create(
            model=self.settings.groq_model,
            messages=messages,
            temperature=self.settings.groq_temperature,
            max_tokens=self.settings.groq_max_tokens,
            stream=True,
        )
        assistant_parts: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if not delta:
                continue
            assistant_parts.append(delta)
            yield delta

        full = "".join(assistant_parts).strip()
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": full})
        logger.info("llm_complete chars=%d", len(full))
