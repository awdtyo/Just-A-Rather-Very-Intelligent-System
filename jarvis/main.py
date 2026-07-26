"""CLI entrypoint for JARVIS v2."""

from __future__ import annotations

import argparse
import sys

from jarvis import __version__
from jarvis.config import get_settings, reload_settings
from jarvis.logging_util import log_event, setup_logging


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
        help="Enable live state-machine debug printing (step 10)",
    )
    parser.add_argument(
        "--stage",
        choices=["wake", "vad", "stt", "llm", "chunker", "tts", "full"],
        default="full",
        help="Run an isolated stage test (steps 2–7) or the full pipeline",
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
    # Paths as strings for readable dump
    for k, v in list(data.items()):
        if hasattr(v, "as_posix"):
            data[k] = str(v)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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

    if args.stage == "full":
        print(
            "Scaffold ready. Full pipeline lands in step 8.\n"
            "Next: implement step 2 (audio I/O + wake word).\n"
            "Try: python -m jarvis --show-config",
            file=sys.stderr,
        )
        return 0

    print(
        f"Stage '{args.stage}' isolation runner not wired yet "
        f"(see scripts/test_{args.stage}.py once implemented).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
