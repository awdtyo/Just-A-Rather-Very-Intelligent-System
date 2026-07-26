"""Memory tools — save notes and update profile via voice."""

from __future__ import annotations

from typing import Any

from jarvis.memory.profile import ProfileMemory
from jarvis.tools.base import Tool


def build_memory_tools(memory: ProfileMemory) -> list[Tool]:
    """Return memory-related tools bound to the given ProfileMemory instance."""

    async def _save_note(args: dict[str, Any]) -> str:
        title = args.get("title", "").strip()
        content = args.get("content", "").strip()
        if not title or not content:
            return "Error: both title and content are required."
        return memory.save_note(title, content)

    async def _update_profile(args: dict[str, Any]) -> str:
        field_path = args.get("field", "").strip()
        value = args.get("value", "").strip()
        if not field_path or not value:
            return "Error: both field and value are required."
        return memory.update_profile_field(field_path, value)

    return [
        Tool(
            name="save_note",
            description="Save a note to JARVIS's local notes. Use this when the user wants to remember something.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title for the note",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content of the note",
                    },
                },
                "required": ["title", "content"],
            },
            handler=_save_note,
            requires_confirm=False,
        ),
        Tool(
            name="update_profile",
            description="Update a field in the user's profile. Use this for preferences, timezone, name, etc.",
            parameters={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Dot-separated field path, e.g. 'timezone' or 'work.role'",
                    },
                    "value": {
                        "type": "string",
                        "description": "The new value to set",
                    },
                },
                "required": ["field", "value"],
            },
            handler=_update_profile,
            requires_confirm=False,
        ),
    ]
