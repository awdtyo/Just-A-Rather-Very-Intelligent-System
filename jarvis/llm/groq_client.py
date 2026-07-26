"""Groq streaming LLM client (hybrid brain with tool support)."""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, Optional

from groq import AsyncGroq

from jarvis.config import Settings
from jarvis.tools.base import ToolRegistry

logger = logging.getLogger("jarvis.llm")


class GroqBrain:
    """Streaming chat completions with a short rolling history and optional tool support."""

    def __init__(
        self,
        settings: Settings,
        *,
        memory_context: str = "",
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.settings = settings
        self._memory_context = memory_context
        self._tool_registry = tool_registry
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set")
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._history: deque[dict[str, str]] = deque(maxlen=settings.history_turns)

    def clear_history(self) -> None:
        self._history.clear()

    def set_memory_context(self, context: str) -> None:
        self._memory_context = context

    def _build_system_prompt(self) -> str:
        parts = [self.settings.system_prompt]
        if self._memory_context:
            parts.append(self._memory_context)
        return "\n\n".join(parts)

    def _build_messages(self, user_text: str) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": self._build_system_prompt()},
            *list(self._history),
            {"role": "user", "content": user_text},
        ]

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Stream a plain text reply (no tools)."""
        messages = self._build_messages(user_text)
        logger.info(
            "llm_request model=%s user=%r history=%d tools=false",
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

    async def stream_reply_collect(self, user_text: str) -> str:
        """Stream a reply and return the full text (for tool-result follow-ups)."""
        parts: list[str] = []
        async for token in self.stream_reply(user_text):
            parts.append(token)
        return "".join(parts)

    async def complete_with_tools(
        self, user_text: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Non-streaming completion with tool support.

        Returns:
            (final_text, tool_calls) where tool_calls is a list of
            {"id": str, "name": str, "arguments": dict} for any tool invocations.
        """
        if self._tool_registry is None or self._tool_registry.is_empty:
            # No tools available — fall back to streaming and collect the full text
            parts: list[str] = []
            async for token in self.stream_reply(user_text):
                parts.append(token)
            return "".join(parts), []

        messages = self._build_messages(user_text)
        tools = self._tool_registry.groq_tools()
        logger.info(
            "llm_request model=%s user=%r history=%d tools=%d",
            self.settings.groq_model,
            user_text[:80],
            len(self._history),
            len(tools),
        )

        try:
            response = await self._client.chat.completions.create(
                model=self.settings.groq_model,
                messages=messages,
                temperature=self.settings.groq_temperature,
                max_tokens=self.settings.groq_max_tokens,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            # If tool call validation fails (model hallucinated a tool),
            # fall back to a plain completion without tools.
            err_str = str(e).lower()
            is_tool_error = (
                "tool call validation" in err_str
                or "not in request.tools" in err_str
                or "tool_use_failed" in err_str
                or "brave_search" in err_str
            )
            if is_tool_error:
                logger.warning("tool hallucination detected, falling back to text: %s", e)
                plain_messages = self._build_messages(user_text)
                stream = await self._client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=plain_messages,
                    temperature=self.settings.groq_temperature,
                    max_tokens=self.settings.groq_max_tokens,
                )
                text = stream.choices[0].message.content or ""
                self._history.append({"role": "user", "content": user_text})
                if text:
                    self._history.append({"role": "assistant", "content": text})
                logger.info("llm_fallback_complete chars=%d", len(text))
                return text, []
            raise

        choice = response.choices[0]
        message = choice.message

        # Collect tool calls if present
        tool_calls: list[dict[str, Any]] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        # Build the text reply (may be empty if only tools were called)
        text = message.content or ""

        # Append to history
        self._history.append({"role": "user", "content": user_text})
        if text:
            self._history.append({"role": "assistant", "content": text})
        logger.info("llm_complete chars=%d tool_calls=%d", len(text), len(tool_calls))

        return text, tool_calls

    async def complete_with_tool_results(
        self, user_text: str, tool_results: list[dict[str, str]]
    ) -> str:
        """Continue a conversation after tool execution, streaming the final reply.

        tool_results: list of {"tool_call_id": str, "content": str}

        NOTE: We intentionally do NOT add tool messages to history. The tool results
        are embedded in the synthetic user_text passed to the LLM. Adding orphaned
        tool-role messages would break Groq's API (tool messages require a preceding
        assistant message with tool_calls).
        """
        return await self.stream_reply_collect(user_text)
