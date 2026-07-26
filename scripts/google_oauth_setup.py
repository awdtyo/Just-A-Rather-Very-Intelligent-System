#!/usr/bin/env python3
"""One-time Google OAuth setup for Calendar + Gmail access.

Run this script once to authenticate and cache the token:
    PYTHONPATH=. python scripts/google_oauth_setup.py

It opens a browser for consent, then writes data/google_token.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> int:
    from jarvis.config import reload_settings

    settings = reload_settings()

    if not settings.google_client_id or not settings.google_client_secret:
        print(
            "ERROR: Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.\n"
            "Create a Google Cloud project at https://console.cloud.google.com/\n"
            "Enable Calendar + Gmail APIs, then create OAuth 2.0 credentials.",
            file=sys.stderr,
        )
        return 1

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "ERROR: Missing google dependencies. Install them with:\n"
            "  pip install google-auth-oauthlib google-api-python-client",
            file=sys.stderr,
        )
        return 1

    token_path = settings.resolve_path(settings.google_token_path)

    # If token already exists, try to refresh it
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            print(f"Token refreshed: {token_path}")
            return 0
        print("Token is valid — no re-auth needed.")
        return 0

    # Build the OAuth consent screen URL
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    # Try local server first; fall back to console
    try:
        creds = flow.run_local_server(port=8080, open_browser=True)
    except Exception:
        print("Browser not available — using console flow.")
        creds = flow.run_console()

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"Token saved to {token_path}")
    print("You can now use Calendar and Gmail tools in JARVIS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
