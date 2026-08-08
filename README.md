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
# Say "Jarvis" — detections print with score + turn_id
```

### Models to place under `models/`

| Asset | Notes |
|-------|--------|
| Piper voice | Download `en_US-lessac-medium.onnx` + `.onnx.json` → `models/` |
| Wake word | Stock `jarvis` (uses `hey_jarvis` model) via openWakeWord (auto-fetched), or set `WAKE_MODEL` to a custom `.onnx` |
| Silero VAD | ONNX model cached on first use (or set `VAD_MODEL_PATH`) |
| Whisper | `base.en` downloaded by faster-whisper on first run |

### Google OAuth (Calendar + Gmail)

One-time browser auth: `PYTHONPATH=. python scripts/google_oauth_setup.py` — writes `data/google_token.json` (gitignored).

> **Important:** while your OAuth app is in **"Testing"** status, Google revokes refresh tokens after **7 days** and Gmail/Calendar tools start failing with `invalid_grant`. Fix it permanently by setting the app to **"In production"** (Google Cloud Console → OAuth consent screen), then re-auth once. Otherwise just re-run the setup script whenever the token dies; it now falls back to a fresh login instead of crashing.

## Run

```bash
python -m jarvis --show-config
python -m jarvis --debug-state                  # full mic pipeline
python -m jarvis --text "What time is it?"      # LLM→TTS dry run (no mic)
python -m jarvis --stage vad --synthetic
```

### Web UI

Serve a live dashboard (animated orb, state captions, weather, CPU/RAM/disk) while the pipeline runs:

```bash
python -m jarvis --web 8080     # full pipeline + web UI (open http://127.0.0.1:8080)
python -m jarvis.web --port 8080  # UI only (state mirror, no audio)
```

The orb animates by pipeline state: **listening** (green pulse) → **transcribing** (pink) → **thinking** (purple spin) → **speaking** (radiating rings + waveform). Live transcripts and latency events stream over WebSocket. Weather uses `wttr.in` (no API key) for `WEATHER_LOCATION` (default `Kolkata`).

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

Barge-in: say the wake word to interrupt. VAD barge-in is **off by default** because laptop speaker echo was cutting replies mid-sentence; enable with headphones via `BARGE_IN_ON_VAD=true`.

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
11. Profile/notes memory + anti-hallucination prompt ← done
12. Tool registry + confirm gate + orchestrator state ← done
13. Google OAuth + Calendar + Gmail tools ← done
14. WhatsApp Cloud API connector ← done
15. Instagram Graph connector ← done
16. LinkedIn connector (posts + draft-only DMs) ← done
17. Voice UX polish: draft readback before confirm ← done

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
| Wake model | `jarvis` (uses `hey_jarvis` ONNX model) |
| History | last 6 turns |
| Audio | 16 kHz mono, 30 ms frames, sounddevice |
