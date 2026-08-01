"""Independent native dialogue sensing and physical Ctrl/Skip control."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .actuator import Keyboard
from .native import NativeProcess, read_dialogue_state


@dataclass(frozen=True)
class DialogueState:
    active: bool
    skippable: bool
    pulsed_shoot: bool


class DialogueSkipper:
    def __init__(self, process: NativeProcess, keyboard: Keyboard):
        self.process = process
        self.keyboard = keyboard
        self.last_shoot_pulse = 0.0

    def update(self, gameplay_context: bool) -> DialogueState:
        if gameplay_context:
            active, skippable = read_dialogue_state(self.process)
        else:
            active, skippable = False, False
        pulsed = False
        self.keyboard.set_auxiliary("skip", active and skippable)
        now = time.monotonic()
        if active and not skippable and now - self.last_shoot_pulse >= 0.25:
            # GuiImpl::RunMsg requires a new WAS_PRESSED(SHOOT) edge for an
            # unskippable WAIT. Z is normally held, so release/re-press it.
            self.keyboard.pulse("shoot")
            self.last_shoot_pulse = now
            pulsed = True
        state = DialogueState(active, skippable, pulsed)
        return state

    def release(self) -> None:
        self.keyboard.set_auxiliary("skip", False)
