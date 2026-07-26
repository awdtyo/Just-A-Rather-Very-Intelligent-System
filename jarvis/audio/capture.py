"""Microphone capture (sounddevice) — stub for step 2."""

from __future__ import annotations

from jarvis.config import Settings


class AudioCapture:
    """Streams PCM frames from the default (or configured) input device.

    Implemented in build step 2.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start(self) -> None:
        raise NotImplementedError("AudioCapture.start — implement in step 2")

    async def stop(self) -> None:
        raise NotImplementedError("AudioCapture.stop — implement in step 2")
