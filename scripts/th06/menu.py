"""Source-grounded physical navigation to Hard Reimu-A starts."""

from __future__ import annotations

import time

from .actuator import Keyboard
from .native import NativeProcess, read_menu_state


STATE_PRE_INPUT = 1
STATE_MAIN_MENU = 2
STATE_DIFFICULTY_SELECT = 7
STATE_CHARACTER_SELECT = 9
STATE_SHOT_SELECT = 11
STATE_PRACTICE_LVL_SELECT = 17


def _wait_state(process: NativeProcess, wanted: int, timeout: float) -> tuple[int, int, int]:
    deadline = time.monotonic() + timeout
    last = (-1, -1, -1)
    while time.monotonic() < deadline:
        last = read_menu_state(process)
        if last[0] == wanted:
            return last
        time.sleep(0.02)
    raise RuntimeError(f"menu state {wanted} not reached; last={last}")


def _wait_timer(process: NativeProcess, state: int, minimum: int, timeout: float = 3.0) -> tuple[int, int, int]:
    deadline = time.monotonic() + timeout
    last = (-1, -1, -1)
    while time.monotonic() < deadline:
        last = read_menu_state(process)
        if last[0] == state and last[2] >= minimum:
            return last
        time.sleep(0.02)
    raise RuntimeError(f"menu timer not ready for state {state}; last={last}")


def _set_cursor(
    process: NativeProcess,
    keyboard: Keyboard,
    state: int,
    target: int,
    length: int,
) -> None:
    for _ in range(length + 1):
        current_state, cursor, _timer = read_menu_state(process)
        if current_state != state:
            raise RuntimeError(f"menu left state {state} while selecting cursor")
        if cursor == target:
            return
        downward = (target - cursor) % length
        upward = (cursor - target) % length
        keyboard.tap("down" if downward <= upward else "up")
    raise RuntimeError(f"could not select cursor {target} in state {state}")


def _enter_main_menu(process: NativeProcess, keyboard: Keyboard) -> None:
    # Startup title -> main menu.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        state, _cursor, timer = read_menu_state(process)
        if state == STATE_MAIN_MENU:
            break
        if state == STATE_PRE_INPUT and timer >= 30:
            keyboard.tap("shoot")
        time.sleep(0.02)
    else:
        raise RuntimeError(f"main menu not reached; last={read_menu_state(process)}")

    _wait_timer(process, STATE_MAIN_MENU, 20)


def _select_hard_reimu_a(
    process: NativeProcess,
    keyboard: Keyboard,
    main_cursor: int,
) -> None:
    _set_cursor(process, keyboard, STATE_MAIN_MENU, target=main_cursor, length=8)
    keyboard.tap("shoot")

    _wait_state(process, STATE_DIFFICULTY_SELECT, timeout=4.0)
    _set_cursor(process, keyboard, STATE_DIFFICULTY_SELECT, target=2, length=4)
    keyboard.tap("shoot")

    _wait_timer(process, STATE_CHARACTER_SELECT, minimum=30, timeout=3.0)
    _set_cursor(process, keyboard, STATE_CHARACTER_SELECT, target=0, length=2)
    keyboard.tap("shoot")

    _wait_timer(process, STATE_SHOT_SELECT, minimum=30, timeout=3.0)
    _set_cursor(process, keyboard, STATE_SHOT_SELECT, target=0, length=2)
    keyboard.tap("shoot")


def _select_unlocked_practice_stage(
    process: NativeProcess,
    keyboard: Keyboard,
    stage: int,
) -> None:
    target = stage - 1
    seen: set[int] = set()
    for _ in range(7):
        state, cursor, _timer = read_menu_state(process)
        if state != STATE_PRACTICE_LVL_SELECT:
            raise RuntimeError("menu left Practice stage selection unexpectedly")
        if cursor == target:
            return
        if cursor in seen:
            raise RuntimeError(f"Practice stage {stage} is not unlocked")
        seen.add(cursor)
        keyboard.tap("down")
    raise RuntimeError(f"could not select Practice stage {stage}")


def start_hard_reimu_a(process: NativeProcess, keyboard: Keyboard) -> None:
    _enter_main_menu(process, keyboard)
    _select_hard_reimu_a(process, keyboard, main_cursor=0)
    time.sleep(1.0)


def start_hard_reimu_a_practice(
    process: NativeProcess,
    keyboard: Keyboard,
    stage: int,
) -> None:
    if not 1 <= stage <= 6:
        raise ValueError("Practice stage must be in 1..6")
    _enter_main_menu(process, keyboard)
    # MainMenu::DrawStartMenu cursor 2 sets isInPracticeMode before entering
    # the otherwise shared difficulty/character/shot selection path.
    _select_hard_reimu_a(process, keyboard, main_cursor=2)
    _wait_timer(process, STATE_PRACTICE_LVL_SELECT, minimum=30, timeout=4.0)
    _select_unlocked_practice_stage(process, keyboard, stage)
    keyboard.tap("shoot")
    time.sleep(1.0)
