"""Asyncio pipeline wiring — stub for step 8."""

from __future__ import annotations

from jarvis.config import Settings


class Pipeline:
    """Central orchestrator connecting stages via asyncio.Queue.

    Implemented in build step 8.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self) -> None:
        raise NotImplementedError("Pipeline.run — implement in step 8")
