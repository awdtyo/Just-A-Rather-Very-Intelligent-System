"""CLI entrypoint for JARVIS v2."""

from __future__ import annotations

import argparse
import asyncio
import runpy
import sys
from pathlib import Path

from jarvis import __version__
from jarvis.config import get_settings, reload_settings
from jarvis.logging_util import log_event, setup_logging

STAGE_SCRIPTS = {
    "wake": "test_wake.py",
    "vad": "test_vad.py",
    "stt": "test_stt.py",
    "llm": "test_llm.py",
    "chunker": "test_chunker.py",
    "tts": "test_tts.py",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="JARVIS v2 — low-latency streaming voice assistant",
    )
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print effective config (secrets redacted) and exit",
    )
    parser.add_argument(
        "--debug-state",
        action="store_true",
        help="Enable live state-machine debug printing",
    )
    parser.add_argument(
        "--stage",
        choices=["wake", "vad", "stt", "llm", "chunker", "tts", "full"],
        default="full",
        help="Run an isolated stage test or the full pipeline",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Full-pipeline dry run: skip mic/wake/STT and speak a reply to this text",
    )
    return parser


def _redacted_config() -> dict[str, object]:
    s = get_settings()
    data = s.model_dump()
    key = data.get("groq_api_key") or ""
    if isinstance(key, str) and key:
        data["groq_api_key"] = key[:4] + "…" + key[-4:] if len(key) > 8 else "***"
    else:
        data["groq_api_key"] = "(not set)"
    for k, v in list(data.items()):
        if hasattr(v, "as_posix"):
            data[k] = str(v)
    return data


def _run_stage_script(stage: str, stage_argv: list[str]) -> int:
    script = Path(__file__).resolve().parents[1] / "scripts" / STAGE_SCRIPTS[stage]
    sys.argv = [str(script), *stage_argv]
    runpy.run_path(str(script), run_name="__main__")
    return 0


async def _run_text_turn(user_text: str) -> int:
    """E2E smoke without mic: LLM → chunker → TTS → playback + latency logs."""
    from jarvis.orchestrator.pipeline import Pipeline
    from jarvis.types import PipelineState, TurnLatency, now_monotonic

    settings = get_settings()
    pipeline = Pipeline(settings)
    await pipeline.stt.start()  # warm even if unused
    await pipeline.tts.start()
    await pipeline.playback.start()
    pipeline.playback.on_first_audio(pipeline._on_first_audio)

    turn = TurnLatency(turn_id="text-smoke", wake_ts=now_monotonic())
    pipeline._active_turn = turn
    turn.vad_start_ts = turn.wake_ts
    turn.speech_end_ts = turn.wake_ts
    turn.stt_final_ts = now_monotonic()
    pipeline.state.transition(PipelineState.WAKE_DETECTED)
    pipeline.state.transition(PipelineState.LISTENING)
    pipeline.state.transition(PipelineState.TRANSCRIBING)
    pipeline.state.transition(PipelineState.THINKING)
    print(f"Text turn: {user_text!r}")
    await pipeline._think_and_speak(turn, user_text)
    await pipeline.playback.stop()
    await pipeline.tts.stop()
    await pipeline.stt.stop()
    return 0


async def _run_full() -> int:
    from jarvis.orchestrator.pipeline import Pipeline

    settings = get_settings()
    pipeline = Pipeline(settings)
    try:
        await pipeline.run()
    except KeyboardInterrupt:
        pipeline.request_stop()
        await pipeline.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, stage_argv = parser.parse_known_args(argv)

    reload_settings()
    settings = get_settings()
    if args.debug_state:
        settings.debug_state_machine = True

    logger = setup_logging(settings)

    if args.show_config:
        import json

        print(json.dumps(_redacted_config(), indent=2, default=str))
        return 0

    log_event(
        logger,
        "startup",
        version=__version__,
        stage=args.stage,
        sample_rate=settings.sample_rate,
        whisper_model=settings.whisper_model,
        groq_model=settings.groq_model,
        wake_model=settings.wake_model,
    )

    if args.stage in STAGE_SCRIPTS:
        # Default synthetic flags for non-interactive smoke when no extra args
        if args.stage == "vad" and not stage_argv:
            stage_argv = ["--synthetic"]
        if args.stage == "stt" and not stage_argv:
            stage_argv = ["--synthetic"]
        if args.stage == "tts" and "--no-play" not in stage_argv and not stage_argv:
            stage_argv = ["--no-play"]
        return _run_stage_script(args.stage, stage_argv)

    if args.text:
        return asyncio.run(_run_text_turn(args.text))

    return asyncio.run(_run_full())


if __name__ == "__main__":
    raise SystemExit(main())
