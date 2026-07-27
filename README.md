# JARVIS v1
![Animated Demo](https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNWllaTRmZXoyMXljaWE1Nmtta2RzMG40N2dwcHduZWw4bDR2bWZ1cSZlcD12MV9naWZzX3JlbGF0ZWQmY3Q9Zw/rje8atJc3hnYQ/giphy.gif)


> *"Sometimes you gotta run before you can walk."* — Tony Stark
 
**A fully local, low-latency voice assistant built in a garage.**
*(Okay, a bedroom. But the spirit's the same.)*

## Origin Story
 
Every genius needs a voice in their ear — something that listens before you finish the sentence, thinks faster than you can doubt it, and talks back like it's got opinions of its own. Tony had a fictional AI running his mansion, his suits, and his sarcasm reserves. **JARVIS Mark I** is the real-world, open-source, no-billion-dollar-R&D-budget answer to that.
 
No cloud dependency holding your hand. No "let me think about that" spinner. Just wake word → listen → think → speak, stitched together with `asyncio` and stubbornness.


## The Arc Reactor (Architecture)
 
```
  Wake Word          →  openWakeWord
  Silence Detection   →  Silero VAD
  Speech → Text       →  faster-whisper (streaming)
  Reasoning           →  Groq API (blazing fast inference)
  Text → Speech       →  Piper TTS
  Orchestration       →  asyncio (the nervous system holding it all together)
```
 
Think of it less like a chatbot and more like a **reflex arc** — sound goes in one end, a spoken answer comes out the other, and every stage hands off to the next without blocking the pipeline. Latency isn't a nice-to-have here, it's the whole design philosophy.
 
---
 
## Suit Features
 
- **Hands-free activation** — say the wake word, JARVIS is listening
- **Real-time transcription** — streaming speech-to-text, no waiting for you to finish talking
- **Local-first** — your voice doesn't have to leave the building to be understood
- **Tool-calling** — Gmail, Discord, filesystem access, and a LinkedIn stub, because a good assistant should *do* things, not just talk about them
- **Fast responses** — Groq-backed reasoning means answers land before you finish your coffee sip
---
 
## Powering Up (Getting Started)
 
```bash
# Clone the suit blueprints
git clone git@github.com:awdtyo/Just-A-Rather-Very-Intelligent-System.git
cd Just-A-Rather-Very-Intelligent-System
 
# Suit up — install dependencies
pip install -r requirements.txt
 
# Configure your credentials
cp .env.template .env
# fill in your API keys — Groq, Google OAuth, etc.
```


## Hardware target

- Primary: Ubuntu laptop, Intel i5-1235U, 16 GB RAM, CPU-only
- Secondary (later): Raspberry Pi 5 — not used in Phase 1


### Models 

| Asset | Notes |
|-------|--------|
| Piper voice | Download `en_US-lessac-medium.onnx` + `.onnx.json` → `models/` |
| Wake word | Stock `jarvis` (uses `hey_jarvis` model) via openWakeWord (auto-fetched), or set `WAKE_MODEL` to a custom `.onnx` |
| Silero VAD | ONNX model cached on first use (or set `VAD_MODEL_PATH`) |
| Whisper | `base.en` downloaded by faster-whisper on first run |

## Run

```bash
python -m jarvis --show-config
python -m jarvis --debug-state                  # full mic pipeline
python -m jarvis --text "What time is it?"      # LLM→TTS dry run (no mic)
python -m jarvis --stage vad --synthetic
```


Barge-in: say the wake word to interrupt. VAD barge-in is **off by default** because laptop speaker echo was cutting replies mid-sentence; enable with headphones via `BARGE_IN_ON_VAD=true`.


## Defaults (overridable via `.env`)

| Knob | Default |
|------|---------|
| Groq model | `llama-3.1-8b-instant` |
| Whisper | `base.en` / `int8` / CPU |
| Piper voice | `models/en_US-lessac-medium.onnx` |
| Wake model | `jarvis` (uses `hey_jarvis` ONNX model) |
| History | last 6 turns |
| Audio | 16 kHz mono, 30 ms frames, sounddevice |

## Built By
 
**Aditya** — running this out of a home lab that includes a Raspberry Pi 5, a fleet of microcontrollers, and way too many terminal windows. If Tony had a college dorm instead of a mansion, it probably looked like this.
 
---
 
<div align="center">
*"I am Iron Man."*
*— well, not quite. But JARVIS is real, and it's listening.*
 
</div>
