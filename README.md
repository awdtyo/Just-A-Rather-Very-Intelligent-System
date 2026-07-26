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
# Prefer Python 3.11/3.12 (3.14 often lacks wheels for ctranslate2 / openwakeword)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# or: pip install -e .

cp .env.example .env
# edit .env — at minimum set GROQ_API_KEY when you reach the LLM stage
```

### Wake-word smoke test (step 2)

```bash
source venv/bin/activate
PYTHONPATH=. python scripts/test_wake.py --list-devices
PYTHONPATH=. python scripts/test_wake.py --duration 30
# Say "hey jarvis" — detections print with score + turn_id
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
python -m jarvis --show-config
python -m jarvis --debug-state                  # full mic pipeline
python -m jarvis --text "What time is it?"      # LLM→TTS dry run (no mic)
python -m jarvis --stage vad --synthetic
```

### Stage smoke tests

```bash
./scripts/smoke_all.sh   # all non-interactive smokes
# or individually:
PYTHONPATH=. python scripts/test_wake.py --duration 15
PYTHONPATH=. python scripts/test_vad.py --synthetic
PYTHONPATH=. python scripts/test_stt.py --synthetic
PYTHONPATH=. python scripts/test_llm.py
PYTHONPATH=. python scripts/test_chunker.py
PYTHONPATH=. python scripts/test_tts.py --no-play
PYTHONPATH=. python scripts/test_orchestrator.py
```

Barge-in works on wake word **or** loud speech while JARVIS is talking (`BARGE_IN_ON_VAD`). If speaker echo false-triggers, raise `BARGE_IN_VAD_THRESHOLD`, increase `BARGE_IN_GRACE_MS`, use headphones, or set `BARGE_IN_ON_VAD=false`.

## Build order

1. Scaffold + config ← done
2. Audio I/O + wake word ← done
3. Silero VAD gating ← done
4. Streaming faster-whisper ← done
5. Groq streaming LLM ← done
6. Sentence chunker ← done
7. Streaming Piper TTS ← done
8. Full asyncio orchestrator + state machine ← done
9. Barge-in ← done
10. End-to-end latency logging / live debug ← done

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
