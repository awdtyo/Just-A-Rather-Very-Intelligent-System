"""faster-whisper streaming STT — stub for step 4."""

from __future__ import annotations

from jarvis.config import Settings


class StreamingTranscriber:
    """Incremental transcription fed by VAD-gated speech chunks.

    Implemented in build step 4.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start(self) -> None:
        raise NotImplementedError("StreamingTranscriber.start — implement in step 4")

    async def stop(self) -> None:
        raise NotImplementedError("StreamingTranscriber.stop — implement in step 4")

    def feed_audio(self, pcm: bytes) -> None:
        raise NotImplementedError("StreamingTranscriber.feed_audio — implement in step 4")

    async def finalize(self) -> str:
        raise NotImplementedError("StreamingTranscriber.finalize — implement in step 4")
