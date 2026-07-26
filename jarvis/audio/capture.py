"""Microphone capture via sounddevice → asyncio.Queue of AudioFrame."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np
import sounddevice as sd

from jarvis.config import Settings
from jarvis.types import AudioFrame

logger = logging.getLogger("jarvis.audio.capture")


class AudioCapture:
    """Streams fixed-size PCM int16 frames from the mic into an asyncio queue.

    The PortAudio callback runs on a background thread and bridges into the
    event loop with ``call_soon_threadsafe``. When the queue is full, the oldest
    frame is dropped so wake-word listening never blocks the audio thread.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        queue: Optional[asyncio.Queue[AudioFrame]] = None,
        frame_ms: Optional[int] = None,
    ) -> None:
        self.settings = settings
        self.sample_rate = settings.sample_rate
        self.channels = settings.channels
        self.frame_ms = frame_ms if frame_ms is not None else settings.frame_ms
        self.frame_samples = int(self.sample_rate * self.frame_ms / 1000)
        self.queue: asyncio.Queue[AudioFrame] = queue or asyncio.Queue(
            maxsize=settings.audio_queue_size
        )
        self._stream: Optional[sd.InputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._dropped = 0

    @property
    def running(self) -> bool:
        return self._running

    def list_input_devices(self) -> list[dict[str, object]]:
        """Return host input devices (for CLI debugging)."""
        devices = sd.query_devices()
        result: list[dict[str, object]] = []
        for idx, dev in enumerate(devices):
            if int(dev["max_input_channels"]) > 0:
                result.append(
                    {
                        "index": idx,
                        "name": dev["name"],
                        "channels": int(dev["max_input_channels"]),
                        "default_samplerate": float(dev["default_samplerate"]),
                    }
                )
        return result

    async def start(self) -> None:
        if self._running:
            return
        self._loop = asyncio.get_running_loop()
        device = self.settings.input_device
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frame_samples,
            device=device if device is not None and device != "" else None,
            callback=self._on_audio,
        )
        self._stream.start()
        self._running = True
        logger.info(
            "capture_started sample_rate=%s frame_ms=%s device=%s",
            self.sample_rate,
            self.frame_ms,
            device if device is not None else "default",
        )

    async def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        logger.info("capture_stopped dropped_frames=%s", self._dropped)

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            logger.debug("capture_status %s", status)
        if not self._running or self._loop is None:
            return
        # indata shape: (frames, channels) int16
        pcm = bytes(indata.tobytes())
        frame = AudioFrame(
            pcm=pcm,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        self._loop.call_soon_threadsafe(self._enqueue, frame)

    def _enqueue(self, frame: AudioFrame) -> None:
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                _ = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.queue.put_nowait(frame)
            except asyncio.QueueFull:
                self._dropped += 1
                return
            self._dropped += 1
