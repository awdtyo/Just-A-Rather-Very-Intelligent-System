"""Shared pipeline types and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time
import uuid


def now_monotonic() -> float:
    """High-resolution monotonic clock for latency measurements."""
    return time.perf_counter()


class PipelineState(Enum):
    """Central orchestrator state machine."""

    IDLE = auto()
    WAKE_DETECTED = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    AWAITING_CONFIRM = auto()
    SPEAKING = auto()


@dataclass(slots=True)
class AudioFrame:
    """Raw PCM audio chunk (typically 30 ms)."""

    pcm: bytes
    sample_rate: int
    channels: int = 1
    timestamp: float = field(default_factory=now_monotonic)
    turn_id: Optional[str] = None


@dataclass(slots=True)
class WakeEvent:
    """Wake-word detection event."""

    score: float
    model: str
    timestamp: float = field(default_factory=now_monotonic)
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass(slots=True)
class SpeechEvent:
    """VAD speech boundary."""

    kind: str  # "speech_start" | "speech_end"
    timestamp: float = field(default_factory=now_monotonic)
    turn_id: Optional[str] = None


@dataclass(slots=True)
class TranscriptEvent:
    """STT hypothesis (partial or final)."""

    text: str
    is_final: bool
    timestamp: float = field(default_factory=now_monotonic)
    turn_id: Optional[str] = None
    speech_end_ts: Optional[float] = None


@dataclass(slots=True)
class TokenEvent:
    """Single LLM token (or small delta) from the streaming API."""

    text: str
    turn_id: Optional[str] = None
    timestamp: float = field(default_factory=now_monotonic)
    is_first: bool = False
    is_last: bool = False


@dataclass(slots=True)
class SentenceChunk:
    """Speakable clause emitted by the sentence chunker."""

    text: str
    index: int
    turn_id: Optional[str] = None
    timestamp: float = field(default_factory=now_monotonic)
    is_last: bool = False


@dataclass(slots=True)
class TTSAudioChunk:
    """Synthesized PCM ready for ordered playback."""

    pcm: bytes
    sample_rate: int
    sentence_index: int
    turn_id: Optional[str] = None
    timestamp: float = field(default_factory=now_monotonic)
    is_last_for_sentence: bool = True


@dataclass
class TurnLatency:
    """Per-turn latency markers (monotonic seconds). Filled as stages fire."""

    turn_id: str
    wake_ts: Optional[float] = None
    vad_start_ts: Optional[float] = None
    speech_end_ts: Optional[float] = None
    stt_final_ts: Optional[float] = None
    first_llm_token_ts: Optional[float] = None
    first_tts_chunk_ts: Optional[float] = None
    first_audio_out_ts: Optional[float] = None

    def ms(self, start: Optional[float], end: Optional[float]) -> Optional[float]:
        if start is None or end is None:
            return None
        return round((end - start) * 1000.0, 1)

    def as_dict(self) -> dict[str, object]:
        return {
            "turn_id": self.turn_id,
            "wake_to_vad_start_ms": self.ms(self.wake_ts, self.vad_start_ts),
            "speech_end_to_stt_final_ms": self.ms(self.speech_end_ts, self.stt_final_ts),
            "stt_final_to_first_llm_token_ms": self.ms(
                self.stt_final_ts, self.first_llm_token_ts
            ),
            "first_token_to_first_tts_chunk_ms": self.ms(
                self.first_llm_token_ts, self.first_tts_chunk_ts
            ),
            "first_tts_chunk_to_first_audio_out_ms": self.ms(
                self.first_tts_chunk_ts, self.first_audio_out_ts
            ),
            "time_to_first_audio_ms": self.ms(self.wake_ts, self.first_audio_out_ts),
        }
