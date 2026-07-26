#!/usr/bin/env python3
"""State machine + barge-in smoke (no mic required)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.audio.playback import AudioPlayback
from jarvis.config import reload_settings
from jarvis.orchestrator.state import StateMachine
from jarvis.tts.piper import PiperTTS
from jarvis.types import PipelineState, SentenceChunk


def test_state_machine() -> None:
    sm = StateMachine(debug=True)
    assert sm.state == PipelineState.IDLE
    sm.transition(PipelineState.WAKE_DETECTED)
    sm.transition(PipelineState.LISTENING)
    sm.transition(PipelineState.TRANSCRIBING)
    sm.transition(PipelineState.THINKING)
    sm.transition(PipelineState.SPEAKING)
    sm.barge_in()
    assert sm.state == PipelineState.LISTENING
    print("state_machine PASS")


async def test_barge_in_playback() -> None:
    settings = reload_settings()
    tts = PiperTTS(settings)
    await tts.start()
    playback = AudioPlayback(settings)
    await playback.start()

    # Long-ish utterance
    chunks = await tts.synthesize_sentence(
        SentenceChunk(
            text="This is a longer sentence designed to keep playing while we interrupt.",
            index=0,
        )
    )
    for c in chunks:
        await playback.enqueue(c)

    await asyncio.sleep(0.4)
    assert playback.busy
    await playback.interrupt()
    await asyncio.sleep(0.2)
    assert not playback.playing
    assert not playback.busy
    await playback.stop()
    await tts.stop()
    print("barge_in_playback PASS")


def main() -> int:
    test_state_machine()
    asyncio.run(test_barge_in_playback())
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
