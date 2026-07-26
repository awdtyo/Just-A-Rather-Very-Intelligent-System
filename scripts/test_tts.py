#!/usr/bin/env python3
"""Isolated Piper TTS + playback smoke test.

Usage:
  PYTHONPATH=. python scripts/test_tts.py --no-play   # synth only
  PYTHONPATH=. python scripts/test_tts.py             # synth + play
  PYTHONPATH=. python scripts/test_tts.py --barge-in  # interrupt mid-play
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.audio.playback import AudioPlayback
from jarvis.chunker.sentences import SentenceChunker
from jarvis.config import reload_settings
from jarvis.logging_util import log_event, setup_logging
from jarvis.tts.piper import PiperTTS
from jarvis.types import SentenceChunk, now_monotonic


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test Piper streaming TTS")
    p.add_argument(
        "--text",
        default="Hello. This is JARVIS speaking. Streaming synthesis works.",
    )
    p.add_argument("--no-play", action="store_true", help="Skip speaker output")
    p.add_argument("--barge-in", action="store_true", help="Interrupt after first sentence")
    return p


async def run(args: argparse.Namespace) -> int:
    settings = reload_settings()
    logger = setup_logging(settings)
    tts = PiperTTS(settings)
    t0 = now_monotonic()
    await tts.start()
    print(f"piper ready in {round((now_monotonic()-t0)*1000,1)} ms  sr={tts.sample_rate}")

    playback = None
    first_audio_ms = None
    if not args.no_play:
        playback = AudioPlayback(settings)
        await playback.start()

        def on_first(ts: float) -> None:
            nonlocal first_audio_ms
            if first_audio_ms is None:
                first_audio_ms = round((ts - t_synth0) * 1000, 1)
                print(f"first_audio_out_ms={first_audio_ms}")

        playback.on_first_audio(on_first)

    chunker = SentenceChunker()
    # Simulate token stream as whole words
    tokens = args.text.replace(" ", " |").split("|")
    t_synth0 = now_monotonic()
    index = 0
    total_pcm = 0
    first_tts_ms = None

    async def feed():
        for t in tokens:
            yield t
            await asyncio.sleep(0)

    async for sentence in chunker.stream(feed()):
        print(f"  sentence[{index}]: {sentence!r}")
        sc = SentenceChunk(text=sentence, index=index)
        chunks = await tts.synthesize_sentence(sc)
        for c in chunks:
            total_pcm += len(c.pcm)
            if first_tts_ms is None:
                first_tts_ms = round((c.timestamp - t_synth0) * 1000, 1)
                print(f"first_tts_chunk_ms={first_tts_ms}")
            if playback is not None:
                await playback.enqueue(c)
        index += 1
        if args.barge_in and index >= 1 and playback is not None:
            await asyncio.sleep(0.3)
            print("barge-in → interrupt")
            await playback.interrupt()
            await tts.cancel()
            break

    if playback is not None and not args.barge_in:
        while playback.playing or not playback.queue.empty():
            await asyncio.sleep(0.05)
        await playback.stop()
    elif playback is not None:
        await playback.stop()

    await tts.stop()
    print(f"sentences={index} pcm_bytes={total_pcm}")
    log_event(
        logger,
        "test_tts",
        sentences=index,
        pcm_bytes=total_pcm,
        first_tts_ms=first_tts_ms,
        first_audio_ms=first_audio_ms,
    )
    if index < 1 or total_pcm < 1000:
        print("FAIL", file=sys.stderr)
        return 1
    print("PASS")
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
