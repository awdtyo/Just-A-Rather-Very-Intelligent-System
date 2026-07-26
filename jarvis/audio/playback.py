"""Speaker playback with barge-in flush."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from jarvis.config import Settings
from jarvis.types import TTSAudioChunk, now_monotonic

logger = logging.getLogger("jarvis.audio.playback")

FirstAudioCallback = Callable[[float], None]


class AudioPlayback:
    """Ordered PCM playback queue with immediate interrupt support."""

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
        self._running = False
        self._interrupted = asyncio.Event()
        self._first_audio_cb: Optional[FirstAudioCallback] = None
        self._playing = False
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def busy(self) -> bool:
        return self._playing or self._inflight > 0 or not self.queue.empty()

    def on_first_audio(self, callback: FirstAudioCallback) -> None:
        self._first_audio_cb = callback

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._interrupted.clear()
        self._task = asyncio.create_task(self._run(), name="audio-playback")
        logger.info("playback_started")

    async def stop(self) -> None:
        self._running = False
        await self.interrupt()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("playback_stopped")

    async def enqueue(self, chunk: TTSAudioChunk) -> None:
        self._inflight += 1
        self._idle.clear()
        await self.queue.put(chunk)

    async def wait_until_idle(self, timeout: float = 60.0) -> None:
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("playback_wait_timeout inflight=%s", self._inflight)

    async def interrupt(self) -> None:
        """Flush queue and stop current playback (barge-in)."""
        self._interrupted.set()
        while True:
            try:
                self.queue.get_nowait()
                if self._inflight > 0:
                    self._inflight -= 1
            except asyncio.QueueEmpty:
                break
        self._playing = False
        self._inflight = 0
        self._idle.set()
        logger.info("playback_interrupted")

    async def _run(self) -> None:
        while self._running:
            self._interrupted.clear()
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            if item is None:
                continue
            try:
                await self._play_chunk(item)
            finally:
                if self._inflight > 0:
                    self._inflight -= 1
                if self._inflight == 0 and self.queue.empty() and not self._playing:
                    self._idle.set()

    async def _play_chunk(self, chunk: TTSAudioChunk) -> None:
        if self._interrupted.is_set():
            return
        remaining = np.frombuffer(chunk.pcm, dtype=np.int16).copy()
        if remaining.size == 0:
            return

        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        first_cb_fired = False
        state = {"pcm": remaining}

        def callback(outdata, frames, _time_info, _status) -> None:  # noqa: ANN001
            nonlocal first_cb_fired
            if self._interrupted.is_set():
                outdata.fill(0)
                raise sd.CallbackStop()
            pcm = state["pcm"]
            if pcm.size == 0:
                outdata.fill(0)
                raise sd.CallbackStop()
            n = min(frames, pcm.size)
            outdata[:n, 0] = pcm[:n]
            if n < frames:
                outdata[n:] = 0
            state["pcm"] = pcm[n:]
            if not first_cb_fired:
                first_cb_fired = True
                cb = self._first_audio_cb
                if cb is not None:
                    loop.call_soon_threadsafe(cb, now_monotonic())
            if state["pcm"].size == 0:
                raise sd.CallbackStop()

        def finished_callback() -> None:
            loop.call_soon_threadsafe(done.set)

        self._playing = True
        self._idle.clear()
        stream: Optional[sd.OutputStream] = None
        try:
            stream = sd.OutputStream(
                samplerate=chunk.sample_rate,
                channels=1,
                dtype="int16",
                device=self.settings.output_device
                if self.settings.output_device not in (None, "")
                else None,
                callback=callback,
                finished_callback=finished_callback,
            )
            stream.start()
            while not done.is_set() and not self._interrupted.is_set():
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
