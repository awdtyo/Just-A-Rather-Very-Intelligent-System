"""Piper TTS — per-sentence synthesis into ordered playback chunks."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from piper import PiperVoice, SynthesisConfig

from jarvis.config import Settings
from jarvis.types import SentenceChunk, TTSAudioChunk, now_monotonic

logger = logging.getLogger("jarvis.tts")


class PiperTTS:
    """Synthesize each sentence chunk and yield PCM for the playback queue."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._voice: Optional[PiperVoice] = None
        self._cancel = asyncio.Event()
        self._sample_rate = 22050

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def start(self) -> None:
        if self._voice is not None:
            return
        path = self.settings.piper_model_resolved
        if not path.exists():
            raise FileNotFoundError(
                f"Piper model not found: {path}. "
                "Download en_US-lessac-medium.onnx into models/."
            )
        logger.info("loading_piper path=%s", path)
        self._voice = await asyncio.to_thread(PiperVoice.load, path)
        self._sample_rate = int(self._voice.config.sample_rate)
        logger.info("piper_ready sample_rate=%s", self._sample_rate)

    async def stop(self) -> None:
        self._voice = None

    async def cancel(self) -> None:
        """Abort in-flight synthesis (barge-in)."""
        self._cancel.set()
        logger.info("piper_cancelled")

    def clear_cancel(self) -> None:
        self._cancel.clear()

    async def synthesize(self, text: str) -> bytes:
        """Synthesize full text to int16 PCM bytes."""
        chunks = [
            c
            async for c in self.synthesize_sentence(
                SentenceChunk(text=text, index=0, is_last=True)
            )
        ]
        return b"".join(c.pcm for c in chunks)

    async def synthesize_sentence(self, sentence: SentenceChunk) -> list[TTSAudioChunk]:
        if self._voice is None:
            raise RuntimeError("PiperTTS.start() not called")
        if self._cancel.is_set():
            return []

        syn = SynthesisConfig(
            speaker_id=self.settings.piper_speaker_id
            if self.settings.piper_speaker_id is not None
            else None,
            length_scale=self.settings.piper_length_scale,
        )

        def _run() -> list[TTSAudioChunk]:
            assert self._voice is not None
            out: list[TTSAudioChunk] = []
            for i, audio in enumerate(self._voice.synthesize(sentence.text, syn_config=syn)):
                if self._cancel.is_set():
                    break
                out.append(
                    TTSAudioChunk(
                        pcm=audio.audio_int16_bytes,
                        sample_rate=audio.sample_rate,
                        sentence_index=sentence.index,
                        turn_id=sentence.turn_id,
                        timestamp=now_monotonic(),
                        is_last_for_sentence=True,  # updated below
                    )
                )
            if out:
                for c in out[:-1]:
                    c.is_last_for_sentence = False
                out[-1].is_last_for_sentence = True
            return out

        result = await asyncio.to_thread(_run)
        if result:
            logger.info(
                "tts_sentence index=%s chars=%d pcm_bytes=%d",
                sentence.index,
                len(sentence.text),
                sum(len(c.pcm) for c in result),
            )
        return result
