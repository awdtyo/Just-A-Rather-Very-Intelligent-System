"""Speaker playback with barge-in flush — stub for steps 7/9."""

from __future__ import annotations

from jarvis.config import Settings


class AudioPlayback:
    """Ordered PCM playback queue with immediate interrupt support.

    Implemented in build steps 7 and 9.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start(self) -> None:
        raise NotImplementedError("AudioPlayback.start — implement in step 7")

    async def stop(self) -> None:
        raise NotImplementedError("AudioPlayback.stop — implement in step 7")

    async def enqueue(self, pcm: bytes, sample_rate: int) -> None:
        raise NotImplementedError("AudioPlayback.enqueue — implement in step 7")

    async def interrupt(self) -> None:
        """Flush queue and stop current playback (barge-in)."""
        raise NotImplementedError("AudioPlayback.interrupt — implement in step 9")
