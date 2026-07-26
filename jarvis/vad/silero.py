"""Silero VAD (ONNX) — speech_start / speech_end end-pointing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort

from jarvis.config import Settings
from jarvis.types import SpeechEvent, now_monotonic

logger = logging.getLogger("jarvis.vad")


def resolve_vad_model_path(settings: Settings) -> Path:
    if settings.vad_model_path is not None:
        path = settings.resolve_path(settings.vad_model_path)
        if not path.exists():
            raise FileNotFoundError(f"VAD model not found: {path}")
        return path

    try:
        import openwakeword

        oww_path = (
            Path(openwakeword.__file__).resolve().parent
            / "resources"
            / "models"
            / "silero_vad.onnx"
        )
        if oww_path.exists():
            return oww_path
    except Exception:
        pass

    raise FileNotFoundError(
        "silero_vad.onnx not found. Run: python -c "
        "\"import openwakeword.utils as u; u.download_models()\""
    )


class SileroVAD:
    """Frame-level VAD emitting speech_start / speech_end with hysteresis.

    Expects 16 kHz mono int16 PCM. Works best with ~30 ms frames (480 samples),
    matching Silero's recommended window.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sample_rate = settings.sample_rate
        self.threshold = settings.vad_threshold
        self.min_speech_frames = max(
            1, settings.vad_min_speech_ms // settings.frame_ms
        )
        self.min_silence_frames = max(
            1, settings.vad_min_silence_ms // settings.frame_ms
        )
        self.speech_pad_frames = max(0, settings.vad_speech_pad_ms // settings.frame_ms)

        model_path = resolve_vad_model_path(settings)
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._sr = np.array(self.sample_rate, dtype=np.int64)
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._turn_id: Optional[str] = None
        logger.info(
            "vad_loaded path=%s threshold=%.2f min_speech_ms=%s min_silence_ms=%s",
            model_path,
            self.threshold,
            settings.vad_min_speech_ms,
            settings.vad_min_silence_ms,
        )

    def reset(self, turn_id: Optional[str] = None) -> None:
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._turn_id = turn_id

    def set_turn(self, turn_id: str) -> None:
        self._turn_id = turn_id

    def score_frame(self, pcm: bytes) -> float:
        """Return speech probability for one PCM frame."""
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)
        ort_inputs = {
            "input": audio,
            "sr": self._sr,
            "h": self._h,
            "c": self._c,
        }
        out, self._h, self._c = self._session.run(None, ort_inputs)
        return float(out[0][0])

    def process_frame(self, pcm: bytes) -> list[SpeechEvent]:
        """Process one frame; return zero or more SpeechEvent objects."""
        return self.process_score(self.score_frame(pcm))

    def process_score(self, score: float) -> list[SpeechEvent]:
        """Advance end-pointing state from a raw speech probability."""
        events: list[SpeechEvent] = []
        ts = now_monotonic()

        if not self._in_speech:
            if score >= self.threshold:
                self._speech_frames += 1
                if self._speech_frames >= self.min_speech_frames:
                    self._in_speech = True
                    self._silence_frames = 0
                    events.append(
                        SpeechEvent(
                            kind="speech_start",
                            timestamp=ts,
                            turn_id=self._turn_id,
                        )
                    )
            else:
                self._speech_frames = 0
        else:
            if score < self.threshold:
                self._silence_frames += 1
                if self._silence_frames >= self.min_silence_frames:
                    self._in_speech = False
                    self._speech_frames = 0
                    self._silence_frames = 0
                    events.append(
                        SpeechEvent(
                            kind="speech_end",
                            timestamp=ts,
                            turn_id=self._turn_id,
                        )
                    )
            else:
                self._silence_frames = 0

        return events

    @property
    def in_speech(self) -> bool:
        return self._in_speech
