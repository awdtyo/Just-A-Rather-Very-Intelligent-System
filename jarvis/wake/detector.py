"""openWakeWord detector — stub for step 2."""

from __future__ import annotations

from jarvis.config import Settings


class WakeWordDetector:
    """Always-on wake-word listener (dedicated thread → asyncio bridge).

    Implemented in build step 2.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start(self) -> None:
        raise NotImplementedError("WakeWordDetector.start — implement in step 2")

    async def stop(self) -> None:
        raise NotImplementedError("WakeWordDetector.stop — implement in step 2")
