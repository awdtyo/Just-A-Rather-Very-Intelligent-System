"""Piper TTS per-sentence synthesis — stub for step 7."""

from __future__ import annotations

from jarvis.config import Settings


class PiperTTS:
    """Synthesize each sentence chunk and push PCM to the playback queue.

    Implemented in build step 7.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start(self) -> None:
        raise NotImplementedError("PiperTTS.start — implement in step 7")

    async def stop(self) -> None:
        raise NotImplementedError("PiperTTS.stop — implement in step 7")

    async def synthesize(self, text: str) -> bytes:
        raise NotImplementedError("PiperTTS.synthesize — implement in step 7")

    async def cancel(self) -> None:
        """Abort in-flight synthesis (barge-in)."""
        raise NotImplementedError("PiperTTS.cancel — implement in step 9")
