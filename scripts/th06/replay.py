"""Source-grounded non-Practice ResultScreen replay saving."""

from __future__ import annotations

import struct
from collections import deque
from pathlib import Path

from .actuator import Keyboard
from .native import NativeProcess, ResultScreenState, read_result_screen, read_supervisor_state


SUPERVISOR_RESULT_STATES = frozenset((6, 7))
RESULT_EXITING = 2
RESULT_WRITING_HIGHSCORE_NAME = 9
RESULT_SAVE_REPLAY_QUESTION = 10
RESULT_CANT_SAVE_REPLAY = 11
RESULT_CHOOSING_REPLAY_FILE = 12
RESULT_WRITING_REPLAY_NAME = 13
RESULT_OVERWRITE_REPLAY_FILE = 14
RESULT_STATS_SCREEN = 15
RESULT_STATS_TO_SAVE_TRANSITION = 16
RESULT_EXIT = 17

KEYBOARD_COLUMNS = 16
KEYBOARD_CHARACTERS = 96
KEYBOARD_END = 95
ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ.,:;·@"
    "abcdefghijklmnopqrstuvwxyz+-/*=%0123456789(){}[]<>#!?'\"$      --"
)


def _move_character(index: int, key: str) -> int:
    while True:
        if key == "up":
            index = (index - KEYBOARD_COLUMNS) % KEYBOARD_CHARACTERS
        elif key == "down":
            index = (index + KEYBOARD_COLUMNS) % KEYBOARD_CHARACTERS
        elif key == "left":
            index = (index - 1) % KEYBOARD_CHARACTERS
            if index % KEYBOARD_COLUMNS == KEYBOARD_COLUMNS - 1:
                index = (index + KEYBOARD_COLUMNS) % KEYBOARD_CHARACTERS
        elif key == "right":
            index += 1
            if index % KEYBOARD_COLUMNS == 0:
                index -= KEYBOARD_COLUMNS
        else:
            raise ValueError(f"invalid result-keyboard direction: {key}")
        if ALPHABET[index] != " ":
            return index


def _next_character_key(start: int, target: int) -> str:
    if start == target:
        raise ValueError("result-keyboard cursor is already at target")
    queue = deque((start,))
    paths: dict[int, str] = {start: ""}
    while queue:
        current = queue.popleft()
        for key in ("left", "right", "up", "down"):
            nxt = _move_character(current, key)
            if nxt in paths:
                continue
            paths[nxt] = paths[current] + key[0]
            if nxt == target:
                first = paths[nxt][0]
                return {"l": "left", "r": "right", "u": "up", "d": "down"}[first]
            queue.append(nxt)
    raise RuntimeError(f"result-keyboard target {target} is unreachable")


def validate_replay_bytes(data: bytes) -> None:
    if len(data) < 0x50:
        raise RuntimeError("saved replay is shorter than ReplayData")
    if data[:4] != b"T6RP":
        raise RuntimeError("saved replay magic mismatch")
    if struct.unpack_from("<H", data, 4)[0] != 0x102:
        raise RuntimeError("saved replay version mismatch")
    decoded = bytearray(data)
    offset = decoded[0xE]
    for index in range(0xF, len(decoded)):
        decoded[index] = (decoded[index] - offset) & 0xFF
        offset = (offset + 7) & 0xFF
    expected = struct.unpack_from("<I", decoded, 0x8)[0]
    actual = (0x3F000318 + sum(decoded[0xE:])) & 0xFFFFFFFF
    if actual != expected:
        raise RuntimeError("saved replay checksum mismatch")


class ReplaySaver:
    def __init__(self, game_dir: Path, keyboard: Keyboard, name: str, slot: int | None):
        if not name or len(name) > 8 or any(character not in ALPHABET[:94] for character in name):
            raise ValueError("replay name must contain 1..8 supported non-space characters")
        replay_dir = game_dir / "replay"
        candidates = range(1, 16) if slot is None else (slot,)
        for candidate in candidates:
            path = replay_dir / f"th6_{candidate:02d}.rpy"
            if not path.exists():
                self.slot = candidate
                self.path = path
                break
        else:
            raise RuntimeError("no requested empty replay slot is available")
        self.keyboard = keyboard
        self.name = name
        self.seen_result = False
        self.completed = False

    def _set_linear_cursor(self, state: ResultScreenState, target: int, length: int) -> None:
        if state.cursor == target:
            self.keyboard.tap("shoot")
            return
        downward = (target - state.cursor) % length
        upward = (state.cursor - target) % length
        self.keyboard.tap("down" if downward <= upward else "up")

    def _write_name(self, state: ResultScreenState) -> None:
        if state.cursor < len(self.name):
            target = ALPHABET.index(self.name[state.cursor])
            if state.selected_character == target:
                self.keyboard.tap("shoot")
            else:
                self.keyboard.tap(_next_character_key(state.selected_character, target))
            return
        if state.selected_character == KEYBOARD_END:
            self.keyboard.tap("shoot")
        else:
            self.keyboard.tap(_next_character_key(state.selected_character, KEYBOARD_END))

    def update(self, process: NativeProcess) -> str:
        _wanted, current = read_supervisor_state(process)
        if current not in SUPERVISOR_RESULT_STATES:
            if self.seen_result and not self.completed:
                raise RuntimeError("ResultScreen exited before replay validation")
            return "inactive"
        self.seen_result = True
        self.keyboard.release_all()
        state = read_result_screen(process)
        if state is None:
            return "active"
        if self.path.exists():
            validate_replay_bytes(self.path.read_bytes())
            self.completed = True
            return "saved"
        if state.state == RESULT_WRITING_HIGHSCORE_NAME and state.frame_timer >= 30:
            self.keyboard.tap("menu")
        elif state.state == RESULT_STATS_SCREEN and state.frame_timer >= 90:
            self.keyboard.tap("shoot")
        elif state.state == RESULT_STATS_TO_SAVE_TRANSITION:
            pass
        elif state.state == RESULT_SAVE_REPLAY_QUESTION and state.frame_timer >= 80:
            self._set_linear_cursor(state, target=0, length=2)
        elif state.state == RESULT_CHOOSING_REPLAY_FILE and state.frame_timer >= 20:
            self._set_linear_cursor(state, target=self.slot - 1, length=15)
        elif state.state == RESULT_WRITING_REPLAY_NAME and state.frame_timer >= 30:
            self._write_name(state)
        elif state.state in (RESULT_CANT_SAVE_REPLAY, RESULT_OVERWRITE_REPLAY_FILE):
            raise RuntimeError(f"replay save refused in ResultScreen state {state.state}")
        elif state.state in (RESULT_EXITING, RESULT_EXIT):
            raise RuntimeError("ResultScreen exited without creating the replay")
        elif state.state not in (
            RESULT_WRITING_HIGHSCORE_NAME,
            RESULT_STATS_SCREEN,
            RESULT_STATS_TO_SAVE_TRANSITION,
            RESULT_SAVE_REPLAY_QUESTION,
            RESULT_CHOOSING_REPLAY_FILE,
            RESULT_WRITING_REPLAY_NAME,
        ):
            raise RuntimeError(f"unsupported ResultScreen state {state.state}")
        return "active"
