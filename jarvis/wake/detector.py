"""openWakeWord always-on detector with asyncio event bridge."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import openwakeword
from openwakeword.model import Model

from jarvis.config import Settings
from jarvis.types import AudioFrame, WakeEvent, now_monotonic

logger = logging.getLogger("jarvis.wake")

# openWakeWord is most efficient on multiples of 80 ms @ 16 kHz.
WAKE_CHUNK_MS = 80
WAKE_CHUNK_SAMPLES = 16_000 * WAKE_CHUNK_MS // 1000  # 1280


def ensure_wake_models_downloaded() -> None:
    """Download feature + configured pretrained models if missing."""
    import openwakeword.utils as oww_utils

    oww_utils.download_models()


def resolve_wake_model_path(settings: Settings) -> str:
    """Resolve ``WAKE_MODEL`` (name or path) to an on-disk model file."""
    raw = settings.wake_model.strip()
    path = Path(raw)
    if path.suffix.lower() in {".onnx", ".tflite"}:
        resolved = settings.resolve_path(path) if not path.is_absolute() else path
        if not resolved.exists():
            raise FileNotFoundError(f"Wake model not found: {resolved}")
        return str(resolved)

    framework = settings.wake_inference_framework
    candidates = openwakeword.get_pretrained_model_paths(framework)
    needle = raw.lower().replace("-", "_")
    for candidate in candidates:
        stem = Path(candidate).stem.lower()  # e.g. hey_jarvis_v0.1
        if stem.startswith(needle) or needle in stem:
            if Path(candidate).exists():
                return candidate

    # Attempt download then retry
    ensure_wake_models_downloaded()
    candidates = openwakeword.get_pretrained_model_paths(framework)
    for candidate in candidates:
        stem = Path(candidate).stem.lower()
        if stem.startswith(needle) or needle in stem:
            if Path(candidate).exists():
                return candidate

    raise FileNotFoundError(
        f"No pretrained wake model matching '{raw}' for framework '{framework}'. "
        f"Tried: {candidates}"
    )


class WakeWordDetector:
    """Consumes AudioFrame stream, emits WakeEvent when score ≥ threshold.

    Runs openWakeWord ``predict`` in a worker thread so the event loop stays free.
    Includes a refractory cooldown after each detection to avoid burst re-triggers.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        audio_queue: asyncio.Queue[AudioFrame],
        event_queue: Optional[asyncio.Queue[WakeEvent]] = None,
        cooldown_s: float = 2.0,
    ) -> None:
        self.settings = settings
        self.audio_queue = audio_queue
        self.event_queue: asyncio.Queue[WakeEvent] = event_queue or asyncio.Queue(
            maxsize=8
        )
        self.cooldown_s = cooldown_s
        self._model: Optional[Model] = None
        self._model_path: Optional[str] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._pcm_buffer = bytearray()
        self._last_fire_ts = 0.0
        self._bytes_per_chunk = WAKE_CHUNK_SAMPLES * 2  # int16 mono

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._model_path = resolve_wake_model_path(self.settings)
        framework = self.settings.wake_inference_framework
        logger.info(
            "loading_wake_model path=%s framework=%s threshold=%.3f",
            self._model_path,
            framework,
            self.settings.wake_threshold,
        )
        self._model = await asyncio.to_thread(
            Model,
            wakeword_models=[self._model_path],
            inference_framework=framework,
        )
        self._running = True
        self._task = asyncio.create_task(self._run(), name="wake-detector")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._model = None
        self._pcm_buffer.clear()
        logger.info("wake_detector_stopped")

    async def _run(self) -> None:
        assert self._model is not None
        while self._running:
            frame = await self.audio_queue.get()
            self._pcm_buffer.extend(frame.pcm)
            while len(self._pcm_buffer) >= self._bytes_per_chunk:
                chunk = bytes(self._pcm_buffer[: self._bytes_per_chunk])
                del self._pcm_buffer[: self._bytes_per_chunk]
                await self._predict_chunk(chunk)

    async def _predict_chunk(self, pcm: bytes) -> None:
        assert self._model is not None
        audio = np.frombuffer(pcm, dtype=np.int16)
        prediction = await asyncio.to_thread(self._model.predict, audio)
        # prediction: dict[model_name, score]
        for model_name, score in prediction.items():
            score_f = float(score)
            if score_f < self.settings.wake_threshold:
                continue
            now = now_monotonic()
            if now - self._last_fire_ts < self.cooldown_s:
                logger.debug(
                    "wake_suppressed model=%s score=%.3f cooldown",
                    model_name,
                    score_f,
                )
                continue
            self._last_fire_ts = now
            event = WakeEvent(score=score_f, model=str(model_name), timestamp=now)
            logger.info(
                "wake_detected model=%s score=%.3f turn_id=%s",
                model_name,
                score_f,
                event.turn_id,
            )
            try:
                self.event_queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    _ = self.event_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                self.event_queue.put_nowait(event)
