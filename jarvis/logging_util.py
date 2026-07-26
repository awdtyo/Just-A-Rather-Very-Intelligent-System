"""Structured JSON-lines logging for latency and pipeline events."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jarvis.config import Settings, get_settings
from jarvis.types import TurnLatency


class JsonLineFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(settings: Optional[Settings] = None) -> logging.Logger:
    """Configure root jarvis logger (stdout + optional rotating file)."""
    settings = settings or get_settings()
    logger = logging.getLogger("jarvis")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(JsonLineFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    logger.addHandler(handler)

    log_dir: Path = settings.log_dir_resolved
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "jarvis.jsonl", encoding="utf-8")
    file_handler.setFormatter(JsonLineFormatter())
    logger.addHandler(file_handler)

    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log a structured pipeline event."""
    record = logger.makeRecord(
        logger.name,
        level,
        "(event)",
        0,
        event,
        args=(),
        exc_info=None,
    )
    record.extra_fields = {"event": event, **fields}
    logger.handle(record)


def log_turn_latency(logger: logging.Logger, latency: TurnLatency) -> None:
    """Emit the end-of-turn latency summary (time-to-first-audio is the headline)."""
    metrics = latency.as_dict()
    log_event(logger, "turn_latency", **metrics)
