#!/usr/bin/env bash
# Run all non-interactive smoke tests. Exit non-zero on first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source venv/bin/activate
export PYTHONPATH=.

echo "== VAD =="
python scripts/test_vad.py --synthetic
echo "== CHUNKER =="
python scripts/test_chunker.py
echo "== LLM =="
python scripts/test_llm.py
echo "== TTS =="
python scripts/test_tts.py --no-play
echo "== STT =="
python scripts/test_stt.py --synthetic
echo "== ORCHESTRATOR =="
python scripts/test_orchestrator.py
echo "== TEXT E2E =="
python -m jarvis --text "Reply with exactly: smoke ok."
echo
echo "ALL SMOKES PASSED"
