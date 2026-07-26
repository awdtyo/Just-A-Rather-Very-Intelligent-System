#!/usr/bin/env python3
"""Standalone wake-word test: mic → openWakeWord → print detections.

Usage:
  source venv/bin/activate
  PYTHONPATH=. python scripts/test_wake.py
  PYTHONPATH=. python scripts/test_wake.py --list-devices
  PYTHONPATH=. python scripts/test_wake.py --duration 30 --threshold 0.5
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Allow running without editable install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.audio.capture import AudioCapture
from jarvis.config import reload_settings
from jarvis.logging_util import log_event, setup_logging
from jarvis.wake.detector import (
    WakeWordDetector,
    ensure_wake_models_downloaded,
    resolve_wake_model_path,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test openWakeWord detection from mic")
    p.add_argument("--duration", type=float, default=0.0, help="Seconds to listen (0=forever)")
    p.add_argument("--threshold", type=float, default=None, help="Override WAKE_THRESHOLD")
    p.add_argument("--model", type=str, default=None, help="Wake model name or .onnx path")
    p.add_argument("--list-devices", action="store_true", help="List input devices and exit")
    p.add_argument("--download-models", action="store_true", help="Force-download OWW models")
    p.add_argument("--cooldown", type=float, default=2.0, help="Seconds between detections")
    return p


async def run(args: argparse.Namespace) -> int:
    settings = reload_settings()
    if args.threshold is not None:
        settings.wake_threshold = args.threshold
    if args.model is not None:
        settings.wake_model = args.model

    logger = setup_logging(settings)

    if args.download_models:
        print("Downloading openWakeWord models…")
        await asyncio.to_thread(ensure_wake_models_downloaded)

    capture = AudioCapture(settings)
    if args.list_devices:
        for dev in capture.list_input_devices():
            print(f"  [{dev['index']}] {dev['name']}  "
                  f"(in={dev['channels']}, sr={dev['default_samplerate']})")
        return 0

    model_path = resolve_wake_model_path(settings)
    print(f"Wake model : {model_path}")
    print(f"Threshold  : {settings.wake_threshold}")
    print(f"Sample rate: {settings.sample_rate} Hz, frame={settings.frame_ms} ms")
    print("Say the wake word (default: 'hey jarvis'). Ctrl+C to stop.\n")

    detector = WakeWordDetector(
        settings,
        audio_queue=capture.queue,
        cooldown_s=args.cooldown,
    )

    await capture.start()
    await detector.start()
    log_event(logger, "test_wake_started", model=model_path, threshold=settings.wake_threshold)

    start = time.monotonic()
    count = 0
    try:
        while True:
            if args.duration > 0 and (time.monotonic() - start) >= args.duration:
                break
            try:
                event = await asyncio.wait_for(detector.event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            count += 1
            elapsed = time.monotonic() - start
            print(
                f"[{elapsed:7.2f}s] WAKE  model={event.model}  "
                f"score={event.score:.3f}  turn_id={event.turn_id}"
            )
            log_event(
                logger,
                "wake_detected",
                model=event.model,
                score=event.score,
                turn_id=event.turn_id,
                elapsed_s=round(elapsed, 3),
            )
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        await detector.stop()
        await capture.stop()
        print(f"\nDetections: {count}")
        log_event(logger, "test_wake_finished", detections=count)

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
