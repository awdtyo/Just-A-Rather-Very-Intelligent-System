#!/usr/bin/env python3
"""Tool registry + confirm gate smoke test — no network/audio."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.tools.base import Tool, ToolRegistry  # noqa: E402
from jarvis.tools.confirm import ConfirmStore, PendingAction  # noqa: E402


async def test_registry() -> None:
    """Register tools and execute them."""
    registry = ToolRegistry()
    assert registry.is_empty

    async def _echo(args: dict) -> str:
        return f"echo: {args.get('text', '')}"

    async def _fail(args: dict) -> str:
        raise ValueError("boom")

    registry.register(Tool(
        name="echo",
        description="Echo text back",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=_echo,
    ))
    registry.register(Tool(
        name="fail",
        description="Always fails",
        parameters={"type": "object", "properties": {}},
        handler=_fail,
    ))

    assert not registry.is_empty
    assert "echo" in registry.names
    assert "fail" in registry.names

    # Execute echo
    result = await registry.execute("echo", {"text": "hello"})
    assert result == "echo: hello", f"Expected 'echo: hello', got: {result!r}"

    # Execute fail — should return error string, not raise
    result = await registry.execute("fail", {})
    assert "Error" in result, f"Expected error, got: {result!r}"

    # Unknown tool
    result = await registry.execute("nope", {})
    assert "Error" in result

    # Groq schema generation
    schemas = registry.groq_tools()
    assert len(schemas) == 2
    assert schemas[0]["function"]["name"] == "echo"

    print("registry PASS")


def test_confirm_store() -> None:
    """Test confirm/cancel matching."""
    store = ConfirmStore()
    assert not store.has_pending

    store.store(PendingAction(
        tool_name="send_email",
        arguments={"to": "alice@example.com", "subject": "Hi", "body": "Hello"},
        description="send email to alice@example.com",
    ))
    assert store.has_pending
    assert store.pending.tool_name == "send_email"

    # Ambiguous — should return None
    assert store.check("sure thing maybe") is None

    # Confirm variants
    for phrase in ["yes", "Yeah", "send it", "confirm", "do it", "go ahead"]:
        store.store(PendingAction(tool_name="test", arguments={}, description="test"))
        result = store.check(phrase)
        assert result == "confirm", f"Expected confirm for '{phrase}', got: {result!r}"

    # Cancel variants
    for phrase in ["no", "cancel", "stop", "don't send", "nevermind"]:
        store.store(PendingAction(tool_name="test", arguments={}, description="test"))
        result = store.check(phrase)
        assert result == "cancel", f"Expected cancel for '{phrase}', got: {result!r}"

    store.clear()
    assert not store.has_pending
    print("confirm_store PASS")


def test_groq_schema_format() -> None:
    """Verify tool schema matches Groq/OpenAI function calling format."""
    async def _noop(args: dict) -> str:
        return "ok"

    tool = Tool(
        name="test_tool",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
        handler=_noop,
        requires_confirm=True,
    )
    schema = tool.to_groq_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "test_tool"
    assert schema["function"]["description"] == "A test tool"
    assert "x" in schema["function"]["parameters"]["properties"]
    print("groq_schema PASS")


def main() -> int:
    asyncio.run(test_registry())
    test_confirm_store()
    test_groq_schema_format()
    print("\nALL TOOL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
