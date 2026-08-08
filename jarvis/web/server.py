"""FastAPI server for the JARVIS web UI.

Run standalone (state mirror only):
    PYTHONPATH=. python -m jarvis.web --port 8080

Or alongside the pipeline (recommended):
    python -m jarvis --web 8080
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from jarvis.config import Settings, get_settings
from jarvis.web.hub import hub

logger = logging.getLogger("jarvis.web")

STATIC_DIR = Path(__file__).resolve().parent / "static"

_weather_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="JARVIS Web UI")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/system")
    async def system() -> dict[str, Any]:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        cpu = psutil.cpu_percent(interval=0.4)
        freq = psutil.cpu_freq()
        return {
            "cpu_percent": round(cpu, 1),
            "cpu_count": psutil.cpu_count(),
            "cpu_freq_mhz": round(freq.current, 0) if freq else None,
            "ram": {
                "percent": round(mem.percent, 1),
                "used": mem.used,
                "total": mem.total,
            },
            "disk": {
                "percent": round(disk.percent, 1),
                "used": disk.used,
                "total": disk.total,
            },
        }

    @app.get("/api/weather")
    async def weather() -> dict[str, Any]:
        return await _fetch_weather(settings)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await hub.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await hub.disconnect(ws)

    return app


async def _fetch_weather(settings: Settings) -> dict[str, Any]:
    """Fetch + cache current weather from wttr.in (no API key needed)."""
    now = time.time()
    cached = _weather_cache.get("data")
    if cached and now - _weather_cache["ts"] < settings.weather_update_seconds:
        return cached

    location = settings.weather_location or "Kolkata"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.get(f"https://wttr.in/{location}?format=j1")
            resp.raise_for_status()
            data = resp.json()
        cur = data["current_condition"][0]
        area = data["nearest_area"][0]
        result = {
            "location": area["areaName"][0]["value"],
            "region": area.get("region", [{}])[0].get("value", ""),
            "country": area.get("country", [{}])[0].get("value", ""),
            "temp_c": float(cur.get("temp_C", 0)),
            "feels_like_c": float(cur.get("FeelsLikeC", 0)),
            "humidity": cur.get("humidity", ""),
            "wind_kph": cur.get("windspeedKmph", ""),
            "wind_dir": cur.get("winddir16Point", ""),
            "cloud": cur.get("cloudcover", ""),
            "desc": cur.get("weatherDesc", [{}])[0].get("value", ""),
            "icon": cur.get("weatherIconUrl", [{}])[0].get("value", ""),
        }
        _weather_cache["ts"] = now
        _weather_cache["data"] = result
        return result
    except Exception as e:
        logger.warning("weather fetch failed: %s", e)
        return {
            "error": str(e),
            "location": location,
            "desc": "Weather unavailable",
        }


async def start_web(port: int = 8080, settings: Optional[Settings] = None) -> None:
    """Run the uvicorn server (blocks until cancelled)."""
    from uvicorn import Config, Server

    app = create_app(settings)
    server = Server(
        Config(app, host="127.0.0.1", port=port, log_level="warning", ws="auto")
    )
    logger.info("web UI listening on http://127.0.0.1:%s", port)
    print(f"JARVIS web UI → http://127.0.0.1:{port}", flush=True)
    await server.serve()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the JARVIS web UI alone")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    from jarvis.config import reload_settings

    settings = reload_settings()

    import uvicorn

    app = create_app(settings)
    print(f"JARVIS web UI → http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
