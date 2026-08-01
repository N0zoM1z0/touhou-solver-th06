from __future__ import annotations

from dataclasses import dataclass


BUTTON_SHOOT = 0x01
BUTTON_BOMB = 0x02
BUTTON_FOCUS = 0x04
BUTTON_UP = 0x10
BUTTON_DOWN = 0x20
BUTTON_LEFT = 0x40
BUTTON_RIGHT = 0x80

PLAYER_ALIVE = 0
PLAYER_SPAWNING = 1
PLAYER_DEAD = 2
PLAYER_INVULNERABLE = 3


@dataclass(frozen=True)
class Action:
    name: str
    dx: int
    dy: int


ACTIONS = (
    Action("stay", 0, 0),
    Action("up", 0, -1),
    Action("down", 0, 1),
    Action("left", -1, 0),
    Action("right", 1, 0),
    Action("up_left", -1, -1),
    Action("up_right", 1, -1),
    Action("down_left", -1, 1),
    Action("down_right", 1, 1),
)
ACTION_BY_VECTOR = {(action.dx, action.dy): action for action in ACTIONS}


@dataclass(frozen=True)
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    half_width: float
    half_height: float
    state: int
    ex_flags: int = 0
    acceleration: float = 0.0
    speed: float = 0.0
    turn_speed: float = 0.0
    acceleration_x: float = 0.0
    acceleration_y: float = 0.0


@dataclass(frozen=True)
class Laser:
    x: float
    y: float
    angle: float
    start_offset: float
    end_offset: float
    start_length: float
    width: float
    speed: float
    start_time: int
    hitbox_start_time: int
    duration: int
    despawn_duration: int
    hitbox_end_delay: int
    timer: int
    timer_float: float
    flags: int
    state: int


@dataclass(frozen=True)
class Snapshot:
    frame: int
    stage: int
    player_state: int
    x: float
    y: float
    half_width: float
    half_height: float
    normal_speed: float
    focus_speed: float
    normal_diagonal_speed: float
    focus_diagonal_speed: float
    frame_multiplier: float
    input_mask: int
    bullets: tuple[Bullet, ...]
    laser_count: int
    in_menu: bool
    time_stopped: bool
    replay_or_demo: bool
    lasers: tuple[Laser, ...] = ()


@dataclass(frozen=True)
class SafeAction:
    action: Action
    clearance: float
    final_x: float
    final_y: float


@dataclass(frozen=True)
class Decision:
    action: Action | None
    safe_actions: tuple[SafeAction, ...]
    clearance: float
    horizon: int
    reason: str
    effort_horizon: int = 0
    effort_safe_count: int = 0


def action_from_input(mask: int) -> Action:
    """Match Player::HandlePlayerInputs directional precedence."""
    dx = 0
    dy = 0
    if mask & BUTTON_UP:
        dy = -1
        if mask & BUTTON_LEFT:
            dx = -1
        if mask & BUTTON_RIGHT:
            dx = 1
    elif mask & BUTTON_DOWN:
        dy = 1
        if mask & BUTTON_LEFT:
            dx = -1
        if mask & BUTTON_RIGHT:
            dx = 1
    else:
        if mask & BUTTON_LEFT:
            dx = -1
        if mask & BUTTON_RIGHT:
            dx = 1
    return ACTION_BY_VECTOR[(dx, dy)]
