# JARVIS v2

Low-latency local voice assistant. The design goal is **minimizing time-to-first-audio** via a streaming, overlapping asyncio pipeline — not just swapping models.

```
Mic → openWakeWord → Silero VAD → faster-whisper → Groq (stream)
    → sentence chunker → Piper TTS → speaker  (+ barge-in)
```

## Hardware target

- Primary: Ubuntu laptop, Intel i5-1235U, 16 GB RAM, CPU-only
- Secondary (later): Raspberry Pi 5 — not used in Phase 1

## Setup

```bash
cd "Jarvis Mark II"
source venv/bin/activate
pip install -r requirements.txt
# or: pip install -e .

cp .env.example .env
# edit .env — at minimum set GROQ_API_KEY
```

### Models to place under `models/`

| Asset | Notes |
|-------|--------|
| Piper voice | Download `en_US-lessac-medium.onnx` + `.onnx.json` → `models/` |
| Wake word | Stock `hey_jarvis` via openWakeWord (auto-fetched), or set `WAKE_MODEL` to a custom `.onnx` |
| Silero VAD | ONNX model cached on first use (or set `VAD_MODEL_PATH`) |
| Whisper | `base.en` downloaded by faster-whisper on first run |

## Run

```bash
python -m jarvis --show-config   # verify env loading
python -m jarvis                 # full pipeline (step 8+)
python -m jarvis --stage wake    # isolated stage runners (as implemented)
```

## Build order

1. Scaffold + config ← **you are here**
2. Audio I/O + wake word
3. Silero VAD gating
4. Streaming faster-whisper
5. Groq streaming LLM
6. Sentence chunker
7. Streaming Piper TTS
8. Full asyncio orchestrator + state machine
9. Barge-in
10. End-to-end latency logging / live debug

## Latency metrics (JSON lines → `logs/jarvis.jsonl`)

Per turn we log:

- wake → VAD start
- speech_end → STT final
- STT final → first LLM token
- first token → first TTS chunk
- first TTS chunk → first audio out
- **time_to_first_audio_ms** (headline metric)

## Defaults (overridable via `.env`)

| Knob | Default |
|------|---------|
| Groq model | `llama-3.1-8b-instant` |
| Whisper | `base.en` / `int8` / CPU |
| Piper voice | `models/en_US-lessac-medium.onnx` |
| Wake model | `hey_jarvis` |
| History | last 6 turns |
| Audio | 16 kHz mono, 30 ms frames, sounddevice |
