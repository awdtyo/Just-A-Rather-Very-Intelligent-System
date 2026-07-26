#!/usr/bin/env python3
"""Social connectors smoke test — verifies tool registration and schema format."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.tools.base import ToolRegistry  # noqa: E402


def test_whatsapp_tools() -> None:
    from jarvis.tools.whatsapp_meta import build_whatsapp_tools

    tools = build_whatsapp_tools("fake_token", "fake_phone_id")
    assert len(tools) == 3
    names = [t.name for t in tools]
    assert "read_whatsapp_inbox" in names
    assert "send_whatsapp_message" in names
    assert "draft_whatsapp_reply" in names

    send_tool = next(t for t in tools if t.name == "send_whatsapp_message")
    assert send_tool.requires_confirm

    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    schemas = registry.groq_tools()
    assert len(schemas) == 3
    print("whatsapp_tools PASS")


def test_instagram_tools() -> None:
    from jarvis.tools.instagram_meta import build_instagram_tools

    tools = build_instagram_tools("fake_token", "fake_ig_id")
    assert len(tools) == 4
    names = [t.name for t in tools]
    assert "read_instagram_comments" in names
    assert "reply_to_instagram_comment" in names
    assert "create_instagram_post" in names
    assert "draft_instagram_post" in names

    reply_tool = next(t for t in tools if t.name == "reply_to_instagram_comment")
    assert reply_tool.requires_confirm
    post_tool = next(t for t in tools if t.name == "create_instagram_post")
    assert post_tool.requires_confirm
    draft_tool = next(t for t in tools if t.name == "draft_instagram_post")
    assert not draft_tool.requires_confirm

    print("instagram_tools PASS")


def test_linkedin_tools() -> None:
    from jarvis.tools.linkedin import build_linkedin_tools

    tools = build_linkedin_tools("fake_token")
    assert len(tools) == 4
    names = [t.name for t in tools]
    assert "read_linkedin_profile" in names
    assert "create_linkedin_post" in names
    assert "draft_linkedin_post" in names
    assert "draft_linkedin_dm" in names

    create_tool = next(t for t in tools if t.name == "create_linkedin_post")
    assert create_tool.requires_confirm
    draft_tool = next(t for t in tools if t.name == "draft_linkedin_post")
    assert not draft_tool.requires_confirm
    dm_tool = next(t for t in tools if t.name == "draft_linkedin_dm")
    assert not dm_tool.requires_confirm

    print("linkedin_tools PASS")


def test_describe_tool_calls() -> None:
    """Verify _describe_tool_call covers all confirm-gated tools."""
    try:
        from jarvis.orchestrator.pipeline import Pipeline  # noqa: E402
    except (ImportError, ModuleNotFoundError):
        print("describe_tool_calls SKIP (sounddevice not available)")
        return

    class MockPipeline:
        pass

    mock = MockPipeline()
    method = Pipeline._describe_tool_call.__get__(mock)

    assert "email" in method("send_email", {"to": "a@b.com", "subject": "Hi"}).lower()
    assert "whatsapp" in method("send_whatsapp_message", {"to": "+123", "text": "Hi"}).lower()
    assert "instagram" in method("create_instagram_post", {"caption": "Hello"}).lower()
    assert "linkedin" in method("create_linkedin_post", {"text": "Hello"}).lower()
    assert "calendar" in method("create_calendar_event", {"summary": "Meeting", "start_time": "2pm"}).lower()
    print("describe_tool_calls PASS")


def main() -> int:
    test_whatsapp_tools()
    test_instagram_tools()
    test_linkedin_tools()
    test_describe_tool_calls()
    print("\nALL CONNECTOR TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
