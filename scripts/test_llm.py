#!/usr/bin/env python3
"""Isolated Groq streaming LLM smoke test."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.config import reload_settings
from jarvis.llm.groq_client import GroqBrain
from jarvis.logging_util import log_event, setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test Groq streaming tokens")
    p.add_argument(
        "--prompt",
        default="In one short sentence, what is 2+2?",
        help="User prompt",
    )
    return p


async def run(prompt: str) -> int:
    settings = reload_settings()
    logger = setup_logging(settings)
    brain = GroqBrain(settings)
    print(f"model={settings.groq_model}")
    print(f"prompt={prompt!r}")
    t0 = time.perf_counter()
    first_ms = None
    parts: list[str] = []
    async for token in brain.stream_reply(prompt):
        if first_ms is None:
            first_ms = round((time.perf_counter() - t0) * 1000, 1)
            print(f"\nfirst_token_ms={first_ms}")
            print("--- stream ---")
        parts.append(token)
        print(token, end="", flush=True)
    print("\n--------------")
    full = "".join(parts)
    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    print(f"chars={len(full)} total_ms={total_ms}")
    log_event(
        logger,
        "test_llm",
        first_token_ms=first_ms,
        total_ms=total_ms,
        chars=len(full),
        reply=full,
    )
    if first_ms is None or not full.strip():
        print("FAIL: no tokens", file=sys.stderr)
        return 1
    print("PASS")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
