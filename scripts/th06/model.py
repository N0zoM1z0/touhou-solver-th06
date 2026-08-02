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
    focused: bool = True


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
FAST_ACTIONS = tuple(
    Action(f"{action.name}_fast", action.dx, action.dy, False)
    for action in ACTIONS
)
FAST_ACTION_BY_VECTOR = {
    (action.dx, action.dy): action for action in FAST_ACTIONS
}
CONTROL_ACTIONS = ACTIONS + FAST_ACTIONS


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
    angle: float = 0.0
    direction_rotation: float = 0.0
    timer: int = 0
    timer_float: float = 0.0
    acceleration_duration: int = 0
    direction_interval: int = 0
    direction_num_times: int = 0
    direction_max_times: int = 0
    curve_speed_acceleration: float = 0.0
    curve_angular_velocity: float = 0.0
    slot: int = -1


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
    slot: int = -1
    angular_velocity: float = 0.0
    motion_known: bool = False


@dataclass(frozen=True)
class EnemyBody:
    x: float
    y: float
    half_width: float
    half_height: float
    velocity_x: float
    velocity_y: float
    angle: float
    angular_velocity: float
    speed: float
    acceleration: float
    movement_mode: int
    movement_ease: int
    invert_x: bool
    move_interp_x: float
    move_interp_y: float
    move_start_x: float
    move_start_y: float
    move_timer: int
    move_timer_float: float
    move_start_time: int


@dataclass(frozen=True)
class BulletPattern:
    """Runtime-resolved EnemyBulletShooter plus its copied collision size."""

    sprite: int
    angle1: float
    angle2: float
    speed1: float
    speed2: float
    ex_floats: tuple[float, float, float, float]
    ex_ints: tuple[int, int, int, int]
    count1: int
    count2: int
    aim_mode: int
    flags: int
    half_width: float
    half_height: float


@dataclass(frozen=True)
class EclInstruction:
    address: int
    time: int
    opcode: int
    offset_to_next: int
    skip_for_difficulty: int
    raw_hex: str


@dataclass(frozen=True)
class EnemyEclContext:
    instruction_address: int
    time: int
    time_float: float
    ints: tuple[int, int, int, int, int, int, int, int]
    floats: tuple[float, float, float, float]
    compare: int
    repeat_ex_index: int | None


@dataclass(frozen=True)
class EnemySpawner:
    """An occupied enemy's observable periodic and ECL emission state."""

    slot: int
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    angle: float
    angular_velocity: float
    speed: float
    acceleration: float
    movement_mode: int
    movement_ease: int
    invert_x: bool
    move_interp_x: float
    move_interp_y: float
    move_start_x: float
    move_start_y: float
    move_timer: int
    move_timer_float: float
    move_start_time: int
    shoot_offset_x: float
    shoot_offset_y: float
    bullet_rank_speed_low: float
    bullet_rank_speed_high: float
    bullet_rank_amount1_low: int
    bullet_rank_amount1_high: int
    bullet_rank_amount2_low: int
    bullet_rank_amount2_high: int
    life: int
    shooting_disabled: bool
    interval: int
    timer: int
    timer_float: float
    pattern: BulletPattern | None
    ecl_time: int
    ecl_time_float: float
    ecl_ints: tuple[int, int, int, int, int, int, int, int]
    ecl_floats: tuple[float, float, float, float]
    ecl_compare: int
    repeat_ex_index: int | None
    next_instruction: EclInstruction | None
    ecl_program: tuple[EclInstruction, ...]
    ecl_stack: tuple[EnemyEclContext, ...] = ()
    hitbox_half_width: float = 0.0
    hitbox_half_height: float = 0.0
    interactable: bool = False
    collidable: bool = False
    invisible: bool = False


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
    enemies: tuple[EnemyBody, ...] = ()
    despawning_bullets: tuple[Bullet, ...] = ()
    bullet_read_retries: int = 0
    spawners: tuple[EnemySpawner, ...] = ()
    difficulty: int = 2
    rank: int = 0
    bullet_sizes: tuple[tuple[float, float], ...] = ()
    rng_seed: int = 0
    rng_generation: int = 0


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
    repairable_count: int = 0
    held_horizon: int = 0


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
    actions = ACTION_BY_VECTOR if mask & BUTTON_FOCUS else FAST_ACTION_BY_VECTOR
    return actions[(dx, dy)]
