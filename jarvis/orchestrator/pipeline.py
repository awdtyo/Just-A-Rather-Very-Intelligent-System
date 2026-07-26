"""Asyncio pipeline wiring all JARVIS stages."""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from typing import Any, Optional

from jarvis.audio.capture import AudioCapture
from jarvis.audio.playback import AudioPlayback
from jarvis.chunker.sentences import SentenceChunker
from jarvis.config import Settings
from jarvis.llm.groq_client import GroqBrain
from jarvis.logging_util import log_event, log_turn_latency, setup_logging
from jarvis.memory.profile import ProfileMemory
from jarvis.orchestrator.state import StateMachine
from jarvis.stt.whisper import StreamingTranscriber
from jarvis.tts.piper import PiperTTS
from jarvis.tools.base import ToolRegistry
from jarvis.tools.confirm import ConfirmStore, PendingAction
from jarvis.tools.memory_tools import build_memory_tools
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

        # Memory
        profile_path = settings.resolve_path(settings.profile_path)
        notes_dir = settings.resolve_path(settings.notes_dir)
        self.memory = ProfileMemory(profile_path, notes_dir)

        # Tool registry
        self.tool_registry = ToolRegistry()
        self.confirm_store = ConfirmStore()
        self._register_tools()

        # LLM with memory context + tools
        memory_context = self.memory.build_context_block()
        self.llm = GroqBrain(
            settings,
            memory_context=memory_context,
            tool_registry=self.tool_registry,
        )

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
        logger.info(
            "barge_vad_threshold=%.2f grace_ms=%s enabled=%s",
            self._barge_vad.threshold,
            settings.barge_in_grace_ms,
            settings.barge_in_on_vad,
        )

    def _register_tools(self) -> None:
        """Register all available tools."""
        # Memory tools (always available)
        for tool in build_memory_tools(self.memory):
            self.tool_registry.register(tool)

        # Web search tools (always available, no API key needed)
        from jarvis.tools.web_search import build_web_search_tools

        for tool in build_web_search_tools():
            self.tool_registry.register(tool)

        # Wikipedia tools (always available, no API key needed)
        from jarvis.tools.wikipedia import build_wikipedia_tools

        for tool in build_wikipedia_tools():
            self.tool_registry.register(tool)

        # System tools (always available)
        from jarvis.tools.system import build_system_tools

        for tool in build_system_tools():
            self.tool_registry.register(tool)

        # Google tools (only if OAuth token exists)
        token_path = self.settings.resolve_path(self.settings.google_token_path)
        if token_path.exists():
            try:
                from jarvis.tools.calendar_google import build_calendar_tools
                from jarvis.tools.gmail import build_gmail_tools

                for tool in build_calendar_tools(
                    token_path,
                    self.settings.google_client_id,
                    self.settings.google_client_secret,
                ):
                    self.tool_registry.register(tool)

                for tool in build_gmail_tools(
                    token_path,
                    self.settings.google_client_id,
                    self.settings.google_client_secret,
                ):
                    self.tool_registry.register(tool)

                logger.info("google tools registered (token found)")
            except Exception:
                logger.exception("failed to register google tools")
        else:
            logger.info("google tools skipped (no token at %s)", token_path)

        # WhatsApp Cloud API tools
        if self.settings.meta_wa_token and self.settings.meta_wa_phone_number_id:
            try:
                from jarvis.tools.whatsapp_meta import build_whatsapp_tools

                for tool in build_whatsapp_tools(
                    self.settings.meta_wa_token,
                    self.settings.meta_wa_phone_number_id,
                ):
                    self.tool_registry.register(tool)
                logger.info("whatsapp tools registered")
            except Exception:
                logger.exception("failed to register whatsapp tools")

        # Instagram Graph API tools
        if self.settings.meta_ig_token and self.settings.meta_ig_user_id:
            try:
                from jarvis.tools.instagram_meta import build_instagram_tools

                for tool in build_instagram_tools(
                    self.settings.meta_ig_token,
                    self.settings.meta_ig_user_id,
                ):
                    self.tool_registry.register(tool)
                logger.info("instagram tools registered")
            except Exception:
                logger.exception("failed to register instagram tools")

        # LinkedIn tools
        if self.settings.linkedin_access_token:
            try:
                from jarvis.tools.linkedin import build_linkedin_tools

                for tool in build_linkedin_tools(
                    self.settings.linkedin_access_token,
                ):
                    self.tool_registry.register(tool)
                logger.info("linkedin tools registered")
            except Exception:
                logger.exception("failed to register linkedin tools")

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
            asyncio.create_task(self._stdin_barge_loop(), name="stdin-barge"),
        ]
        log_event(self.logger, "pipeline_running")
        tools_desc = ", ".join(self.tool_registry.names) if not self.tool_registry.is_empty else "none"
        print(
            f"JARVIS listening — say 'hey jarvis'. Ctrl+C to stop. "
            f"Press Enter to interrupt during speech. "
            f"[tools: {tools_desc}]",
            flush=True,
        )
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
            if self.state.state == PipelineState.AWAITING_CONFIRM:
                # Wake word during confirm cancels the pending action
                self.confirm_store.clear()
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

    async def _stdin_barge_loop(self) -> None:
        """Press Enter to interrupt JARVIS mid-speech."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        while not self._stop.is_set():
            try:
                await reader.readline()
            except Exception:
                break
            if self.state.state in {PipelineState.SPEAKING, PipelineState.THINKING}:
                log_event(self.logger, "barge_in_stdin", turn_id=(
                    self._active_turn.turn_id if self._active_turn else "stdin"
                ))
                await self._handle_barge_in(wake=None)

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
        self.confirm_store.clear()
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
            # Use the tool-aware completion path
            text, tool_calls = await self.llm.complete_with_tools(user_text)

            if self._barge_requested.is_set():
                return

            # If there are tool calls, execute them
            if tool_calls:
                await self._execute_tools(turn, user_text, tool_calls, assistant_parts)
                return

            # Pure text reply — stream it through the chunker
            turn.first_llm_token_ts = now_monotonic()
            log_event(
                self.logger,
                "first_llm_token",
                turn_id=turn.turn_id,
                stt_to_token_ms=turn.ms(turn.stt_final_ts, turn.first_llm_token_ts),
            )

            # If complete_with_tools returned text directly (no tools), we need to
            # stream it through chunker. But since it's not streamed, feed it as one piece.
            for char in text:
                assistant_parts.append(char)

            for sentence in self.chunker.feed(text):
                if self._barge_requested.is_set():
                    return
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

    async def _execute_tools(
        self,
        turn: TurnLatency,
        user_text: str,
        tool_calls: list[dict[str, Any]],
        assistant_parts: list[str],
    ) -> None:
        """Execute tool calls, handling confirm gate as needed."""
        tool_results: list[dict[str, str]] = []

        for tc in tool_calls:
            tool = self.tool_registry.get(tc["name"])

            if tool and tool.requires_confirm and self.settings.require_send_confirm:
                # Enter confirm gate — read back the full draft before asking
                desc = self._describe_tool_call(tc["name"], tc["arguments"])
                self.confirm_store.store(PendingAction(
                    tool_name=tc["name"],
                    arguments=tc["arguments"],
                    description=desc,
                ))

                # Build a rich readback including the full content
                readback = self._build_confirm_readback(tc["name"], tc["arguments"])
                print(f"[{turn.turn_id}] JARVIS: {readback}", flush=True)
                turn.first_llm_token_ts = now_monotonic()
                await self._speak_text(turn, readback)
                self.state.transition(PipelineState.AWAITING_CONFIRM)
                return

            # Execute directly (no confirm needed)
            result = await self.tool_registry.execute(tc["name"], tc["arguments"])
            tool_results.append({"tool_call_id": tc["id"], "content": result})

        # Get the final reply incorporating tool results
        if tool_results:
            results_summary = "\n".join(
                f"- {tr['content']}" for tr in tool_results
            )
            final_text = await self.llm.complete_with_tool_results(
                f"[Tool results:\n{results_summary}\n]\nNow reply to the user based on these results.",
                tool_results,
            )
        else:
            # This shouldn't happen, but handle gracefully
            final_text = "I wasn't able to process that request."

        turn.first_llm_token_ts = now_monotonic()
        for char in final_text:
            assistant_parts.append(char)

        await self._speak_text(turn, final_text)

        if self._barge_requested.is_set():
            return

        await self.playback.wait_until_idle(timeout=60.0)
        self._speak_gate.clear()

        full = "".join(assistant_parts).strip()
        print(f"[{turn.turn_id}] JARVIS: {full}", flush=True)
        log_turn_latency(self.logger, turn)
        self.state.transition(PipelineState.IDLE)

    async def _handle_confirm_turn(self, turn: TurnLatency, user_text: str) -> None:
        """Handle a user response during AWAITING_CONFIRM state."""
        pending = self.confirm_store.pending
        if not pending:
            self.state.transition(PipelineState.IDLE)
            return

        result = self.confirm_store.check(user_text)
        if result is None:
            # Ambiguous — ask again
            ask = "Please say yes to confirm or no to cancel."
            await self._speak_text(turn, ask)
            return

        self.confirm_store.clear()

        if result == "cancel":
            self.state.transition(PipelineState.SPEAKING)
            await self._speak_text(turn, "Cancelled.")
            await self.playback.wait_until_idle(timeout=30.0)
            self._speak_gate.clear()
            self.state.transition(PipelineState.IDLE)
            return

        # Confirmed — execute the pending tool
        self.state.transition(PipelineState.THINKING)
        result_text = await self.tool_registry.execute(
            pending.tool_name, pending.arguments
        )

        # Get LLM to summarize the result
        full_reply = await self.llm.complete_with_tool_results(
            f"[Tool result: {result_text}]\nSummarize this result for the user briefly.",
            [{"tool_call_id": "confirm", "content": result_text}],
        )

        turn.first_llm_token_ts = now_monotonic()
        await self._speak_text(turn, full_reply)

        if self._barge_requested.is_set():
            return

        await self.playback.wait_until_idle(timeout=60.0)
        self._speak_gate.clear()
        print(f"[{turn.turn_id}] JARVIS: {full_reply}", flush=True)
        log_turn_latency(self.logger, turn)
        self.state.transition(PipelineState.IDLE)

    async def _speak_text(self, turn: TurnLatency, text: str) -> None:
        """Speak a complete text string through the chunker + TTS pipeline."""
        self.chunker.reset()
        sentence_index = 0
        for sentence in self.chunker.feed(text):
            if self._barge_requested.is_set():
                return
            await self._speak_sentence(turn, sentence, sentence_index)
            sentence_index += 1
        for sentence in self.chunker.flush():
            if self._barge_requested.is_set():
                return
            await self._speak_sentence(turn, sentence, sentence_index)
            sentence_index += 1

    def _describe_tool_call(self, name: str, args: dict) -> str:
        """Generate a human-readable description of a tool call for confirmation."""
        if name == "send_email":
            to = args.get("to", "someone")
            subject = args.get("subject", "no subject")
            return f"send an email to {to} with subject '{subject}'"
        if name == "create_calendar_event":
            summary = args.get("summary", "an event")
            start = args.get("start_time", "unknown time")
            return f"create calendar event '{summary}' at {start}"
        if name == "draft_email":
            to = args.get("to", "someone")
            subject = args.get("subject", "no subject")
            return f"draft an email to {to} with subject '{subject}'"
        if name == "send_whatsapp_message":
            to = args.get("to", "someone")
            text = args.get("text", "")[:50]
            return f"send WhatsApp to {to}: \"{text}\""
        if name == "reply_to_instagram_comment":
            comment_id = args.get("comment_id", "a comment")
            text = args.get("text", "")[:50]
            return f"reply to Instagram comment {comment_id}: \"{text}\""
        if name == "create_instagram_post":
            caption = args.get("caption", "")[:50]
            return f"publish Instagram post: \"{caption}\""
        if name == "create_linkedin_post":
            text = args.get("text", "")[:50]
            return f"publish LinkedIn post: \"{text}\""
        # Generic fallback
        return f"execute {name}"

    def _build_confirm_readback(self, name: str, args: dict) -> str:
        """Build a full readback of what will be sent, including content."""
        if name == "send_email":
            to = args.get("to", "someone")
            subject = args.get("subject", "")
            body = args.get("body", "")
            parts = [f"Here's the email to {to}."]
            if subject:
                parts.append(f"Subject: {subject}.")
            if body:
                parts.append(f"Body: {body}.")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        if name == "send_whatsapp_message":
            to = args.get("to", "someone")
            text = args.get("text", "")
            parts = [f"Here's the WhatsApp message to {to}."]
            if text:
                parts.append(f"Message: {text}.")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        if name == "reply_to_instagram_comment":
            text = args.get("text", "")
            parts = ["Here's the Instagram reply."]
            if text:
                parts.append(f"Reply: {text}.")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        if name == "create_instagram_post":
            caption = args.get("caption", "")
            parts = ["Here's the Instagram post."]
            if caption:
                parts.append(f"Caption: {caption}.")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        if name == "create_linkedin_post":
            text = args.get("text", "")
            parts = ["Here's the LinkedIn post."]
            if text:
                parts.append(f"Post: {text}.")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        if name == "create_calendar_event":
            summary = args.get("summary", "an event")
            start = args.get("start_time", "")
            end = args.get("end_time", "")
            parts = [f"Here's the calendar event: {summary}."]
            if start:
                parts.append(f"From {start}")
                if end:
                    parts.append(f"to {end}.")
                else:
                    parts.append(".")
            parts.append("Say send it to confirm, or cancel.")
            return " ".join(parts)

        # Generic fallback
        desc = self._describe_tool_call(name, args)
        return f"Sure — {desc}. Say send it to confirm, or cancel."

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
