"""Pipeline state machine."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from jarvis.types import PipelineState

logger = logging.getLogger("jarvis.orchestrator.state")

# Legal transitions
_TRANSITIONS: dict[PipelineState, set[PipelineState]] = {
    PipelineState.IDLE: {PipelineState.WAKE_DETECTED},
    PipelineState.WAKE_DETECTED: {PipelineState.LISTENING, PipelineState.IDLE},
    PipelineState.LISTENING: {
        PipelineState.TRANSCRIBING,
        PipelineState.IDLE,
        PipelineState.SPEAKING,  # rare: still speaking while re-listen after barge-in
    },
    PipelineState.TRANSCRIBING: {
        PipelineState.THINKING,
        PipelineState.LISTENING,
        PipelineState.IDLE,
    },
    PipelineState.THINKING: {
        PipelineState.SPEAKING,
        PipelineState.IDLE,
        PipelineState.LISTENING,  # barge-in / cancel
    },
    PipelineState.SPEAKING: {
        PipelineState.IDLE,
        PipelineState.LISTENING,  # barge-in
        PipelineState.WAKE_DETECTED,
    },
}


class StateMachine:
    """IDLE → WAKE_DETECTED → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE.

    Barge-in: SPEAKING → LISTENING (also THINKING → LISTENING).
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        on_change: Optional[Callable[[PipelineState, PipelineState], None]] = None,
    ) -> None:
        self.state = PipelineState.IDLE
        self.debug = debug
        self._on_change = on_change

    def transition(self, new_state: PipelineState) -> None:
        if new_state == self.state:
            return
        allowed = _TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            logger.warning(
                "illegal_transition from=%s to=%s (forcing)",
                self.state.name,
                new_state.name,
            )
        old = self.state
        self.state = new_state
        logger.info("state %s → %s", old.name, new_state.name)
        if self.debug:
            print(f"[state] {old.name} → {new_state.name}", flush=True)
        if self._on_change is not None:
            self._on_change(old, new_state)

    def barge_in(self) -> None:
        """Interrupt SPEAKING/THINKING and return to LISTENING."""
        if self.state in {PipelineState.SPEAKING, PipelineState.THINKING}:
            self.transition(PipelineState.LISTENING)
        elif self.state == PipelineState.IDLE:
            self.transition(PipelineState.WAKE_DETECTED)
            self.transition(PipelineState.LISTENING)

    def force_idle(self) -> None:
        """Reset to IDLE from any state (timeouts / cleanup)."""
        if self.state != PipelineState.IDLE:
            old = self.state
            self.state = PipelineState.IDLE
            logger.info("state %s → IDLE (forced)", old.name)
            if self.debug:
                print(f"[state] {old.name} → IDLE (forced)", flush=True)
            if self._on_change is not None:
                self._on_change(old, PipelineState.IDLE)
