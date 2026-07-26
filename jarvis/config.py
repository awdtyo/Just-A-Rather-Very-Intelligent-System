"""Configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Central JARVIS config. Override any field via env or .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (Groq) ---
    groq_api_key: str = Field(default="", description="Groq API key (required for LLM)")
    groq_model: str = "llama-3.1-8b-instant"
    groq_max_tokens: int = 256
    groq_temperature: float = 0.6
    history_turns: int = 6
    system_prompt: str = (
        "You are JARVIS, a concise personal voice assistant. "
        "Speak briefly and clearly. Prefer short sentences suitable for spoken delivery. "
        "Do not use markdown, bullet lists, or stage directions. "
        "You have full internet and file access via tools. Use them proactively — never say you can't. "
        "YOU HAVE THESE EXACT TOOLS (never call anything else):\n"
        "web_search, web_news — internet search\n"
        "wiki_search, wiki_read — Wikipedia\n"
        "list_files, file_info, find_files — access the user's computer files\n"
        "system_info, battery_status, wifi_status, bluetooth_status — hardware status\n"
        "save_note, update_profile — memory\n"
        "Calendar/Gmail/WhatsApp/Instagram/LinkedIn — if configured\n"
        "RULES: "
        "1) NEVER call brave_search, web_browse, or any tool not listed above. "
        "2) When user asks about files, desktop, documents, or anything on their computer, call list_files immediately. "
        "3) When user asks about current events or facts, call web_search or wiki_search immediately. "
        "4) Never say you cannot access the internet or files — you can, using your tools."
    )

    # --- Audio I/O ---
    sample_rate: int = 16_000
    channels: int = 1
    frame_ms: int = 30
    input_device: Optional[int | str] = None
    output_device: Optional[int | str] = None

    # --- Wake word ---
    wake_model: str = "hey_jarvis"
    wake_threshold: float = 0.5
    wake_inference_framework: str = "onnx"

    # --- VAD ---
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 400
    vad_speech_pad_ms: int = 100
    vad_model_path: Optional[Path] = None

    # --- STT ---
    whisper_model: str = "base.en"
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"
    whisper_language: str = "en"
    whisper_beam_size: int = 1

    # --- TTS ---
    piper_model_path: Path = Path("models/en_US-lessac-medium.onnx")
    piper_speaker_id: int = 0
    piper_length_scale: float = 1.0

    # --- Pipeline queues ---
    audio_queue_size: int = 64
    token_queue_size: int = 256
    tts_sentence_queue_size: int = 8
    playback_queue_size: int = 32

    # --- Memory (profile + notes) ---
    profile_path: Path = Path("data/profile.yaml")
    notes_dir: Path = Path("data/notes")

    # --- Tools / confirm gate ---
    require_send_confirm: bool = True

    # --- Google (OAuth for Calendar + Gmail) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_token_path: Path = Path("data/google_token.json")

    # --- Meta (WhatsApp Cloud API + Instagram Graph API) ---
    meta_wa_token: str = ""
    meta_wa_phone_number_id: str = ""
    meta_ig_token: str = ""
    meta_ig_user_id: str = ""

    # --- LinkedIn ---
    linkedin_access_token: str = ""

    # --- Observability ---
    log_level: str = "INFO"
    log_json: bool = True
    log_dir: Path = Path("logs")
    debug_state_machine: bool = False
    # VAD barge-in is off by default: laptop speaker echo false-triggers mid-reply.
    # Interrupt with the wake word instead, or enable if using headphones.
    barge_in_on_vad: bool = False
    barge_in_vad_threshold: float = 0.9
    barge_in_grace_ms: int = 1500

    @field_validator(
        "piper_model_path", "log_dir", "vad_model_path",
        "profile_path", "notes_dir", "google_token_path",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return Path(value)
        return value

    @property
    def frame_samples(self) -> int:
        """Samples per audio frame at the configured sample rate."""
        return int(self.sample_rate * self.frame_ms / 1000)

    def resolve_path(self, path: Path) -> Path:
        """Resolve relative paths against the project root."""
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()

    @property
    def piper_model_resolved(self) -> Path:
        return self.resolve_path(self.piper_model_path)

    @property
    def log_dir_resolved(self) -> Path:
        return self.resolve_path(self.log_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton for the process."""
    return Settings()


def reload_settings() -> Settings:
    """Clear cache and reload (useful in tests / CLI)."""
    get_settings.cache_clear()
    return get_settings()
