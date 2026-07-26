#!/usr/bin/env python3
"""Isolated faster-whisper STT smoke test.

Usage:
  PYTHONPATH=. python scripts/test_stt.py --synthetic
  PYTHONPATH=. python scripts/test_stt.py --duration 8
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.audio.capture import AudioCapture
from jarvis.config import reload_settings
from jarvis.logging_util import log_event, setup_logging
from jarvis.stt.whisper import StreamingTranscriber
from jarvis.types import now_monotonic


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test streaming faster-whisper")
    p.add_argument("--synthetic", action="store_true", help="Transcribe generated tone+noise WAV")
    p.add_argument("--wav", type=str, default=None, help="Transcribe a 16kHz mono wav")
    p.add_argument("--duration", type=float, default=6.0)
    return p


def _make_dummy_pcm(sample_rate: int = 16000, seconds: float = 2.0) -> bytes:
    """Not real speech — used only to verify model loads and returns quickly."""
    n = int(sample_rate * seconds)
    t = np.arange(n) / sample_rate
    # Soft noise so whisper doesn't hang on pure digital silence edge cases
    rng = np.random.default_rng(42)
    audio = (0.01 * rng.normal(0, 1, n)).astype(np.float32)
    audio += 0.005 * np.sin(2 * np.pi * 220 * t)
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()


async def run_pcm(pcm: bytes, label: str) -> int:
    settings = reload_settings()
    logger = setup_logging(settings)
    stt = StreamingTranscriber(settings)
    t0 = now_monotonic()
    await stt.start()
    load_ms = round((now_monotonic() - t0) * 1000, 1)
    print(f"whisper loaded in {load_ms} ms ({settings.whisper_model})")

    stt.begin_utterance(turn_id="stt-smoke")
    # Feed in chunks to mimic streaming
    chunk = settings.frame_samples * 2
    for i in range(0, len(pcm), chunk * 10):
        stt.feed_audio(pcm[i : i + chunk * 10])
        partial = await stt.maybe_partial()
        if partial:
            print(f"  partial: {partial.text!r}")

    speech_end = now_monotonic()
    final = await stt.finalize(speech_end_ts=speech_end)
    latency = round((final.timestamp - speech_end) * 1000, 1)
    print(f"final ({label}): {final.text!r}")
    print(f"speech_end_to_final_ms={latency}")
    log_event(
        logger,
        "test_stt",
        text=final.text,
        latency_ms=latency,
        load_ms=load_ms,
    )
    await stt.stop()
    print("PASS (model decode ok)")
    return 0


async def run_mic(duration: float) -> int:
    settings = reload_settings()
    logger = setup_logging(settings)
    capture = AudioCapture(settings)
    stt = StreamingTranscriber(settings)
    await stt.start()
    stt.begin_utterance(turn_id="mic-stt")
    print(f"Speak for up to {duration}s…")
    await capture.start()
    start = time.monotonic()
    try:
        while time.monotonic() - start < duration:
            frame = await capture.queue.get()
            stt.feed_audio(frame.pcm)
    finally:
        await capture.stop()
    speech_end = now_monotonic()
    final = await stt.finalize(speech_end_ts=speech_end)
    print(f"final: {final.text!r}")
    print(f"latency_ms={round((final.timestamp - speech_end) * 1000, 1)}")
    log_event(logger, "test_stt_mic", text=final.text)
    await stt.stop()
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.wav:
        with wave.open(args.wav, "rb") as wf:
            assert wf.getframerate() == 16000
            pcm = wf.readframes(wf.getnframes())
        return asyncio.run(run_pcm(pcm, args.wav))
    if args.synthetic:
        return asyncio.run(run_pcm(_make_dummy_pcm(), "synthetic"))
    return asyncio.run(run_mic(args.duration))


if __name__ == "__main__":
    raise SystemExit(main())
