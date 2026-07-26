"""Silero VAD (ONNX) — stub for step 3."""

from __future__ import annotations

from jarvis.config import Settings


class SileroVAD:
    """Frame-level VAD emitting speech_start / speech_end.

    Implemented in build step 3.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def reset(self) -> None:
        raise NotImplementedError("SileroVAD.reset — implement in step 3")

    def process_frame(self, pcm: bytes) -> list[str]:
        """Return zero or more event kinds: speech_start, speech_end."""
        raise NotImplementedError("SileroVAD.process_frame — implement in step 3")
