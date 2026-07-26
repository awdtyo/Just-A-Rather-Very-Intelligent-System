"""Asyncio pipeline wiring all JARVIS stages."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from jarvis.audio.capture import AudioCapture
from jarvis.audio.playback import AudioPlayback
from jarvis.chunker.sentences import SentenceChunker
from jarvis.config import Settings
from jarvis.llm.groq_client import GroqBrain
from jarvis.logging_util import log_event, log_turn_latency, setup_logging
from jarvis.orchestrator.state import StateMachine
from jarvis.stt.whisper import StreamingTranscriber
from jarvis.tts.piper import PiperTTS
from jarvis.types import (
    PipelineState,
    SentenceChunk,
    TurnLatency,
    WakeEvent,
    now_monotonic,
)
from jarvis.vad.silero import SileroVAD
from jarvis.wake.detector import WakeWordDetector

logger = logging.getLogger("jarvis.orchestrator")


class Pipeline:
    """Capture → fanout → (wake | VAD/STT) → Groq → chunker → Piper → playback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = setup_logging(settings)
        self.state = StateMachine(debug=settings.debug_state_machine)

        self.raw_q: asyncio.Queue = asyncio.Queue(maxsize=settings.audio_queue_size)
        self.wake_q: asyncio.Queue = asyncio.Queue(maxsize=settings.audio_queue_size)
        self.speech_q: asyncio.Queue = asyncio.Queue(maxsize=settings.audio_queue_size)

        self.capture = AudioCapture(settings, queue=self.raw_q)
        self.wake = WakeWordDetector(settings, audio_queue=self.wake_q)
        self.vad = SileroVAD(settings)
        self.stt = StreamingTranscriber(settings)
        self.llm = GroqBrain(settings)
        self.chunker = SentenceChunker()
        self.tts = PiperTTS(settings)
        self.playback = AudioPlayback(settings)

        self._tasks: list[asyncio.Task] = []
        self._active_turn: Optional[TurnLatency] = None
        self._listen_gate = asyncio.Event()
        self._speak_gate = asyncio.Event()  # set while SPEAKING for VAD barge-in
        self._barge_requested = asyncio.Event()
        self._stop = asyncio.Event()
        self._utterance_task: Optional[asyncio.Task] = None
        self._speaking_since: Optional[float] = None
        self._barge_vad = SileroVAD(settings)
        self._barge_vad.threshold = settings.barge_in_vad_threshold
        # Re-derive frame hysteresis against the higher barge threshold context
        logger.info(
            "barge_vad_threshold=%.2f grace_ms=%s enabled=%s",
            self._barge_vad.threshold,
            settings.barge_in_grace_ms,
            settings.barge_in_on_vad,
        )

    async def run(self) -> None:
        log_event(self.logger, "pipeline_starting")
        await self.stt.start()
        await self.tts.start()
        await self.playback.start()
        await self.capture.start()
        await self.wake.start()
        self.playback.on_first_audio(self._on_first_audio)

        self._tasks = [
            asyncio.create_task(self._fanout_loop(), name="fanout"),
            asyncio.create_task(self._wake_loop(), name="wake-loop"),
            asyncio.create_task(self._barge_vad_loop(), name="barge-vad"),
        ]
        log_event(self.logger, "pipeline_running")
        print("JARVIS listening — say 'hey jarvis'. Ctrl+C to stop.", flush=True)
        try:
            await self._stop.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._stop.set()
        self._listen_gate.clear()
        if self._utterance_task and not self._utterance_task.done():
            self._utterance_task.cancel()
            await asyncio.gather(self._utterance_task, return_exceptions=True)
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.wake.stop()
        await self.capture.stop()
        await self.playback.stop()
        await self.tts.stop()
        await self.stt.stop()
        log_event(self.logger, "pipeline_stopped")

    def request_stop(self) -> None:
        self._stop.set()

    def _on_first_audio(self, ts: float) -> None:
        turn = self._active_turn
        if turn is not None and turn.first_audio_out_ts is None:
            turn.first_audio_out_ts = ts
            log_event(
                self.logger,
                "first_audio_out",
                turn_id=turn.turn_id,
                tts_to_audio_ms=turn.ms(turn.first_tts_chunk_ts, turn.first_audio_out_ts),
                time_to_first_audio_ms=turn.ms(turn.wake_ts, turn.first_audio_out_ts),
            )

    async def _fanout_loop(self) -> None:
        while not self._stop.is_set():
            frame = await self.raw_q.get()
            self._offer(self.wake_q, frame)
            # Speech path while listening for user OR while speaking (VAD barge-in)
            if self._listen_gate.is_set() or self._speak_gate.is_set():
                self._offer(self.speech_q, frame)

    @staticmethod
    def _offer(q: asyncio.Queue, item) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass

    async def _wake_loop(self) -> None:
        while not self._stop.is_set():
            event: WakeEvent = await self.wake.event_queue.get()
            if self.state.state in {PipelineState.SPEAKING, PipelineState.THINKING}:
                await self._handle_barge_in(wake=event)
                continue
            if self.state.state != PipelineState.IDLE:
                continue
            await self._begin_turn(event)

    async def _barge_vad_loop(self) -> None:
        """Interrupt playback when loud user speech is detected (optional)."""
        if not self.settings.barge_in_on_vad:
            await self._stop.wait()
            return

        while not self._stop.is_set():
            if not self._speak_gate.is_set():
                await asyncio.sleep(0.05)
                continue
            try:
                frame = await asyncio.wait_for(self.speech_q.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            # Only consume for barge while speaking; listening uses its own consumer
            if not self._speak_gate.is_set():
                # Put back if listening just took over — drop is fine under load
                continue
            if self._speaking_since is not None:
                grace = self.settings.barge_in_grace_ms / 1000.0
                if now_monotonic() - self._speaking_since < grace:
                    continue
            for ev in self._barge_vad.process_frame(frame.pcm):
                if ev.kind == "speech_start":
                    log_event(self.logger, "barge_in_vad", turn_id=ev.turn_id)
                    await self._handle_barge_in(wake=None)
                    break

    async def _begin_turn(self, event: WakeEvent) -> None:
        if self._utterance_task and not self._utterance_task.done():
            self._utterance_task.cancel()
            await asyncio.gather(self._utterance_task, return_exceptions=True)

        while True:
            try:
                self.speech_q.get_nowait()
            except asyncio.QueueEmpty:
                break

        turn = TurnLatency(turn_id=event.turn_id, wake_ts=event.timestamp)
        self._active_turn = turn
        self.vad.reset(turn_id=event.turn_id)
        self._barge_vad.reset(turn_id=event.turn_id)
        self.stt.begin_utterance(turn_id=event.turn_id)
        self.tts.clear_cancel()
        self.chunker.reset()
        self._barge_requested.clear()
        self._speak_gate.clear()

        if self.state.state == PipelineState.IDLE:
            self.state.transition(PipelineState.WAKE_DETECTED)
            self.state.transition(PipelineState.LISTENING)
        elif self.state.state == PipelineState.LISTENING:
            pass
        else:
            self.state.force_idle()
            self.state.transition(PipelineState.WAKE_DETECTED)
            self.state.transition(PipelineState.LISTENING)

        self._listen_gate.set()
        log_event(self.logger, "turn_begin", turn_id=event.turn_id, score=event.score)
        print(f"[{event.turn_id}] Listening…", flush=True)
        self._utterance_task = asyncio.create_task(
            self._handle_utterance(turn), name=f"utterance-{event.turn_id}"
        )

    async def _handle_barge_in(self, *, wake: Optional[WakeEvent]) -> None:
        if self._barge_requested.is_set():
            return
        turn_id = wake.turn_id if wake else (
            self._active_turn.turn_id if self._active_turn else "barge"
        )
        log_event(self.logger, "barge_in", turn_id=turn_id, via="wake" if wake else "vad")
        print("Barge-in — interrupting playback", flush=True)
        self._barge_requested.set()
        self._speak_gate.clear()
        await self.playback.interrupt()
        await self.tts.cancel()
        self._listen_gate.clear()
        if self._utterance_task and not self._utterance_task.done():
            self._utterance_task.cancel()
            await asyncio.gather(self._utterance_task, return_exceptions=True)
        self.state.barge_in()

        if wake is not None:
            await self._begin_turn(wake)
        else:
            # VAD barge-in: stay in LISTENING and start a fresh utterance capture
            fake = WakeEvent(
                score=1.0,
                model="vad_barge",
                turn_id=uuid.uuid4().hex[:12],
                timestamp=now_monotonic(),
            )
            await self._begin_turn(fake)

    async def _handle_utterance(self, turn: TurnLatency) -> None:
        try:
            speech_started = False
            while not self._barge_requested.is_set():
                try:
                    frame = await asyncio.wait_for(self.speech_q.get(), timeout=8.0)
                except asyncio.TimeoutError:
                    print(f"[{turn.turn_id}] Listen timeout — back to idle", flush=True)
                    break

                events = self.vad.process_frame(frame.pcm)
                for ev in events:
                    if ev.kind == "speech_start":
                        speech_started = True
                        turn.vad_start_ts = ev.timestamp
                        self.state.transition(PipelineState.TRANSCRIBING)
                        log_event(
                            self.logger,
                            "speech_start",
                            turn_id=turn.turn_id,
                            wake_to_vad_ms=turn.ms(turn.wake_ts, turn.vad_start_ts),
                        )
                        print(f"[{turn.turn_id}] Speech start", flush=True)
                    elif ev.kind == "speech_end":
                        turn.speech_end_ts = ev.timestamp
                        log_event(self.logger, "speech_end", turn_id=turn.turn_id)
                        print(f"[{turn.turn_id}] Speech end", flush=True)
                        self.stt.feed_audio(frame.pcm)
                        await self._after_speech_end(turn)
                        return

                if speech_started or self.vad.in_speech:
                    self.stt.feed_audio(frame.pcm)
                    partial = await self.stt.maybe_partial()
                    if partial and partial.text:
                        print(f"[{turn.turn_id}] partial: {partial.text}", flush=True)
        except asyncio.CancelledError:
            raise
        finally:
            self._listen_gate.clear()
            if self.state.state in {
                PipelineState.LISTENING,
                PipelineState.TRANSCRIBING,
                PipelineState.WAKE_DETECTED,
            }:
                self.state.force_idle()

    async def _after_speech_end(self, turn: TurnLatency) -> None:
        self._listen_gate.clear()
        final = await self.stt.finalize(speech_end_ts=turn.speech_end_ts)
        turn.stt_final_ts = final.timestamp
        log_event(
            self.logger,
            "stt_final",
            turn_id=turn.turn_id,
            text=final.text,
            speech_end_to_stt_ms=turn.ms(turn.speech_end_ts, turn.stt_final_ts),
        )
        print(f"[{turn.turn_id}] You: {final.text}", flush=True)

        if not final.text:
            self.state.transition(PipelineState.IDLE)
            return

        self.state.transition(PipelineState.THINKING)
        await self._think_and_speak(turn, final.text)

    async def _think_and_speak(self, turn: TurnLatency, user_text: str) -> None:
        self.chunker.reset()
        self.tts.clear_cancel()
        sentence_index = 0
        assistant_parts: list[str] = []

        try:
            first = True
            async for token in self.llm.stream_reply(user_text):
                if self._barge_requested.is_set():
                    return
                if first:
                    turn.first_llm_token_ts = now_monotonic()
                    first = False
                    log_event(
                        self.logger,
                        "first_llm_token",
                        turn_id=turn.turn_id,
                        stt_to_token_ms=turn.ms(
                            turn.stt_final_ts, turn.first_llm_token_ts
                        ),
                    )
                assistant_parts.append(token)
                for sentence in self.chunker.feed(token):
                    await self._speak_sentence(turn, sentence, sentence_index)
                    sentence_index += 1
            for sentence in self.chunker.flush():
                if self._barge_requested.is_set():
                    return
                await self._speak_sentence(turn, sentence, sentence_index)
                sentence_index += 1
        except Exception:
            logger.exception("think_and_speak_error")
            self.state.transition(PipelineState.IDLE)
            return

        if self._barge_requested.is_set():
            return

        await self.playback.wait_until_idle(timeout=60.0)
        self._speak_gate.clear()

        full = "".join(assistant_parts).strip()
        print(f"[{turn.turn_id}] JARVIS: {full}", flush=True)
        log_turn_latency(self.logger, turn)
        metrics = turn.as_dict()
        print(
            f"[{turn.turn_id}] time_to_first_audio_ms={metrics.get('time_to_first_audio_ms')}",
            flush=True,
        )
        self.state.transition(PipelineState.IDLE)

    async def _speak_sentence(self, turn: TurnLatency, text: str, index: int) -> None:
        if self._barge_requested.is_set():
            return
        if self.state.state != PipelineState.SPEAKING:
            self.state.transition(PipelineState.SPEAKING)
            self._speaking_since = now_monotonic()
            self._barge_vad.reset(turn_id=turn.turn_id)
            while True:
                try:
                    self.speech_q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._speak_gate.set()
        sentence = SentenceChunk(text=text, index=index, turn_id=turn.turn_id)
        chunks = await self.tts.synthesize_sentence(sentence)
        for chunk in chunks:
            if self._barge_requested.is_set():
                return
            if turn.first_tts_chunk_ts is None:
                turn.first_tts_chunk_ts = chunk.timestamp
                log_event(
                    self.logger,
                    "first_tts_chunk",
                    turn_id=turn.turn_id,
                    token_to_tts_ms=turn.ms(
                        turn.first_llm_token_ts, turn.first_tts_chunk_ts
                    ),
                )
            await self.playback.enqueue(chunk)
