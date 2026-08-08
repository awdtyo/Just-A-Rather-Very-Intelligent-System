"""Allow `python -m jarvis.web` — run the web UI alone (state mirror only)."""

from jarvis.web.server import main

raise SystemExit(main())
