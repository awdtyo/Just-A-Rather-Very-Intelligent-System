"""Speaker playback with barge-in flush and gapless chunk streaming."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from jarvis.config import Settings
from jarvis.types import TTSAudioChunk, now_monotonic

logger = logging.getLogger("jarvis.audio.playback")

FirstAudioCallback = Callable[[float], None]


class AudioPlayback:
    """Ordered PCM playback with a persistent OutputStream (gapless sentences)."""

    def __init__(
        self,
        settings: Settings,
        *,
        queue: Optional[asyncio.Queue[Optional[TTSAudioChunk]]] = None,
    ) -> None:
        self.settings = settings
        self.queue: asyncio.Queue[Optional[TTSAudioChunk]] = queue or asyncio.Queue(
            maxsize=settings.playback_queue_size
        )
        self._task: Optional[asyncio.Task[None]] = None
        self._stream_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._interrupted = threading.Event()
        self._first_audio_cb: Optional[FirstAudioCallback] = None
        self._playing = False
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._sample_rate: Optional[int] = None
        self._buf = np.zeros(0, dtype=np.int16)
        self._lock = threading.Lock()

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def busy(self) -> bool:
        with self._lock:
            buf_size = self._buf.size
        return self._playing or self._inflight > 0 or not self.queue.empty() or buf_size > 0

    def on_first_audio(self, callback: FirstAudioCallback) -> None:
        self._first_audio_cb = callback

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._interrupted.clear()
        self._task = asyncio.create_task(self._pump(), name="audio-playback-pump")
        logger.info("playback_started")

    async def stop(self) -> None:
        self._running = False
        await self.interrupt()
        for t in (self._task, self._stream_task):
            if t is not None:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._stream_task = None
        logger.info("playback_stopped")

    async def enqueue(self, chunk: TTSAudioChunk) -> None:
        self._inflight += 1
        self._idle.clear()
        await self.queue.put(chunk)

    async def wait_until_idle(self, timeout: float = 60.0) -> None:
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            with self._lock:
                buf_size = self._buf.size
            logger.warning(
                "playback_wait_timeout inflight=%s buf=%s", self._inflight, buf_size
            )

    async def interrupt(self) -> None:
        """Flush queue/buffer and stop current playback (barge-in)."""
        self._interrupted.set()
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        with self._lock:
            self._buf = np.zeros(0, dtype=np.int16)
        self._playing = False
        self._inflight = 0
        self._idle.set()
        logger.info("playback_interrupted")

    def _append_pcm(self, pcm: np.ndarray) -> None:
        with self._lock:
            if self._buf.size == 0:
                self._buf = pcm
            else:
                self._buf = np.concatenate([self._buf, pcm])

    def _take_pcm(self, frames: int) -> np.ndarray:
        with self._lock:
            if self._buf.size == 0:
                return np.zeros(0, dtype=np.int16)
            n = min(frames, self._buf.size)
            out = self._buf[:n].copy()
            self._buf = self._buf[n:]
            return out

    def _buf_size(self) -> int:
        with self._lock:
            return int(self._buf.size)

    async def _pump(self) -> None:
        while self._running:
            # Allow new audio after a prior interrupt
            if self._interrupted.is_set() and self.queue.empty() and self._inflight == 0:
                await asyncio.sleep(0.05)
                continue
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                if (
                    self._inflight == 0
                    and self.queue.empty()
                    and self._buf_size() == 0
                    and not self._playing
                ):
                    self._idle.set()
                continue
            if item is None:
                continue
            try:
                pcm = np.frombuffer(item.pcm, dtype=np.int16).copy()
                if pcm.size == 0:
                    continue
                # New audio after barge-in clears the interrupt latch
                self._interrupted.clear()
                if self._sample_rate is None:
                    self._sample_rate = item.sample_rate
                self._append_pcm(pcm)
                self._idle.clear()
                if self._stream_task is None or self._stream_task.done():
                    self._stream_task = asyncio.create_task(
                        self._stream_loop(), name="audio-playback-stream"
                    )
            finally:
                if self._inflight > 0:
                    self._inflight -= 1

    async def _stream_loop(self) -> None:
        if self._sample_rate is None:
            return
        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        first_cb_fired = False
        underrun_streak = 0
        # ~1.2s of silence underrun tolerance while next sentence synthesizes
        max_underrun = 25

        def callback(outdata, frames, _time_info, _status) -> None:  # noqa: ANN001
            nonlocal first_cb_fired, underrun_streak
            if self._interrupted.is_set() or not self._running:
                outdata.fill(0)
                raise sd.CallbackStop()

            chunk = self._take_pcm(frames)
            if chunk.size == 0:
                outdata.fill(0)
                underrun_streak += 1
                if (
                    underrun_streak > max_underrun
                    and self._inflight == 0
                    and self.queue.empty()
                ):
                    raise sd.CallbackStop()
                return

            underrun_streak = 0
            outdata[: chunk.size, 0] = chunk
            if chunk.size < frames:
                outdata[chunk.size :] = 0
            if not first_cb_fired:
                first_cb_fired = True
                cb = self._first_audio_cb
                if cb is not None:
                    loop.call_soon_threadsafe(cb, now_monotonic())

        def finished_callback() -> None:
            loop.call_soon_threadsafe(done.set)

        self._playing = True
        self._idle.clear()
        stream: Optional[sd.OutputStream] = None
        try:
            stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=1024,
                device=self.settings.output_device
                if self.settings.output_device not in (None, "")
                else None,
                callback=callback,
                finished_callback=finished_callback,
            )
            stream.start()
            while not done.is_set() and not self._interrupted.is_set() and self._running:
                await asyncio.sleep(0.02)
        except Exception:
            logger.exception("playback_error")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            self._playing = False
            if self._inflight == 0 and self.queue.empty() and self._buf_size() == 0:
                self._idle.set()
