"""faster-whisper streaming / incremental transcription."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from jarvis.config import Settings
from jarvis.types import TranscriptEvent, now_monotonic

logger = logging.getLogger("jarvis.stt")


class StreamingTranscriber:
    """Buffers VAD-gated speech and decodes incrementally + on finalize.

    faster-whisper does not truly stream tokens mid-utterance on CPU with low
    latency, so we:
      1. Accept PCM chunks as they arrive (no wait for full utterance).
      2. Periodically emit partial hypotheses on a rolling buffer.
      3. On ``finalize()`` (VAD speech_end), run a final decode and emit that.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Optional[WhisperModel] = None
        self._pcm = bytearray()
        self._turn_id: Optional[str] = None
        self._speech_end_ts: Optional[float] = None
        self._partial_every_bytes = int(settings.sample_rate * 2 * 1.0)  # ~1s
        self._last_partial_at = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._model is not None:
            return
        logger.info(
            "loading_whisper model=%s compute=%s device=%s",
            self.settings.whisper_model,
            self.settings.whisper_compute_type,
            self.settings.whisper_device,
        )
        self._model = await asyncio.to_thread(
            WhisperModel,
            self.settings.whisper_model,
            device=self.settings.whisper_device,
            compute_type=self.settings.whisper_compute_type,
        )
        logger.info("whisper_ready")

    async def stop(self) -> None:
        self._model = None
        self._pcm.clear()

    def begin_utterance(self, turn_id: Optional[str] = None) -> None:
        self._pcm.clear()
        self._turn_id = turn_id
        self._speech_end_ts = None
        self._last_partial_at = 0

    def feed_audio(self, pcm: bytes) -> None:
        self._pcm.extend(pcm)

    async def maybe_partial(self) -> Optional[TranscriptEvent]:
        """Decode a partial hypothesis if enough new audio has arrived."""
        if self._model is None or len(self._pcm) < self._partial_every_bytes:
            return None
        if len(self._pcm) - self._last_partial_at < self._partial_every_bytes:
            return None
        self._last_partial_at = len(self._pcm)
        text = await self._transcribe(bytes(self._pcm))
        if not text:
            return None
        return TranscriptEvent(
            text=text,
            is_final=False,
            turn_id=self._turn_id,
        )

    async def finalize(self, speech_end_ts: Optional[float] = None) -> TranscriptEvent:
        """Final decode after VAD speech_end."""
        self._speech_end_ts = speech_end_ts or now_monotonic()
        text = await self._transcribe(bytes(self._pcm)) if self._pcm else ""
        event = TranscriptEvent(
            text=text.strip(),
            is_final=True,
            turn_id=self._turn_id,
            speech_end_ts=self._speech_end_ts,
        )
        latency_ms = None
        if event.speech_end_ts is not None:
            latency_ms = round((event.timestamp - event.speech_end_ts) * 1000.0, 1)
        logger.info(
            "stt_final text=%r latency_ms=%s turn_id=%s",
            event.text,
            latency_ms,
            self._turn_id,
        )
        self._pcm.clear()
        return event

    async def _transcribe(self, pcm: bytes) -> str:
        if self._model is None or not pcm:
            return ""
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        def _run() -> str:
            assert self._model is not None
            segments, _info = self._model.transcribe(
                audio,
                language=self.settings.whisper_language,
                beam_size=self.settings.whisper_beam_size,
                vad_filter=False,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

        async with self._lock:
            return await asyncio.to_thread(_run)
