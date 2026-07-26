#!/usr/bin/env python3
"""Isolated Silero VAD smoke test.

Usage:
  PYTHONPATH=. python scripts/test_vad.py --synthetic
  PYTHONPATH=. python scripts/test_vad.py --duration 15
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.audio.capture import AudioCapture
from jarvis.config import reload_settings
from jarvis.logging_util import log_event, setup_logging
from jarvis.vad.silero import SileroVAD


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test Silero VAD speech_start/end")
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument(
        "--synthetic",
        action="store_true",
        help="ONNX load + hysteresis state-machine smoke (no mic)",
    )
    p.add_argument("--threshold", type=float, default=None)
    return p


async def run_synthetic(args: argparse.Namespace) -> int:
    settings = reload_settings()
    if args.threshold is not None:
        settings.vad_threshold = args.threshold
    logger = setup_logging(settings)
    vad = SileroVAD(settings)
    vad.reset(turn_id="synth-test")

    # 1) ONNX scores silence low
    silence = np.zeros(settings.frame_samples, dtype=np.int16).tobytes()
    sil_score = vad.score_frame(silence)
    print(f"silence_score={sil_score:.4f}")
    if sil_score > 0.5:
        print("FAIL: silence scored as speech", file=sys.stderr)
        return 1

    # 2) Hysteresis: inject scores to verify speech_start / speech_end
    vad.reset(turn_id="synth-hysteresis")
    events: list[str] = []
    for _ in range(vad.min_speech_frames):
        for ev in vad.process_score(0.9):
            events.append(ev.kind)
    for _ in range(vad.min_silence_frames):
        for ev in vad.process_score(0.05):
            events.append(ev.kind)

    print(f"events={events}")
    log_event(logger, "test_vad_synthetic", events=events, silence_score=sil_score)
    if events != ["speech_start", "speech_end"]:
        print("FAIL: expected [speech_start, speech_end]", file=sys.stderr)
        return 1
    print("PASS")
    return 0


async def run_mic(args: argparse.Namespace) -> int:
    settings = reload_settings()
    if args.threshold is not None:
        settings.vad_threshold = args.threshold
    logger = setup_logging(settings)
    capture = AudioCapture(settings)
    vad = SileroVAD(settings)
    vad.reset(turn_id="mic-test")

    print(f"Listening {args.duration}s — speak, then pause.")
    await capture.start()
    start = time.monotonic()
    counts = {"speech_start": 0, "speech_end": 0}
    try:
        while time.monotonic() - start < args.duration:
            frame = await asyncio.wait_for(capture.queue.get(), timeout=1.0)
            for ev in vad.process_frame(frame.pcm):
                counts[ev.kind] = counts.get(ev.kind, 0) + 1
                print(f"  {ev.kind}")
                log_event(logger, "vad_event", kind=ev.kind)
    except (asyncio.TimeoutError, KeyboardInterrupt):
        pass
    finally:
        await capture.stop()
    print(f"Counts: {counts}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.synthetic:
        return asyncio.run(run_synthetic(args))
    return asyncio.run(run_mic(args))


if __name__ == "__main__":
    raise SystemExit(main())
