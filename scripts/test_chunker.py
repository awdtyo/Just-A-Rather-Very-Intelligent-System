#!/usr/bin/env python3
"""Isolated sentence chunker smoke test (no network/audio)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.chunker.sentences import SentenceChunker


async def token_gen(text: str, width: int = 3):
    for i in range(0, len(text), width):
        yield text[i : i + width]
        await asyncio.sleep(0)


async def run() -> int:
    text = (
        "Good morning. The weather looks clear today, so you might enjoy a walk. "
        "Shall I set a reminder?"
    )
    chunker = SentenceChunker()
    emitted: list[str] = []
    async for sentence in chunker.stream(token_gen(text)):
        emitted.append(sentence)
        print(f"  chunk: {sentence!r}")

    if len(emitted) < 2:
        print(f"FAIL: expected ≥2 chunks, got {emitted}", file=sys.stderr)
        return 1
    # First chunk should end at first sentence
    if not emitted[0].rstrip().endswith("."):
        print(f"FAIL: first chunk not sentence-ended: {emitted[0]!r}", file=sys.stderr)
        return 1
    joined = " ".join(emitted)
    if "Good morning" not in joined or "reminder" not in joined.lower():
        print("FAIL: content missing", file=sys.stderr)
        return 1
    print(f"PASS ({len(emitted)} chunks)")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
