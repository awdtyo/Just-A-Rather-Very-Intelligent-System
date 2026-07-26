#!/usr/bin/env python3
"""Google tools smoke test — skipped if no token file present."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.config import reload_settings  # noqa: E402


def main() -> int:
    settings = reload_settings()
    token_path = settings.resolve_path(settings.google_token_path)

    if not token_path.exists():
        print(f"SKIP: no Google token at {token_path}")
        print("Run: PYTHONPATH=. python scripts/google_oauth_setup.py")
        return 0

    try:
        from jarvis.tools.calendar_google import build_calendar_tools
        from jarvis.tools.gmail import build_gmail_tools

        cal_tools = build_calendar_tools(
            token_path, settings.google_client_id, settings.google_client_secret
        )
        gmail_tools = build_gmail_tools(
            token_path, settings.google_client_id, settings.google_client_secret
        )

        print(f"Calendar tools: {[t.name for t in cal_tools]}")
        print(f"Gmail tools: {[t.name for t in gmail_tools]}")

        # Test schema generation
        for tool in cal_tools + gmail_tools:
            schema = tool.to_groq_schema()
            assert "function" in schema
            print(f"  {tool.name}: confirm={tool.requires_confirm}")

        print("google_tools PASS")
        return 0
    except ImportError as e:
        print(f"SKIP: missing google dependencies: {e}")
        print("Install with: pip install google-auth-oauthlib google-api-python-client")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
