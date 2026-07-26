"""Confirm gate for side-effect tools (send, post, etc.)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("jarvis.tools.confirm")

_CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|confirm|do it|go ahead|send it|send|proceed)\b", re.IGNORECASE
)
_CANCEL_RE = re.compile(
    r"\b(cancel|stop|nevermind|never mind|abort|do not|don.t|nope|no)\b", re.IGNORECASE
)


@dataclass
class PendingAction:
    """An action awaiting user confirmation before execution."""

    tool_name: str
    arguments: dict[str, Any]
    description: str  # human-readable summary of what will happen
    handler_name: str = ""  # optional: override handler dispatch


class ConfirmStore:
    """Holds a single pending action awaiting confirmation."""

    def __init__(self) -> None:
        self._pending: Optional[PendingAction] = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    @property
    def pending(self) -> Optional[PendingAction]:
        return self._pending

    def store(self, action: PendingAction) -> None:
        self._pending = action
        logger.info(
            "confirm gate: stored action %s — %s",
            action.tool_name,
            action.description,
        )

    def clear(self) -> None:
        self._pending = None

    def check(self, user_text: str) -> str | None:
        """Check user text against confirm/cancel patterns.

        Returns:
            "confirm" if user confirmed,
            "cancel" if user cancelled,
            None if ambiguous (ask again).
        """
        text = user_text.strip().lower()
        # Check cancel first — "don't send" should cancel, not confirm
        if _CANCEL_RE.search(text):
            logger.info("confirm gate: user cancelled")
            return "cancel"
        if _CONFIRM_RE.search(text):
            logger.info("confirm gate: user confirmed")
            return "confirm"
        return None
