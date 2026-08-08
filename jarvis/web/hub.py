"""In-process event hub bridging pipeline events to connected WebSocket clients.

The pipeline calls ``hub.publish(...)`` (sync, safe from the event loop thread)
and every connected browser receives the JSON payload. Each connection gets its
own queue + sender task so slow clients can't stall the pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("jarvis.web.hub")


@dataclass(eq=False)
class _Client:
    ws: Any
    queue: asyncio.Queue[str]


class EventHub:
    """Fan-out bus for pipeline → browser events."""

    def __init__(self) -> None:
        self._clients: set[_Client] = set()
        self._tasks: set[asyncio.Task] = set()
        # Snapshot sent to newly-connected clients so they don't start blank.
        self.state: Optional[str] = "IDLE"
        self.last_user: Optional[str] = None
        self.last_jarvis: Optional[str] = None

    def publish(self, event: str, **data: Any) -> None:
        """Broadcast an event to all connected clients (call from any async ctx)."""
        payload = json.dumps({"event": event, **data}, default=str)
        for client in list(self._clients):
            try:
                client.queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("web client queue full — dropping event %s", event)
        if event == "state":
            self.state = data.get("state")
        elif event == "user_text":
            self.last_user = data.get("text")
        elif event == "jarvis_text":
            self.last_jarvis = data.get("text")

    def _snapshot(self) -> str:
        return json.dumps(
            {
                "event": "snapshot",
                "state": self.state,
                "last_user": self.last_user,
                "last_jarvis": self.last_jarvis,
            },
            default=str,
        )

    async def connect(self, ws: Any) -> None:
        """Accept a WebSocket connection and start forwarding to it."""
        client = _Client(ws, asyncio.Queue(maxsize=200))
        self._clients.add(client)
        try:
            await ws.send_text(self._snapshot())
        except Exception:
            pass
        task = asyncio.create_task(self._sender(client))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.info("web client connected (%d total)", len(self._clients))

    async def disconnect(self, ws: Any) -> None:
        """Drop a disconnected client."""
        for client in list(self._clients):
            if client.ws is ws:
                self._clients.discard(client)
                logger.info("web client disconnected (%d total)", len(self._clients))
                return

    async def _sender(self, client: _Client) -> None:
        try:
            while True:
                payload = await client.queue.get()
                await client.ws.send_text(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("web client send failed", exc_info=True)
        finally:
            self._clients.discard(client)


hub = EventHub()
