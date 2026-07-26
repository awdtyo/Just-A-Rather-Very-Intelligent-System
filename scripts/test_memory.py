#!/usr/bin/env python3
"""Memory (profile + notes) smoke test — no network/audio."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.memory.profile import ProfileMemory  # noqa: E402


def test_profile_load() -> None:
    """Load the real profile.yaml and build a context block."""
    profile_path = ROOT / "data" / "profile.yaml"
    notes_dir = ROOT / "data" / "notes"
    mem = ProfileMemory(profile_path, notes_dir)
    ctx = mem.build_context_block()
    assert "User Profile" in ctx, f"Expected 'User Profile' in context, got: {ctx[:200]}"
    assert "do_not_invent" not in ctx, "do_not_invent should not appear in context"
    print(f"  profile context: {len(ctx)} chars")
    print("profile_load PASS")


def test_save_note() -> None:
    """Save a note and verify it loads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / "profile.yaml"
        profile_path.write_text("full_name: Test\n")
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()

        mem = ProfileMemory(profile_path, notes_dir)
        result = mem.save_note("test_note", "This is a test note content.")
        assert "saved" in result.lower(), f"Expected save confirmation, got: {result}"

        mem.reload()
        assert "test_note" in mem.notes, "Note not found after reload"
        assert "test note content" in mem.notes["test_note"]
        print("save_note PASS")


def test_update_profile() -> None:
    """Update a profile field and verify it persists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / "profile.yaml"
        profile_path.write_text("full_name: Test\ntimezone: UTC\n")
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()

        mem = ProfileMemory(profile_path, notes_dir)
        result = mem.update_profile_field("timezone", "US/Pacific")
        assert "US/Pacific" in result

        # Reload and verify
        mem2 = ProfileMemory(profile_path, notes_dir)
        assert mem2.profile.get("timezone") == "US/Pacific"
        print("update_profile PASS")


def test_context_block() -> None:
    """Build context from a custom profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / "profile.yaml"
        profile_path.write_text(
            "full_name: Alice\npreferred_name: Ali\ntimezone: Asia/Kolkata\n"
            "work:\n  role: Engineer\n  company: Acme\n"
            "do_not_invent: true\n"
        )
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()
        (notes_dir / "preferences.md").write_text("I prefer dark mode.")

        mem = ProfileMemory(profile_path, notes_dir)
        ctx = mem.build_context_block()
        assert "Alice" in ctx
        assert "Engineer" in ctx
        assert "dark mode" in ctx
        assert "RULE:" in ctx
        print(f"  context block:\n{ctx}")
        print("context_block PASS")


def main() -> int:
    test_profile_load()
    test_save_note()
    test_update_profile()
    test_context_block()
    print("\nALL MEMORY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
