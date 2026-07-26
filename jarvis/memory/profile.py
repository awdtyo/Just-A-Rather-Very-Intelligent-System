"""Load profile.yaml + notes and inject into the LLM system prompt."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("jarvis.memory")


class ProfileMemory:
    """Loads a YAML profile and freeform markdown notes from disk."""

    def __init__(self, profile_path: Path, notes_dir: Path) -> None:
        self.profile_path = profile_path
        self.notes_dir = notes_dir
        self._profile: dict[str, Any] = {}
        self._notes: dict[str, str] = {}  # title -> content
        self.reload()

    def reload(self) -> None:
        """Re-read profile + notes from disk."""
        self._load_profile()
        self._load_notes()

    def _load_profile(self) -> None:
        if not self.profile_path.exists():
            logger.warning("profile.yaml not found at %s", self.profile_path)
            return
        try:
            with open(self.profile_path, "r", encoding="utf-8") as f:
                self._profile = yaml.safe_load(f) or {}
            logger.info("loaded profile with %d top-level keys", len(self._profile))
        except Exception:
            logger.exception("failed to load profile.yaml")

    def _load_notes(self) -> None:
        self._notes.clear()
        if not self.notes_dir.exists():
            return
        for md_file in sorted(self.notes_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8").strip()
                if content:
                    self._notes[md_file.stem] = content
            except Exception:
                logger.exception("failed to load note %s", md_file.name)
        if self._notes:
            logger.info("loaded %d notes", len(self._notes))

    @property
    def profile(self) -> dict[str, Any]:
        return self._profile

    @property
    def notes(self) -> dict[str, str]:
        return self._notes

    def build_context_block(self) -> str:
        """Build a string to inject into the system prompt."""
        parts: list[str] = []

        if self._profile:
            parts.append("## User Profile")
            for key, value in self._profile.items():
                if key == "do_not_invent":
                    continue
                if isinstance(value, list):
                    if value:
                        lines = []
                        for item in value:
                            if isinstance(item, dict):
                                lines.append(
                                    "  - " + ", ".join(f"{k}: {v}" for k, v in item.items())
                                )
                            else:
                                lines.append(f"  - {item}")
                        parts.append(f"{key}:\n" + "\n".join(lines))
                elif isinstance(value, dict):
                    lines = []
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                    parts.append(f"{key}:\n" + "\n".join(lines))
                elif value:
                    parts.append(f"{key}: {value}")

        if self._profile.get("do_not_invent"):
            parts.append(
                "RULE: Never invent personal facts, schedule items, or preferences. "
                "If you don't have it saved, say so and offer to add it."
            )

        if self._notes:
            parts.append("## Notes")
            for title, content in self._notes.items():
                parts.append(f"### {title}\n{content}")

        return "\n\n".join(parts)

    def save_note(self, title: str, content: str) -> str:
        """Write a note to data/notes/{title}.md."""
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
        path = self.notes_dir / f"{safe_title}.md"
        path.write_text(content, encoding="utf-8")
        self._notes[safe_title] = content
        logger.info("saved note: %s", path.name)
        return f"Note saved: {title}"

    def update_profile_field(self, field_path: str, value: Any) -> str:
        """Update a profile field using dot notation (e.g. 'timezone')."""
        keys = field_path.split(".")
        target = self._profile
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        old_value = target.get(keys[-1])
        target[keys[-1]] = value
        self._persist_profile()
        logger.info("profile field updated: %s = %r (was %r)", field_path, value, old_value)
        return f"Updated {field_path} to {value}"

    def _persist_profile(self) -> None:
        """Write current profile back to YAML."""
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profile_path, "w", encoding="utf-8") as f:
            yaml.dump(self._profile, f, default_flow_style=False, allow_unicode=True)
