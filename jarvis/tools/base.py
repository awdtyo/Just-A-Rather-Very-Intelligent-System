"""Tool schema, registry, and Groq-compatible tool definitions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.tools")


@dataclass
class Tool:
    """A callable tool with metadata."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the parameters
    handler: Callable[..., Awaitable[str]]  # async (args) -> result_text
    requires_confirm: bool = False

    def to_groq_schema(self) -> dict[str, Any]:
        """Return OpenAI/Groq-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("registered tool: %s (confirm=%s)", tool.name, tool.requires_confirm)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def groq_tools(self) -> list[dict[str, Any]]:
        """Return all tool schemas in Groq/OpenAI format."""
        return [t.to_groq_schema() for t in self._tools.values()]

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def is_empty(self) -> bool:
        return len(self._tools) == 0

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call. Returns result text or error message."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            result = await tool.handler(arguments)
            return result
        except Exception as e:
            logger.exception("tool execution failed: %s", name)
            return f"Error executing {name}: {e}"
