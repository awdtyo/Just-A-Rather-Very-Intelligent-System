"""Pipeline state machine — stub for step 8."""

from __future__ import annotations

from jarvis.types import PipelineState


class StateMachine:
    """IDLE → WAKE_DETECTED → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE.

    Barge-in: SPEAKING → LISTENING.
    Implemented in build step 8.
    """

    def __init__(self) -> None:
        self.state = PipelineState.IDLE

    def transition(self, new_state: PipelineState) -> None:
        raise NotImplementedError("StateMachine.transition — implement in step 8")

    def barge_in(self) -> None:
        """Interrupt SPEAKING and return to LISTENING."""
        raise NotImplementedError("StateMachine.barge_in — implement in step 9")
