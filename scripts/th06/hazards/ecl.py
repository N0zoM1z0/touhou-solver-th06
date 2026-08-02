"""Bounded, fail-closed ECL bullet-birth forecasting.

The forecaster interprets only source-audited emission instructions and the
small amount of control flow needed to reach them. Its coverage result is part
of the contract: callers must not treat frames after the first unsupported
instruction as modeled.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import math
import struct

from ..model import (
    Bullet,
    BulletPattern,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
)
from .births import UnsupportedBirthModel, spawn_pattern, spawn_pattern_envelope
from .enemies import finish_motion_values
from .rng import RngState


OPCODE_NOP = 0
OPCODE_JUMP = 2
OPCODE_JUMPDEC = 3
OPCODE_SET_INT = 4
OPCODE_SET_FLOAT = 5
OPCODE_SET_INT_RANDOM = 6
OPCODE_SET_INT_RANDOM_MIN = 7
OPCODE_SET_FLOAT_RANDOM = 8
OPCODE_SET_FLOAT_RANDOM_MIN = 9
OPCODE_SET_SELF_X = 10
OPCODE_SET_SELF_Y = 11
OPCODE_SET_SELF_Z = 12
OPCODE_MATH_INT_ADD = 13
OPCODE_MATH_INT_SUBTRACT = 14
OPCODE_MATH_INT_MULTIPLY = 15
OPCODE_MATH_INT_DIVIDE = 16
OPCODE_MATH_INT_MODULO = 17
OPCODE_MATH_INCREMENT = 18
OPCODE_MATH_DECREMENT = 19
OPCODE_MATH_FLOAT_ADD = 20
OPCODE_MATH_FLOAT_SUBTRACT = 21
OPCODE_MATH_FLOAT_MULTIPLY = 22
OPCODE_MATH_FLOAT_DIVIDE = 23
OPCODE_MATH_FLOAT_MODULO = 24
OPCODE_MATH_ATAN2 = 25
OPCODE_MATH_NORMALIZE_ANGLE = 26
OPCODE_COMPARE_INT = 27
OPCODE_COMPARE_FLOAT = 28
OPCODE_JUMP_LESS = 29
OPCODE_JUMP_LESS_EQUAL = 30
OPCODE_JUMP_EQUAL = 31
OPCODE_JUMP_GREATER = 32
OPCODE_JUMP_GREATER_EQUAL = 33
OPCODE_JUMP_NOT_EQUAL = 34
OPCODE_CALL = 35
OPCODE_RETURN = 36
OPCODE_CALL_LESS = 37
OPCODE_CALL_LESS_EQUAL = 38
OPCODE_CALL_EQUAL = 39
OPCODE_CALL_GREATER = 40
OPCODE_CALL_GREATER_EQUAL = 41
OPCODE_CALL_NOT_EQUAL = 42
OPCODE_MOVE_POSITION = 43
OPCODE_MOVE_AT_PLAYER = 51
OPCODE_MOVE_RANDOM = 49
OPCODE_MOVE_RANDOM_IN_BOUNDS = 50
OPCODE_MOVE_DIR_TIME_FIRST = 52
OPCODE_MOVE_POSITION_TIME_FIRST = 56
OPCODE_MOVE_TIME_FIRST = 61
OPCODE_MOVE_TIME_LAST = 64
OPCODE_MOVE_BOUNDS_SET = 65
OPCODE_MOVE_BOUNDS_DISABLE = 66
OPCODE_BULLET_FIRST = 67
OPCODE_BULLET_LAST = 75
OPCODE_SHOOT_INTERVAL = 76
OPCODE_SHOOT_INTERVAL_DELAYED = 77
OPCODE_SHOOT_DISABLED = 78
OPCODE_SHOOT_ENABLED = 79
OPCODE_SHOOT_NOW = 80
OPCODE_SHOOT_OFFSET = 81
OPCODE_BULLET_EFFECTS = 82
OPCODE_BULLET_CANCEL = 83
OPCODE_BULLET_SOUND = 84
OPCODE_LASER_CREATE = 85
OPCODE_LASER_CREATE_AIMED = 86
OPCODE_LASER_INDEX = 87
OPCODE_LASER_ROTATE = 88
OPCODE_LASER_ROTATE_FROM_PLAYER = 89
OPCODE_LASER_OFFSET = 90
OPCODE_LASER_TEST = 91
OPCODE_LASER_CANCEL = 92
OPCODE_SPELL_START = 93
OPCODE_SPELL_END = 94
OPCODE_ENEMY_CREATE = 95
OPCODE_ENEMY_KILL_ALL = 96
OPCODE_ANIMATION_MAIN = 97
OPCODE_ANIMATION_POSES = 98
OPCODE_ANIMATION_SLOT = 99
OPCODE_ANIMATION_DEATH = 100
OPCODE_BOSS_SET = 101
OPCODE_SPELL_EFFECT = 102
OPCODE_HITBOX_SET = 103
OPCODE_COLLIDABLE_FLAG = 104
OPCODE_DAMAGEABLE_FLAG = 105
OPCODE_EFFECT_SOUND = 106
OPCODE_DEATH_FLAG = 107
OPCODE_DEATH_CALLBACK = 108
OPCODE_INTERRUPT_SET = 109
OPCODE_INTERRUPT = 110
OPCODE_LIFE_SET = 111
OPCODE_BOSS_TIMER_SET = 112
OPCODE_LIFE_CALLBACK_THRESHOLD = 113
OPCODE_LIFE_CALLBACK_SUB = 114
OPCODE_TIMER_CALLBACK_THRESHOLD = 115
OPCODE_TIMER_CALLBACK_SUB = 116
OPCODE_EFFECT_PARTICLE = 118
OPCODE_INTERACTABLE_FLAG = 117
OPCODE_DROP_ITEMS = 119
OPCODE_ANIMATION_ROTATION = 120
OPCODE_EX_CALL = 121
OPCODE_EX_REPEAT = 122
OPCODE_TIME_SET = 123
OPCODE_DROP_ITEM_ID = 124
OPCODE_STAGE_UNPAUSE = 125
OPCODE_BOSS_LIFE_COUNT = 126
OPCODE_DEBUG_WATCH = 127
OPCODE_ANIMATION_INTERRUPT_MAIN = 128
OPCODE_ANIMATION_INTERRUPT_SLOT = 129
OPCODE_CALL_STACK_DISABLED = 130
OPCODE_BULLET_RANK_INFLUENCE = 131
OPCODE_INVISIBLE_FLAG = 132
OPCODE_BOSS_TIMER_CLEAR = 133
OPCODE_LASER_CLEAR_ALL = 134
OPCODE_SPELL_TIMEOUT_FLAG = 135
ECL_OPCODE_COUNT = 136
MAX_ABSTRACT_INTEGER_RNG_BRANCHES = 64
MAX_ABSTRACT_INTEGER_RNG_EVALUATIONS = 256

# Every source opcode has one deliberate authority classification.  The
# interpreter branches below implement MODELLED_ECL_OPCODES.  Hazard-neutral
# instructions may be ignored because they only change presentation, scoring,
# drops, or remove an already modelled hazard.  The remaining instructions
# stop coverage with a source-specific reason; none silently become safe.
HAZARD_NEUTRAL_ECL_OPCODES = frozenset({
    OPCODE_BULLET_CANCEL,
    OPCODE_BULLET_SOUND,
    OPCODE_SPELL_END,
    OPCODE_ANIMATION_MAIN,
    OPCODE_ANIMATION_POSES,
    OPCODE_ANIMATION_SLOT,
    OPCODE_ANIMATION_DEATH,
    OPCODE_BOSS_SET,
    OPCODE_SPELL_EFFECT,
    OPCODE_EFFECT_SOUND,
    OPCODE_DEATH_FLAG,
    OPCODE_INTERRUPT_SET,
    OPCODE_EFFECT_PARTICLE,
    OPCODE_ANIMATION_ROTATION,
    OPCODE_DROP_ITEM_ID,
    OPCODE_STAGE_UNPAUSE,
    OPCODE_BOSS_LIFE_COUNT,
    OPCODE_DEBUG_WATCH,
    OPCODE_ANIMATION_INTERRUPT_MAIN,
    OPCODE_ANIMATION_INTERRUPT_SLOT,
    OPCODE_LASER_CLEAR_ALL,
    OPCODE_SPELL_TIMEOUT_FLAG,
})

FAIL_CLOSED_ECL_OPCODES = {
    OPCODE_SET_SELF_Z: "SETVARSELFZ needs the uncaptured source z coordinate",
    OPCODE_LASER_CREATE: "future ECL laser creation is not yet represented",
    OPCODE_LASER_CREATE_AIMED: "future aimed ECL laser creation is not yet represented",
    OPCODE_LASER_INDEX: "future ECL laser store state is not captured",
    OPCODE_LASER_ROTATE: "future ECL laser mutation is not represented",
    OPCODE_LASER_ROTATE_FROM_PLAYER: "future aimed ECL laser mutation is not represented",
    OPCODE_LASER_OFFSET: "future ECL laser mutation is not represented",
    OPCODE_LASER_TEST: "future ECL laser liveness is not captured",
    OPCODE_LASER_CANCEL: "future ECL laser state mutation is not represented",
    OPCODE_ENEMY_CREATE: "future ECL enemy creation needs a world-emitter insertion",
    OPCODE_ENEMY_KILL_ALL: "ENEMYKILLALL can invoke another emitter callback",
    OPCODE_INTERRUPT: "ECL interrupt table is not captured",
    OPCODE_EX_CALL: "ECL external instruction can mutate world hazards",
}

MODELLED_ECL_OPCODES = frozenset(
    {OPCODE_NOP, 1, *range(OPCODE_JUMP, OPCODE_SET_SELF_Z),
     *range(OPCODE_MATH_INT_ADD, OPCODE_MOVE_BOUNDS_DISABLE + 1),
     *range(OPCODE_BULLET_FIRST, OPCODE_BULLET_EFFECTS + 1),
     OPCODE_SPELL_START, OPCODE_HITBOX_SET, OPCODE_COLLIDABLE_FLAG,
     OPCODE_DAMAGEABLE_FLAG,
     OPCODE_DEATH_CALLBACK,
     OPCODE_LIFE_SET, OPCODE_BOSS_TIMER_SET, OPCODE_TIMER_CALLBACK_THRESHOLD,
     OPCODE_TIMER_CALLBACK_SUB, OPCODE_LIFE_CALLBACK_THRESHOLD,
     OPCODE_LIFE_CALLBACK_SUB, OPCODE_INTERACTABLE_FLAG, OPCODE_DROP_ITEMS,
     OPCODE_EX_REPEAT, OPCODE_TIME_SET, OPCODE_CALL_STACK_DISABLED,
     OPCODE_BULLET_RANK_INFLUENCE, OPCODE_INVISIBLE_FLAG,
     OPCODE_BOSS_TIMER_CLEAR}
)

assert (
    MODELLED_ECL_OPCODES
    | HAZARD_NEUTRAL_ECL_OPCODES
    | FAIL_CLOSED_ECL_OPCODES.keys()
) == frozenset(range(ECL_OPCODE_COUNT))


@dataclass(frozen=True)
class EclForecast:
    births: tuple[tuple[Bullet, ...], ...]
    covered_frames: int
    reason: str = ""
    next_spawner: EnemySpawner | None = None
    body_hazards: tuple[tuple[tuple[float, float, float, float], ...], ...] = ()
    finished: bool = False
    unresolved_int_extent: int = 0


@dataclass(frozen=True)
class FloatInterval:
    low: float
    high: float


def _float_add(left: float | FloatInterval, right: float | FloatInterval) -> float | FloatInterval:
    if isinstance(left, FloatInterval) or isinstance(right, FloatInterval):
        left_low, left_high = (left.low, left.high) if isinstance(left, FloatInterval) else (left, left)
        right_low, right_high = (right.low, right.high) if isinstance(right, FloatInterval) else (right, right)
        return FloatInterval(left_low + right_low, left_high + right_high)
    return left + right


def _float_subtract(
    left: float | FloatInterval,
    right: float | FloatInterval,
) -> float | FloatInterval:
    if isinstance(left, FloatInterval) or isinstance(right, FloatInterval):
        left_low, left_high = (left.low, left.high) if isinstance(left, FloatInterval) else (left, left)
        right_low, right_high = (right.low, right.high) if isinstance(right, FloatInterval) else (right, right)
        return FloatInterval(left_low - right_high, left_high - right_low)
    return left - right


def _float_multiply(
    left: float | FloatInterval,
    right: float | FloatInterval,
) -> float | FloatInterval:
    if isinstance(left, FloatInterval) or isinstance(right, FloatInterval):
        left_low, left_high = (
            (left.low, left.high) if isinstance(left, FloatInterval) else (left, left)
        )
        right_low, right_high = (
            (right.low, right.high) if isinstance(right, FloatInterval) else (right, right)
        )
        products = (
            left_low * right_low,
            left_low * right_high,
            left_high * right_low,
            left_high * right_high,
        )
        return FloatInterval(min(products), max(products))
    return left * right


def _float_divide(
    left: float | FloatInterval,
    right: float | FloatInterval,
) -> float | FloatInterval:
    if not isinstance(left, FloatInterval) and not isinstance(right, FloatInterval):
        if right == 0.0:
            raise UnsupportedBirthModel("ECL float division by zero")
        return left / right
    right_low, right_high = (
        (right.low, right.high) if isinstance(right, FloatInterval) else (right, right)
    )
    if right_low <= 0.0 <= right_high:
        raise UnsupportedBirthModel("ECL float division interval contains zero")
    reciprocal = FloatInterval(1.0 / right_high, 1.0 / right_low)
    return _float_multiply(left, reciprocal)


def _maximum_magnitude(value: float | FloatInterval) -> float:
    if isinstance(value, FloatInterval):
        return max(abs(value.low), abs(value.high))
    return abs(value)


def _copy_spawner(spawner: EnemySpawner, **changes) -> EnemySpawner:
    """Clone forecast state without reflecting over the large dataclass."""
    clone = object.__new__(EnemySpawner)
    clone.__dict__.update(spawner.__dict__)
    clone.__dict__.update(changes)
    return clone


def _trunc_div(numerator: int, denominator: int) -> int:
    return int(numerator / denominator)


def _rank_int(low: int, high: int, rank: int) -> int:
    return _trunc_div(rank * (high - low), 32) + low


def _rank_float(low: float, high: float, rank: int) -> float:
    return rank * (high - low) / 32.0 + low


def _int_var(value: int, integers: list[int], difficulty: int, rank: int, life: int) -> int:
    if -10004 <= value <= -10001:
        return integers[-10001 - value]
    if -10012 <= value <= -10009:
        return integers[4 + (-10009 - value)]
    if value == -10013:
        return difficulty
    if value == -10014:
        return rank
    if value == -10024:
        return life
    return value


def _float_var(
    raw: bytes,
    integers: list[int],
    floats: list[float | FloatInterval],
    difficulty: int,
    rank: int,
    life: int,
    enemy: tuple[float, float],
    player: tuple[float, float] | None,
) -> float | FloatInterval:
    literal = struct.unpack("<f", raw)[0]
    value = int(literal) if math.isfinite(literal) else 0
    if -10008 <= value <= -10005:
        return floats[-10005 - value]
    if value == -10015:
        return enemy[0]
    if value == -10016:
        return enemy[1]
    if value == -10018:
        if player is None:
            raise UnsupportedBirthModel("ECL reads future player x")
        return player[0]
    if value == -10019:
        if player is None:
            raise UnsupportedBirthModel("ECL reads future player y")
        return player[1]
    if value == -10021:
        if player is None:
            return FloatInterval(-math.pi, math.pi)
        return math.atan2(player[1] - enemy[1], player[0] - enemy[0])
    if value == -10023:
        if player is None:
            raise UnsupportedBirthModel("ECL reads future player distance")
        return math.hypot(player[0] - enemy[0], player[1] - enemy[1])
    if value in range(-10024, -10000):
        resolved = _int_var(value, integers, difficulty, rank, life)
        return struct.unpack("<f", struct.pack("<i", resolved))[0]
    return literal


def _set_int_var(identifier: int, value: int, integers: list[int]) -> bool:
    if -10004 <= identifier <= -10001:
        integers[-10001 - identifier] = value
        return True
    if -10012 <= identifier <= -10009:
        integers[4 + (-10009 - identifier)] = value
        return True
    return False


def _set_float_var(
    identifier: int,
    value: float | FloatInterval,
    floats: list[float | FloatInterval],
) -> bool:
    if -10008 <= identifier <= -10005:
        floats[-10005 - identifier] = value
        return True
    return False


def _set_source_value(
    identifier: int,
    integers: list[int],
    floats: list[float | FloatInterval],
    difficulty: int,
    rank: int,
    life: int,
    boss_timer: int,
    enemy: tuple[float, float],
    player: tuple[float, float] | None,
) -> tuple[int | float | FloatInterval, bool]:
    """Resolve the raw 32-bit RHS used by source ``SetVar``.

    The boolean distinguishes a resolved float variable from integer/literal
    bits.  SETINT and SETFLOAT both call this same source function; their names
    do not constrain either operand's type.
    """
    if -10008 <= identifier <= -10005:
        return floats[-10005 - identifier], True
    if -10004 <= identifier <= -10001 or -10012 <= identifier <= -10009:
        return _int_var(identifier, integers, difficulty, rank, life), False
    if identifier == -10013:
        return difficulty, False
    if identifier == -10014:
        return rank, False
    if identifier == -10015:
        return enemy[0], True
    if identifier == -10016:
        return enemy[1], True
    if identifier in (-10017, -10020):
        raise UnsupportedBirthModel("SET reads an uncaptured z coordinate")
    if identifier == -10018:
        if player is None:
            raise UnsupportedBirthModel("SET reads future player x")
        return player[0], True
    if identifier == -10019:
        if player is None:
            raise UnsupportedBirthModel("SET reads future player y")
        return player[1], True
    if identifier == -10021:
        if player is None:
            return FloatInterval(-math.pi, math.pi), True
        return math.atan2(player[1] - enemy[1], player[0] - enemy[0]), True
    if identifier == -10022:
        return boss_timer, False
    if identifier == -10023:
        if player is None:
            raise UnsupportedBirthModel("SET reads future player distance")
        return math.hypot(player[0] - enemy[0], player[1] - enemy[1]), True
    if identifier == -10024:
        return life, False
    if identifier == -10025:
        raise UnsupportedBirthModel("SET reads the uncaptured player shot type")
    return identifier, False


def _set_local_from_source_bits(
    target: int,
    value: int | float | FloatInterval,
    source_is_float: bool,
    integers: list[int],
    floats: list[float | FloatInterval],
) -> bool:
    if -10008 <= target <= -10005:
        if source_is_float:
            return _set_float_var(target, value, floats)
        resolved = struct.unpack("<f", struct.pack("<i", value))[0]
        return _set_float_var(target, resolved, floats)
    if -10004 <= target <= -10001 or -10012 <= target <= -10009:
        if source_is_float:
            if isinstance(value, FloatInterval):
                raise UnsupportedBirthModel(
                    "SET cannot bit-copy an uncertain float into an integer"
                )
            value = struct.unpack("<i", struct.pack("<f", value))[0]
        return _set_int_var(target, value, integers)
    return False


def _resolved_pattern(
    instruction: EclInstruction,
    spawner: EnemySpawner,
    effect_floats: tuple[float, float, float, float],
    effect_ints: tuple[int, int, int, int],
    integers: list[int],
    floats: list[float | FloatInterval],
    difficulty: int,
    rank: int,
    life: int,
    enemy: tuple[float, float],
    player: tuple[float, float] | None,
    bullet_sizes: tuple[tuple[float, float], ...],
    radial_births: bool,
) -> BulletPattern:
    raw = bytes.fromhex(instruction.raw_hex)
    sprite = struct.unpack_from("<h", raw, 0x0C)[0]
    if not 0 <= sprite < len(bullet_sizes):
        raise UnsupportedBirthModel(f"ECL bullet sprite {sprite} has no size")
    half_width, half_height = bullet_sizes[sprite]
    if half_width <= 0.0 or half_height <= 0.0:
        raise UnsupportedBirthModel(f"ECL bullet sprite {sprite} is not loaded")
    count1_raw, count2_raw = struct.unpack_from("<ii", raw, 0x10)
    count1 = max(1, _int_var(count1_raw, integers, difficulty, rank, life) + _rank_int(
        spawner.bullet_rank_amount1_low,
        spawner.bullet_rank_amount1_high,
        rank,
    ))
    count2 = max(1, _int_var(count2_raw, integers, difficulty, rank, life) + _rank_int(
        spawner.bullet_rank_amount2_low,
        spawner.bullet_rank_amount2_high,
        rank,
    ))
    if count1 * count2 > 640:
        raise UnsupportedBirthModel("ECL bullet pattern exceeds the native pool")
    speed_rank = _rank_float(
        spawner.bullet_rank_speed_low,
        spawner.bullet_rank_speed_high,
        rank,
    )
    speed1 = _float_var(
        raw[0x18:0x1C], integers, floats, difficulty, rank, life, enemy, player
    )
    speed2_value = _float_var(
        raw[0x1C:0x20], integers, floats, difficulty, rank, life, enemy, player
    )
    if isinstance(speed1, FloatInterval) or isinstance(speed2_value, FloatInterval):
        if not radial_births:
            raise UnsupportedBirthModel("uncertain bullet speed needs a hard envelope")
        speed1 = max(0.3, _maximum_magnitude(_float_add(speed1, speed_rank)))
        speed2 = max(
            0.3,
            _maximum_magnitude(_float_add(speed2_value, speed_rank / 2.0)),
        )
    else:
        if not math.isfinite(speed1) or not math.isfinite(speed2_value):
            raise UnsupportedBirthModel("non-finite bullet speed")
        if speed1 != 0.0:
            speed1 = max(0.3, speed1 + speed_rank)
        speed2 = max(0.3, speed2_value + speed_rank / 2.0)
    angle1 = _float_var(
        raw[0x20:0x24], integers, floats, difficulty, rank, life, enemy, player
    )
    angle2 = _float_var(
        raw[0x24:0x28], integers, floats, difficulty, rank, life, enemy, player
    )
    if isinstance(angle1, FloatInterval) or isinstance(angle2, FloatInterval):
        if not radial_births:
            raise UnsupportedBirthModel("uncertain bullet angle needs a hard envelope")
        angle1 = angle2 = 0.0
    elif not math.isfinite(angle1) or not math.isfinite(angle2):
        raise UnsupportedBirthModel("non-finite bullet angle")
    angle1 = math.remainder(angle1, math.tau)
    flags = struct.unpack_from("<I", raw, 0x28)[0]
    return BulletPattern(
        sprite,
        angle1,
        angle2,
        speed1,
        speed2,
        effect_floats,
        effect_ints,
        count1,
        count2,
        instruction.opcode - OPCODE_BULLET_FIRST,
        flags,
        half_width,
        half_height,
    )


def _forecast_ecl_births_single(
    spawner: EnemySpawner,
    player_positions: tuple[tuple[float, float], ...],
    difficulty: int,
    rank: int,
    bullet_sizes: tuple[tuple[float, float], ...],
    frame_multiplier: float = 1.0,
    rng: RngState | None = None,
    allow_player_variables: bool = True,
    radial_births: bool = False,
    abstract_rng: bool = False,
    enemy_kill_all_is_noop: bool = False,
    abstract_int_choices: tuple[int, ...] = (),
) -> EclForecast:
    """Forecast one emitter until the first unsupported source instruction."""
    horizon = len(player_positions)
    births: list[list[Bullet]] = [[] for _ in player_positions]
    body_hazards: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    if not spawner.ecl_program or spawner.next_instruction is None:
        return EclForecast(tuple(map(tuple, births)), 0, "missing ECL instruction graph")
    if spawner.repeat_ex_index is not None:
        return EclForecast(tuple(map(tuple, births)), 0, "unsupported repeating ECL callback")
    program = {instruction.address: instruction for instruction in spawner.ecl_program}
    instruction_address = spawner.next_instruction.address
    current_time = spawner.ecl_time
    time_subframe = spawner.ecl_time_float - spawner.ecl_time
    integers = list(spawner.ecl_ints)
    floats = list(spawner.ecl_floats)
    compare_register = spawner.ecl_compare
    call_stack = list(spawner.ecl_stack)
    interactable = spawner.interactable
    collidable = spawner.collidable
    invisible = spawner.invisible
    hitbox_half_width = spawner.hitbox_half_width
    hitbox_half_height = spawner.hitbox_half_height
    call_stack_disabled = spawner.call_stack_disabled
    life = spawner.life
    life_lower_bound = spawner.life
    damageable = spawner.damageable
    is_boss = spawner.is_boss
    rank_speed_low = spawner.bullet_rank_speed_low
    rank_speed_high = spawner.bullet_rank_speed_high
    rank_amount1_low = spawner.bullet_rank_amount1_low
    rank_amount1_high = spawner.bullet_rank_amount1_high
    rank_amount2_low = spawner.bullet_rank_amount2_low
    rank_amount2_high = spawner.bullet_rank_amount2_high
    boss_timer = spawner.boss_timer
    boss_timer_subframe = spawner.boss_timer_float - spawner.boss_timer
    death_callback_sub = spawner.death_callback_sub
    life_callback_threshold = spawner.life_callback_threshold
    life_callback_sub = spawner.life_callback_sub
    timer_callback_threshold = spawner.timer_callback_threshold
    timer_callback_sub = spawner.timer_callback_sub
    pattern = spawner.pattern
    effect_floats = spawner.bullet_effect_floats
    effect_ints = spawner.bullet_effect_ints
    shooting_disabled = spawner.shooting_disabled
    interval = spawner.interval
    interval_timer = spawner.timer
    interval_timer_low = interval_timer
    interval_timer_high = interval_timer
    interval_subframe = spawner.timer_float - spawner.timer
    enemy_x = spawner.x
    enemy_y = spawner.y
    velocity_x = spawner.velocity_x
    velocity_y = spawner.velocity_y
    angle = spawner.angle
    angular_velocity = spawner.angular_velocity
    speed = spawner.speed
    acceleration = spawner.acceleration
    movement_mode = spawner.movement_mode
    movement_ease = spawner.movement_ease
    move_interp_x = spawner.move_interp_x
    move_interp_y = spawner.move_interp_y
    move_start_x = spawner.move_start_x
    move_start_y = spawner.move_start_y
    move_timer = spawner.move_timer
    move_timer_float = spawner.move_timer_float
    move_start_time = spawner.move_start_time
    lower_move_x = spawner.lower_move_x
    lower_move_y = spawner.lower_move_y
    upper_move_x = spawner.upper_move_x
    upper_move_y = spawner.upper_move_y
    should_clamp_position = spawner.should_clamp_position
    position_uncertainty = 0.0
    velocity_uncertainty = 0.0
    uncertain_heading = False
    shoot_offset_x: float | FloatInterval = spawner.shoot_offset_x
    shoot_offset_y: float | FloatInterval = spawner.shoot_offset_y
    abstract_int_cursor = 0

    def emit(
        resolved: BulletPattern,
        origin: tuple[float | FloatInterval, float | FloatInterval],
        player: tuple[float, float],
    ) -> tuple[Bullet, ...]:
        origin_x, origin_y = origin
        origin_uncertainty_x = 0.0
        origin_uncertainty_y = 0.0
        if isinstance(origin_x, FloatInterval):
            if not radial_births:
                raise UnsupportedBirthModel("uncertain shoot-offset x needs a hard envelope")
            origin_uncertainty_x = (origin_x.high - origin_x.low) / 2.0
            origin_x = (origin_x.low + origin_x.high) / 2.0
        if isinstance(origin_y, FloatInterval):
            if not radial_births:
                raise UnsupportedBirthModel("uncertain shoot-offset y needs a hard envelope")
            origin_uncertainty_y = (origin_y.high - origin_y.low) / 2.0
            origin_y = (origin_y.low + origin_y.high) / 2.0
        if radial_births:
            return tuple(
                replace(
                    bullet,
                    half_width=(
                        bullet.half_width
                        + position_uncertainty
                        + origin_uncertainty_x
                    ),
                    half_height=(
                        bullet.half_height
                        + position_uncertainty
                        + origin_uncertainty_y
                    ),
                )
                for bullet in spawn_pattern_envelope(
                    resolved,
                    (origin_x, origin_y),
                )
            )
        return spawn_pattern(resolved, (origin_x, origin_y), player, rng)

    def clamp_position(x: float, y: float) -> tuple[float, float]:
        if not should_clamp_position:
            return x, y
        return (
            min(max(x, lower_move_x), upper_move_x),
            min(max(y, lower_move_y), upper_move_y),
        )

    for frame_index, player in enumerate(player_positions):
        variable_player = player if allow_player_variables else None
        if velocity_uncertainty > 0.0:
            position_uncertainty += velocity_uncertainty
        else:
            enemy_x += -velocity_x if spawner.invert_x else velocity_x
            enemy_y += velocity_y
            enemy_x, enemy_y = clamp_position(enemy_x, enemy_y)
        if (
            life_callback_threshold >= 0
            and life_lower_bound < life_callback_threshold
        ):
            return EclForecast(
                tuple(map(tuple, births)),
                frame_index,
                "player damage can reach an active life callback",
            )
        if death_callback_sub >= 0 and life_lower_bound <= 0:
            return EclForecast(
                tuple(map(tuple, births)),
                frame_index,
                "player damage can reach an active death callback",
            )
        if (
            timer_callback_threshold >= 0
            and boss_timer >= timer_callback_threshold
        ):
            if not 0 <= timer_callback_sub < len(spawner.ecl_subroutines):
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    f"timer callback subroutine {timer_callback_sub} is unavailable",
                )
            callback_address = spawner.ecl_subroutines[timer_callback_sub]
            if callback_address not in program:
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    "timer callback instruction graph is not captured",
                )
            instruction_address = callback_address
            current_time = 0
            time_subframe = 0.0
            timer_callback_threshold = -1
            timer_callback_sub = death_callback_sub
            boss_timer = 0
            boss_timer_subframe = 0.0
            rank_speed_low = -0.5
            rank_speed_high = 0.5
            rank_amount1_low = rank_amount1_high = 0
            rank_amount2_low = rank_amount2_high = 0
            call_stack.clear()
        enemy = (enemy_x, enemy_y)
        stop_after_frame = ""
        for _instruction_count in range(256):
            instruction = program.get(instruction_address)
            if instruction is None:
                return EclForecast(
                    tuple(map(tuple, births)), frame_index, "incomplete ECL instruction graph"
                )
            if instruction.time != current_time:
                break
            execute = bool(instruction.skip_for_difficulty & (1 << difficulty))
            next_address = instruction.address + instruction.offset_to_next
            raw = bytes.fromhex(instruction.raw_hex)
            if not execute or instruction.opcode == OPCODE_NOP:
                instruction_address = next_address
                continue
            if instruction.opcode == 1:
                # RunEcl returns ZUN_ERROR; EnemyManager immediately despawns
                # this emitter before body collision or its periodic shot.
                return EclForecast(
                    tuple(map(tuple, births)),
                    horizon,
                    "source UNIMP despawns emitter",
                    body_hazards=tuple(tuple(frame) for frame in body_hazards),
                    finished=True,
                )
            if instruction.opcode in (OPCODE_JUMP, OPCODE_JUMPDEC):
                jump_time, jump_offset = struct.unpack_from("<ii", raw, 0x0C)
                take_jump = True
                if instruction.opcode == OPCODE_JUMPDEC:
                    variable = struct.unpack_from("<i", raw, 0x14)[0]
                    value = _int_var(variable, integers, difficulty, rank, life) - 1
                    if not _set_int_var(variable, value, integers):
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "unsupported JUMPDEC variable"
                        )
                    take_jump = value > 0
                if take_jump:
                    current_time = jump_time
                    instruction_address = instruction.address + jump_offset
                else:
                    instruction_address = next_address
                continue
            if instruction.opcode in (OPCODE_SET_INT, OPCODE_SET_FLOAT):
                result, argument = struct.unpack_from("<ii", raw, 0x0C)
                try:
                    value, source_is_float = _set_source_value(
                        argument,
                        integers,
                        floats,
                        difficulty,
                        rank,
                        life,
                        boss_timer,
                        enemy,
                        variable_player,
                    )
                    assigned = _set_local_from_source_bits(
                        result,
                        value,
                        source_is_float,
                        integers,
                        floats,
                    )
                except UnsupportedBirthModel as error:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, str(error)
                    )
                if not assigned:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index,
                        "SET writes an unsupported world variable",
                    )
            elif instruction.opcode in (OPCODE_SET_SELF_X, OPCODE_SET_SELF_Y):
                target = struct.unpack_from("<i", raw, 0x0C)[0]
                value = enemy_x if instruction.opcode == OPCODE_SET_SELF_X else enemy_y
                if not _set_float_var(target, value, floats):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported SETVARSELF target"
                    )
            elif instruction.opcode == OPCODE_SET_SELF_Z:
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    "SETVARSELFZ needs the uncaptured source z coordinate",
                )
            elif instruction.opcode in (
                OPCODE_SET_INT_RANDOM,
                OPCODE_SET_INT_RANDOM_MIN,
                OPCODE_SET_FLOAT_RANDOM,
                OPCODE_SET_FLOAT_RANDOM_MIN,
            ):
                result = struct.unpack_from("<i", raw, 0x0C)[0]
                if instruction.opcode in (
                    OPCODE_SET_INT_RANDOM,
                    OPCODE_SET_INT_RANDOM_MIN,
                ):
                    extent_raw = struct.unpack_from("<i", raw, 0x10)[0]
                    extent = _int_var(
                        extent_raw, integers, difficulty, rank, life
                    ) & 0xFFFFFFFF
                    if rng is None:
                        if not abstract_rng:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "integer ECL random variable requires RNG state",
                            )
                        if extent == 0:
                            value = 0
                        elif abstract_int_cursor >= len(abstract_int_choices):
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "integer RNG needs bounded branch expansion",
                                unresolved_int_extent=extent,
                            )
                        else:
                            value = abstract_int_choices[abstract_int_cursor]
                            abstract_int_cursor += 1
                            if not 0 <= value < extent:
                                return EclForecast(
                                    tuple(map(tuple, births)),
                                    frame_index,
                                    "integer RNG branch is outside its source range",
                                )
                    else:
                        value = rng.u32_in_range(extent)
                    if instruction.opcode == OPCODE_SET_INT_RANDOM_MIN:
                        minimum_raw = struct.unpack_from("<i", raw, 0x14)[0]
                        value += _int_var(
                            minimum_raw, integers, difficulty, rank, life
                        )
                    if not _set_int_var(result, value, integers):
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "unsupported random-int target"
                        )
                else:
                    extent = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    if rng is None:
                        if not abstract_rng:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "ECL random variable requires RNG state",
                            )
                        if isinstance(extent, FloatInterval):
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "nested random-float interval is unsupported",
                            )
                        value: float | FloatInterval = FloatInterval(
                            min(0.0, extent), max(0.0, extent)
                        )
                        if instruction.opcode == OPCODE_SET_FLOAT_RANDOM_MIN:
                            value = _float_add(value, _float_var(
                                raw[0x14:0x18], integers, floats, difficulty, rank,
                                life, enemy, variable_player,
                            ))
                    else:
                        value = rng.f32_in_range(extent)
                        if instruction.opcode == OPCODE_SET_FLOAT_RANDOM_MIN:
                            value += _float_var(
                                raw[0x14:0x18], integers, floats, difficulty, rank,
                                life, enemy, variable_player,
                            )
                    if not _set_float_var(result, value, floats):
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "unsupported random-float target"
                        )
            elif instruction.opcode in (
                OPCODE_MATH_INT_ADD,
                OPCODE_MATH_INT_SUBTRACT,
                OPCODE_MATH_INT_MULTIPLY,
                OPCODE_MATH_INT_DIVIDE,
                OPCODE_MATH_INT_MODULO,
            ):
                target, lhs_raw, rhs_raw = struct.unpack_from("<iii", raw, 0x0C)
                lhs = _int_var(lhs_raw, integers, difficulty, rank, life)
                rhs = _int_var(rhs_raw, integers, difficulty, rank, life)
                if instruction.opcode == OPCODE_MATH_INT_ADD:
                    value = lhs + rhs
                elif instruction.opcode == OPCODE_MATH_INT_SUBTRACT:
                    value = lhs - rhs
                elif instruction.opcode == OPCODE_MATH_INT_MULTIPLY:
                    value = lhs * rhs
                elif rhs == 0:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "ECL integer division by zero"
                    )
                elif instruction.opcode == OPCODE_MATH_INT_DIVIDE:
                    value = _trunc_div(lhs, rhs)
                else:
                    value = lhs - _trunc_div(lhs, rhs) * rhs
                if not _set_int_var(target, value, integers):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported integer-math target"
                    )
            elif instruction.opcode in (
                OPCODE_MATH_INCREMENT,
                OPCODE_MATH_DECREMENT,
            ):
                target = struct.unpack_from("<i", raw, 0x0C)[0]
                value = _int_var(
                    target, integers, difficulty, rank, life
                )
                value += 1 if instruction.opcode == OPCODE_MATH_INCREMENT else -1
                if not _set_int_var(target, value, integers):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported increment target"
                    )
            elif OPCODE_MATH_FLOAT_ADD <= instruction.opcode <= OPCODE_MATH_ATAN2:
                target = struct.unpack_from("<i", raw, 0x0C)[0]
                lhs = _float_var(
                    raw[0x10:0x14], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
                rhs = _float_var(
                    raw[0x14:0x18], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
                if instruction.opcode == OPCODE_MATH_FLOAT_ADD:
                    value = _float_add(lhs, rhs)
                elif instruction.opcode == OPCODE_MATH_FLOAT_SUBTRACT:
                    value = _float_subtract(lhs, rhs)
                elif instruction.opcode == OPCODE_MATH_FLOAT_MULTIPLY:
                    value = _float_multiply(lhs, rhs)
                elif instruction.opcode == OPCODE_MATH_FLOAT_DIVIDE:
                    try:
                        value = _float_divide(lhs, rhs)
                    except UnsupportedBirthModel as error:
                        return EclForecast(tuple(map(tuple, births)), frame_index, str(error))
                elif instruction.opcode == OPCODE_MATH_FLOAT_MODULO:
                    if isinstance(lhs, FloatInterval) or isinstance(rhs, FloatInterval):
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "float interval reaches ECL modulo",
                        )
                    if rhs == 0.0:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "ECL float modulo by zero"
                        )
                    value = math.fmod(lhs, rhs)
                else:
                    third = _float_var(
                        raw[0x18:0x1C], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    fourth = _float_var(
                        raw[0x1C:0x20], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    if any(isinstance(item, FloatInterval) for item in (
                        lhs, rhs, third, fourth
                    )):
                        if not radial_births:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "float interval reaches ECL atan2",
                            )
                        value = FloatInterval(-math.pi, math.pi)
                    else:
                        value = math.atan2(fourth - rhs, third - lhs)
                if not _set_float_var(target, value, floats):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported float-math target"
                    )
            elif instruction.opcode == OPCODE_MATH_NORMALIZE_ANGLE:
                target = struct.unpack_from("<i", raw, 0x0C)[0]
                value = _float_var(
                    raw[0x0C:0x10], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
                value = (
                    FloatInterval(-math.pi, math.pi)
                    if isinstance(value, FloatInterval)
                    else math.remainder(value, math.tau)
                )
                if not _set_float_var(target, value, floats):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported angle target"
                    )
            elif instruction.opcode in (OPCODE_COMPARE_INT, OPCODE_COMPARE_FLOAT):
                if instruction.opcode == OPCODE_COMPARE_INT:
                    lhs_raw, rhs_raw = struct.unpack_from("<ii", raw, 0x0C)
                    lhs = _int_var(lhs_raw, integers, difficulty, rank, life)
                    rhs = _int_var(rhs_raw, integers, difficulty, rank, life)
                else:
                    lhs = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    rhs = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    if isinstance(lhs, FloatInterval) or isinstance(rhs, FloatInterval):
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "float interval reaches ECL comparison",
                        )
                    if not math.isfinite(lhs) or not math.isfinite(rhs):
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "non-finite ECL comparison"
                        )
                compare_register = 0 if lhs == rhs else -1 if lhs < rhs else 1
            elif OPCODE_JUMP_LESS <= instruction.opcode <= OPCODE_JUMP_NOT_EQUAL:
                take_jump = (
                    compare_register < 0 if instruction.opcode == OPCODE_JUMP_LESS
                    else compare_register <= 0 if instruction.opcode == OPCODE_JUMP_LESS_EQUAL
                    else compare_register == 0 if instruction.opcode == OPCODE_JUMP_EQUAL
                    else compare_register > 0 if instruction.opcode == OPCODE_JUMP_GREATER
                    else compare_register >= 0 if instruction.opcode == OPCODE_JUMP_GREATER_EQUAL
                    else compare_register != 0
                )
                if take_jump:
                    jump_time, jump_offset = struct.unpack_from("<ii", raw, 0x0C)
                    current_time = jump_time
                    instruction_address = instruction.address + jump_offset
                    continue
            elif instruction.opcode == OPCODE_RETURN:
                if not call_stack:
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "ECL return has no captured caller context",
                    )
                caller = call_stack.pop()
                if caller.repeat_ex_index is not None:
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "ECL caller has a repeating callback",
                    )
                instruction_address = caller.instruction_address
                current_time = caller.time
                time_subframe = caller.time_float - caller.time
                integers = list(caller.ints)
                floats = list(caller.floats)
                compare_register = caller.compare
                continue
            elif OPCODE_CALL <= instruction.opcode <= OPCODE_CALL_NOT_EQUAL:
                take_call = instruction.opcode == OPCODE_CALL
                if instruction.opcode >= OPCODE_CALL_LESS:
                    lhs_raw, rhs = struct.unpack_from("<ii", raw, 0x18)
                    lhs = _int_var(
                        lhs_raw, integers, difficulty, rank, life
                    )
                    take_call = (
                        lhs < rhs
                        if instruction.opcode == OPCODE_CALL_LESS
                        else lhs <= rhs
                        if instruction.opcode == OPCODE_CALL_LESS_EQUAL
                        else lhs == rhs
                        if instruction.opcode == OPCODE_CALL_EQUAL
                        else lhs > rhs
                        if instruction.opcode == OPCODE_CALL_GREATER
                        else lhs >= rhs
                        if instruction.opcode == OPCODE_CALL_GREATER_EQUAL
                        else lhs != rhs
                    )
                if take_call:
                    if call_stack_disabled:
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "ECL call stack is disabled",
                        )
                    if len(call_stack) > 7:
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "invalid ECL call stack depth",
                        )
                    sub_id, var0 = struct.unpack_from("<ii", raw, 0x0C)
                    if not 0 <= sub_id < len(spawner.ecl_subroutines):
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            f"ECL call subroutine {sub_id} is unavailable",
                        )
                    # RunEcl still enters the callee at stackDepth == 7, but
                    # does not increment the depth.  Its write to saved slot 7
                    # is therefore not the context restored by RET: RET first
                    # decrements to 6 and restores saved slot 6.  Keeping the
                    # existing seven captured contexts models that source
                    # behavior exactly.
                    if len(call_stack) < 7:
                        call_stack.append(EnemyEclContext(
                            next_address,
                            current_time,
                            current_time + time_subframe,
                            tuple(integers),
                            tuple(floats),
                            compare_register,
                            None,
                        ))
                    integers[0] = var0
                    floats[0] = struct.unpack_from("<f", raw, 0x14)[0]
                    instruction_address = spawner.ecl_subroutines[sub_id]
                    current_time = 0
                    time_subframe = 0.0
                    continue
            elif instruction.opcode == OPCODE_COLLIDABLE_FLAG:
                collidable = bool(struct.unpack_from("<i", raw, 0x0C)[0])
            elif instruction.opcode == OPCODE_DAMAGEABLE_FLAG:
                damageable = bool(struct.unpack_from("<i", raw, 0x0C)[0])
            elif instruction.opcode == OPCODE_INTERACTABLE_FLAG:
                interactable = bool(struct.unpack_from("<i", raw, 0x0C)[0])
            elif instruction.opcode == OPCODE_INVISIBLE_FLAG:
                invisible = bool(struct.unpack_from("<i", raw, 0x0C)[0])
            elif instruction.opcode == OPCODE_HITBOX_SET:
                hitbox_x, hitbox_y = struct.unpack_from("<ff", raw, 0x0C)
                if not all(
                    math.isfinite(value) and 0.0 <= value <= 1024.0
                    for value in (hitbox_x, hitbox_y)
                ):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "invalid ECL hitbox"
                    )
                # EnemyManager uses hitboxDimensions / 1.5 as a full player
                # collision size, so the half-extent is source value / 3.
                hitbox_half_width = hitbox_x / 3.0
                hitbox_half_height = hitbox_y / 3.0
            elif OPCODE_MOVE_POSITION <= instruction.opcode <= OPCODE_MOVE_AT_PLAYER:
                if instruction.opcode == OPCODE_MOVE_POSITION:
                    enemy_x = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                            life, enemy, variable_player,
                    )
                    enemy_y = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    enemy_x, enemy_y = clamp_position(enemy_x, enemy_y)
                    enemy = (enemy_x, enemy_y)
                elif instruction.opcode == OPCODE_MOVE_POSITION + 1:
                    velocity_x = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    velocity_y = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                            life, enemy, variable_player,
                    )
                    movement_mode = 0
                    uncertain_heading = False
                    velocity_uncertainty = 0.0
                elif instruction.opcode == OPCODE_MOVE_POSITION + 2:
                    angle = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    speed = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    movement_mode = 1
                    if isinstance(angle, FloatInterval) and radial_births:
                        angle = 0.0
                        uncertain_heading = True
                    else:
                        uncertain_heading = False
                        velocity_uncertainty = 0.0
                elif instruction.opcode == OPCODE_MOVE_POSITION + 3:
                    angular_velocity = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    movement_mode = 1
                elif instruction.opcode == OPCODE_MOVE_POSITION + 4:
                    speed = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    movement_mode = 1
                elif instruction.opcode == OPCODE_MOVE_POSITION + 5:
                    acceleration = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    movement_mode = 1
                elif instruction.opcode in (OPCODE_MOVE_RANDOM, OPCODE_MOVE_RANDOM_IN_BOUNDS):
                    if rng is None:
                        if not abstract_rng:
                            return EclForecast(
                                tuple(map(tuple, births)), frame_index, "random movement requires RNG state"
                            )
                        angle = 0.0
                        uncertain_heading = True
                    else:
                        low, high = struct.unpack_from("<ff", raw, 0x0C)
                        angle = rng.f32_in_range(high - low) + low
                        uncertain_heading = False
                        velocity_uncertainty = 0.0
                    if instruction.opcode == OPCODE_MOVE_RANDOM_IN_BOUNDS:
                        if not should_clamp_position:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "MOVERANDINBOUND has no active source bounds",
                            )
                        if not uncertain_heading:
                            if enemy_x < lower_move_x + 96.0 and (
                                angle > math.pi / 2.0 or angle < -math.pi / 2.0
                            ):
                                angle = (
                                    math.pi - angle
                                    if angle > math.pi / 2.0
                                    else -math.pi - angle
                                )
                            if enemy_x > upper_move_x - 96.0 and (
                                0.0 <= angle < math.pi / 2.0
                                or -math.pi / 2.0 < angle <= 0.0
                            ):
                                angle = (
                                    math.pi - angle if angle >= 0.0 else -math.pi - angle
                                )
                            if enemy_y < lower_move_y + 48.0 and angle < 0.0:
                                angle = -angle
                            if enemy_y > upper_move_y - 48.0 and angle > 0.0:
                                angle = -angle
                else:
                    if not allow_player_variables:
                        angle = 0.0
                        uncertain_heading = True
                    else:
                        angle_offset = struct.unpack_from("<f", raw, 0x0C)[0]
                        angle = math.atan2(
                            player[1] - enemy_y, player[0] - enemy_x
                        ) + angle_offset
                        uncertain_heading = False
                        velocity_uncertainty = 0.0
                    speed = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    movement_mode = 1
                if isinstance(enemy_x, FloatInterval) or isinstance(enemy_y, FloatInterval):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "position interval needs clamp bounds"
                    )
                if isinstance(velocity_x, FloatInterval) or isinstance(velocity_y, FloatInterval):
                    if not radial_births:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "uncertain axis velocity"
                        )
                    velocity_uncertainty = math.hypot(
                        _maximum_magnitude(velocity_x),
                        _maximum_magnitude(velocity_y),
                    )
                    velocity_x = velocity_y = 0.0
                    uncertain_heading = True
                if isinstance(angle, FloatInterval):
                    if not radial_births:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "uncertain movement angle"
                        )
                    angle = 0.0
                    uncertain_heading = True
                if isinstance(speed, FloatInterval):
                    if not radial_births:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "uncertain movement speed"
                        )
                    speed = _maximum_magnitude(speed)
                    uncertain_heading = True
                if isinstance(angular_velocity, FloatInterval):
                    if not radial_births:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "uncertain angular velocity"
                        )
                    angular_velocity = _maximum_magnitude(angular_velocity)
                    uncertain_heading = True
                if isinstance(acceleration, FloatInterval):
                    if not radial_births:
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "uncertain acceleration"
                        )
                    acceleration = _maximum_magnitude(acceleration)
                    uncertain_heading = True
                if not all(math.isfinite(value) for value in (
                    enemy_x,
                    enemy_y,
                    velocity_x,
                    velocity_y,
                    angle,
                    angular_velocity,
                    speed,
                    acceleration,
                )):
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "future player dependency reaches emitter motion",
                    )
            elif OPCODE_MOVE_DIR_TIME_FIRST <= instruction.opcode <= OPCODE_MOVE_TIME_LAST:
                duration = struct.unpack_from("<i", raw, 0x0C)[0]
                if duration <= 0:
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "timed ECL movement has a non-positive duration",
                    )
                if instruction.opcode < OPCODE_MOVE_POSITION_TIME_FIRST:
                    timed_angle = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    timed_speed = struct.unpack_from("<f", raw, 0x14)[0]
                    if isinstance(timed_angle, FloatInterval):
                        if not radial_births:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "uncertain timed-movement angle",
                            )
                        position_uncertainty += abs(timed_speed) * duration / 2.0
                        move_interp_x = move_interp_y = 0.0
                    else:
                        move_interp_x = math.cos(timed_angle) * timed_speed * duration / 2.0
                        move_interp_y = math.sin(timed_angle) * timed_speed * duration / 2.0
                    movement_ease = instruction.opcode - OPCODE_MOVE_DIR_TIME_FIRST + 1
                elif instruction.opcode < OPCODE_MOVE_TIME_FIRST:
                    target_x = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    target_y = _float_var(
                        raw[0x14:0x18], integers, floats, difficulty, rank,
                        life, enemy, variable_player,
                    )
                    if isinstance(target_x, FloatInterval) or isinstance(
                        target_y, FloatInterval
                    ):
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "uncertain timed-movement target",
                        )
                    move_interp_x = target_x - enemy_x
                    move_interp_y = target_y - enemy_y
                    movement_ease = instruction.opcode - OPCODE_MOVE_POSITION_TIME_FIRST
                    velocity_x = velocity_y = 0.0
                else:
                    if uncertain_heading:
                        if not radial_births:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "uncertain heading reaches timed movement",
                            )
                        position_uncertainty += abs(speed) * duration / 2.0
                        move_interp_x = move_interp_y = 0.0
                    else:
                        move_interp_x = math.cos(angle) * speed * duration / 2.0
                        move_interp_y = math.sin(angle) * speed * duration / 2.0
                    movement_ease = instruction.opcode - OPCODE_MOVE_TIME_FIRST + 1
                move_start_x = enemy_x
                move_start_y = enemy_y
                move_start_time = duration
                move_timer = duration
                move_timer_float = float(duration)
                movement_mode = 2
                uncertain_heading = False
                velocity_uncertainty = 0.0
            elif instruction.opcode == OPCODE_MOVE_BOUNDS_SET:
                (
                    lower_move_x,
                    lower_move_y,
                    upper_move_x,
                    upper_move_y,
                ) = struct.unpack_from("<ffff", raw, 0x0C)
                if (
                    not all(math.isfinite(value) for value in (
                        lower_move_x, lower_move_y, upper_move_x, upper_move_y
                    ))
                    or lower_move_x > upper_move_x
                    or lower_move_y > upper_move_y
                ):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "invalid ECL move bounds"
                    )
                should_clamp_position = True
                enemy_x, enemy_y = clamp_position(enemy_x, enemy_y)
                enemy = (enemy_x, enemy_y)
            elif instruction.opcode == OPCODE_MOVE_BOUNDS_DISABLE:
                should_clamp_position = False
            elif OPCODE_BULLET_FIRST <= instruction.opcode <= OPCODE_BULLET_LAST:
                try:
                    pattern = _resolved_pattern(
                        instruction,
                        _copy_spawner(
                            spawner,
                            bullet_rank_speed_low=rank_speed_low,
                            bullet_rank_speed_high=rank_speed_high,
                            bullet_rank_amount1_low=rank_amount1_low,
                            bullet_rank_amount1_high=rank_amount1_high,
                            bullet_rank_amount2_low=rank_amount2_low,
                            bullet_rank_amount2_high=rank_amount2_high,
                        ),
                        effect_floats,
                        effect_ints,
                        integers,
                        floats,
                        difficulty,
                        rank,
                        life,
                        enemy,
                        variable_player,
                        bullet_sizes,
                        radial_births,
                    )
                    if not shooting_disabled:
                        births[frame_index].extend(emit(
                            pattern,
                            (
                                _float_add(enemy[0], shoot_offset_x),
                                _float_add(enemy[1], shoot_offset_y),
                            ),
                            player,
                        ))
                except UnsupportedBirthModel as error:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, str(error)
                    )
            elif instruction.opcode == OPCODE_SHOOT_INTERVAL:
                base_interval = struct.unpack_from("<i", raw, 0x0C)[0]
                low = _trunc_div(base_interval, 5)
                high = _trunc_div(-base_interval, 5)
                interval = base_interval + _rank_int(low, high, rank)
                interval_timer = 0
                interval_timer_low = 0
                interval_timer_high = 0
                interval_subframe = 0.0
            elif instruction.opcode == OPCODE_SHOOT_INTERVAL_DELAYED:
                base_interval = struct.unpack_from("<i", raw, 0x0C)[0]
                low = _trunc_div(base_interval, 5)
                high = _trunc_div(-base_interval, 5)
                interval = base_interval + _rank_int(low, high, rank)
                if rng is not None:
                    interval_timer = rng.u32_in_range(interval & 0xFFFFFFFF)
                    interval_timer_low = interval_timer
                    interval_timer_high = interval_timer
                elif abstract_rng and interval > 0:
                    # Randomness selects only the phase of this known periodic
                    # source. Keep every possible phase instead of sampling.
                    interval_timer = 0
                    interval_timer_low = 0
                    interval_timer_high = interval - 1
                elif not abstract_rng:
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "delayed interval requires RNG state",
                    )
                interval_subframe = 0.0
            elif instruction.opcode == OPCODE_SHOOT_DISABLED:
                shooting_disabled = True
            elif instruction.opcode == OPCODE_SHOOT_ENABLED:
                shooting_disabled = False
            elif instruction.opcode == OPCODE_SHOOT_NOW:
                if pattern is None:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "SHOOTNOW has no resolved pattern"
                    )
                try:
                    births[frame_index].extend(emit(
                        pattern,
                        (
                            _float_add(enemy[0], shoot_offset_x),
                            _float_add(enemy[1], shoot_offset_y),
                        ),
                        player,
                    ))
                except UnsupportedBirthModel as error:
                    return EclForecast(tuple(map(tuple, births)), frame_index, str(error))
            elif instruction.opcode == OPCODE_SHOOT_OFFSET:
                shoot_offset_x = _float_var(
                    raw[0x0C:0x10], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
                shoot_offset_y = _float_var(
                    raw[0x10:0x14], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
                # The source also stores z. It does not affect TH06's 2D
                # collision geometry, but resolve it so unknown variables
                # still fail closed consistently.
                _float_var(
                    raw[0x14:0x18], integers, floats, difficulty, rank,
                    life, enemy, variable_player,
                )
            elif instruction.opcode == OPCODE_BULLET_EFFECTS:
                effect_ints = tuple(
                    _int_var(value, integers, difficulty, rank, life)
                    for value in struct.unpack_from("<iiii", raw, 0x0C)
                )
                resolved_effect_floats = tuple(
                    _float_var(
                        raw[offset:offset + 4], integers, floats, difficulty,
                        rank, life, enemy, variable_player,
                    )
                    for offset in range(0x1C, 0x2C, 4)
                )
                if any(
                    isinstance(value, FloatInterval)
                    for value in resolved_effect_floats
                ):
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        "uncertain bullet effects need a hard envelope",
                    )
                effect_floats = resolved_effect_floats
                if pattern is not None:
                    pattern = replace(
                        pattern,
                        ex_ints=effect_ints,
                        ex_floats=effect_floats,
                    )
            elif instruction.opcode == OPCODE_SPELL_START:
                # SpellcardStart source defaults. Bullet cancellation is a
                # hazard removal, so retaining existing bullets is conservative.
                rank_speed_low = -0.5
                rank_speed_high = 0.5
                rank_amount1_low = rank_amount1_high = 0
                rank_amount2_low = rank_amount2_high = 0
            elif instruction.opcode == OPCODE_LIFE_SET:
                life = struct.unpack_from("<i", raw, 0x0C)[0]
                life_lower_bound = life
            elif instruction.opcode == OPCODE_DEATH_CALLBACK:
                death_callback_sub = struct.unpack_from("<i", raw, 0x0C)[0]
            elif instruction.opcode == OPCODE_BOSS_TIMER_SET:
                boss_timer = struct.unpack_from("<i", raw, 0x0C)[0]
                boss_timer_subframe = 0.0
            elif instruction.opcode == OPCODE_LIFE_CALLBACK_THRESHOLD:
                life_callback_threshold = struct.unpack_from("<i", raw, 0x0C)[0]
            elif instruction.opcode == OPCODE_LIFE_CALLBACK_SUB:
                life_callback_sub = struct.unpack_from("<i", raw, 0x0C)[0]
            elif instruction.opcode == OPCODE_TIMER_CALLBACK_THRESHOLD:
                timer_callback_threshold = struct.unpack_from("<i", raw, 0x0C)[0]
                boss_timer = 0
                boss_timer_subframe = 0.0
            elif instruction.opcode == OPCODE_TIMER_CALLBACK_SUB:
                timer_callback_sub = struct.unpack_from("<i", raw, 0x0C)[0]
            elif instruction.opcode == OPCODE_DROP_ITEMS:
                count = struct.unpack_from("<i", raw, 0x0C)[0]
                if count < 0:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "negative DROPITEMS count"
                    )
                if rng is not None:
                    for _ in range(count):
                        rng.f32_in_range(144.0)
                        rng.f32_in_range(144.0)
            elif instruction.opcode == OPCODE_EX_REPEAT:
                index = struct.unpack_from("<i", raw, 0x0C)[0]
                if index >= 0:
                    return EclForecast(
                        tuple(map(tuple, births)),
                        frame_index,
                        f"repeating ECL external instruction {index} can mutate hazards",
                    )
            elif instruction.opcode == OPCODE_TIME_SET:
                variable = struct.unpack_from("<i", raw, 0x0C)[0]
                current_time += _int_var(variable, integers, difficulty, rank, life)
            elif instruction.opcode == OPCODE_CALL_STACK_DISABLED:
                call_stack_disabled = bool(struct.unpack_from("<i", raw, 0x0C)[0])
            elif instruction.opcode == OPCODE_BULLET_RANK_INFLUENCE:
                rank_speed_low, rank_speed_high = struct.unpack_from("<ff", raw, 0x0C)
                (
                    rank_amount1_low,
                    rank_amount1_high,
                    rank_amount2_low,
                    rank_amount2_high,
                ) = struct.unpack_from("<iiii", raw, 0x14)
            elif instruction.opcode == OPCODE_BOSS_TIMER_CLEAR:
                timer_callback_sub = death_callback_sub
                boss_timer = 0
                boss_timer_subframe = 0.0
            elif (
                instruction.opcode == OPCODE_ENEMY_KILL_ALL
                and enemy_kill_all_is_noop
            ):
                pass
            elif instruction.opcode in HAZARD_NEUTRAL_ECL_OPCODES:
                pass
            elif instruction.opcode in FAIL_CLOSED_ECL_OPCODES:
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    FAIL_CLOSED_ECL_OPCODES[instruction.opcode],
                )
            else:
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    f"unclassified ECL opcode {instruction.opcode}",
                )
            instruction_address = next_address
        else:
            return EclForecast(
                tuple(map(tuple, births)), frame_index, "ECL instruction budget exhausted"
            )

        motion = finish_motion_values(
            enemy_x,
            enemy_y,
            velocity_x,
            velocity_y,
            angle,
            speed,
            angular_velocity,
            acceleration,
            movement_mode,
            movement_ease,
            move_interp_x,
            move_interp_y,
            move_start_x,
            move_start_y,
            move_timer,
            move_timer_float,
            move_start_time,
        )
        enemy_x, enemy_y = motion.x, motion.y
        enemy_x, enemy_y = clamp_position(enemy_x, enemy_y)
        velocity_x, velocity_y = motion.velocity_x, motion.velocity_y
        angle, speed = motion.angle, motion.speed
        movement_mode = motion.movement_mode
        move_timer, move_timer_float = motion.move_timer, motion.move_timer_float
        if uncertain_heading:
            velocity_uncertainty = abs(speed)
            velocity_x = 0.0
            velocity_y = 0.0
        else:
            velocity_uncertainty = 0.0
        enemy = (enemy_x, enemy_y)

        if (
            interactable
            and collidable
            and not invisible
            and hitbox_half_width > 0.0
            and hitbox_half_height > 0.0
        ):
            body_hazards[frame_index].append((
                enemy_x - hitbox_half_width - position_uncertainty,
                enemy_y - hitbox_half_height - position_uncertainty,
                enemy_x + hitbox_half_width + position_uncertainty,
                enemy_y + hitbox_half_height + position_uncertainty,
            ))

        if life > 0 and interval > 0:
            interval_subframe += frame_multiplier
            while interval_subframe >= 1.0:
                interval_timer += 1
                interval_timer_low += 1
                interval_timer_high += 1
                interval_subframe -= 1.0
            if interval_timer_high >= interval:
                if pattern is None:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "periodic shooter has no resolved pattern"
                    )
                try:
                    births[frame_index].extend(emit(
                        pattern,
                        (
                            _float_add(enemy[0], shoot_offset_x),
                            _float_add(enemy[1], shoot_offset_y),
                        ),
                        player,
                    ))
                except UnsupportedBirthModel as error:
                    return EclForecast(tuple(map(tuple, births)), frame_index, str(error))
                if interval_timer_low >= interval:
                    interval_timer_low = 0
                    interval_timer_high = 0
                else:
                    # Union the fired phase (timer 0) with every phase that
                    # has not fired. This compact interval remains sound.
                    interval_timer_low = 0
                    interval_timer_high = min(interval_timer_high, interval - 1)
                interval_timer = interval_timer_low
                interval_subframe = 0.0
        if interactable:
            # EnemyManager caps player-shot damage at 70 per update. A
            # collidable non-boss can additionally lose 10 from kill-box
            # contact. This lower bound decides only whether an asynchronous
            # life callback is reachable; it never removes a hazard.
            life_lower_bound -= (70 if damageable else 0) + (
                10 if collidable and not is_boss else 0
            )
        time_subframe += frame_multiplier
        while time_subframe >= 1.0:
            current_time += 1
            time_subframe -= 1.0
        boss_timer_subframe += frame_multiplier
        while boss_timer_subframe >= 1.0:
            boss_timer += 1
            boss_timer_subframe -= 1.0
        if stop_after_frame:
            return EclForecast(
                tuple(map(tuple, births)), frame_index + 1, stop_after_frame
            )
    next_instruction = program.get(instruction_address)
    return EclForecast(
        tuple(map(tuple, births)),
        horizon,
        next_spawner=_copy_spawner(
            spawner,
            x=enemy_x,
            y=enemy_y,
            velocity_x=velocity_x,
            velocity_y=velocity_y,
            angle=angle,
            angular_velocity=angular_velocity,
            speed=speed,
            acceleration=acceleration,
            movement_mode=movement_mode,
            movement_ease=movement_ease,
            move_interp_x=move_interp_x,
            move_interp_y=move_interp_y,
            move_start_x=move_start_x,
            move_start_y=move_start_y,
            move_timer=move_timer,
            move_timer_float=move_timer_float,
            move_start_time=move_start_time,
            shooting_disabled=shooting_disabled,
            shoot_offset_x=shoot_offset_x,
            shoot_offset_y=shoot_offset_y,
            interval=interval,
            timer=interval_timer,
            timer_float=interval_timer + interval_subframe,
            pattern=pattern,
            ecl_time=current_time,
            ecl_time_float=current_time + time_subframe,
            ecl_ints=tuple(integers),
            ecl_floats=tuple(floats),
            ecl_compare=compare_register,
            next_instruction=next_instruction,
            ecl_stack=tuple(call_stack),
            interactable=interactable,
            collidable=collidable,
            invisible=invisible,
            hitbox_half_width=hitbox_half_width,
            hitbox_half_height=hitbox_half_height,
            call_stack_disabled=call_stack_disabled,
            life=life,
            bullet_rank_speed_low=rank_speed_low,
            bullet_rank_speed_high=rank_speed_high,
            bullet_rank_amount1_low=rank_amount1_low,
            bullet_rank_amount1_high=rank_amount1_high,
            bullet_rank_amount2_low=rank_amount2_low,
            bullet_rank_amount2_high=rank_amount2_high,
            lower_move_x=lower_move_x,
            lower_move_y=lower_move_y,
            upper_move_x=upper_move_x,
            upper_move_y=upper_move_y,
            should_clamp_position=should_clamp_position,
            boss_timer=boss_timer,
            boss_timer_float=boss_timer + boss_timer_subframe,
            death_callback_sub=death_callback_sub,
            life_callback_threshold=life_callback_threshold,
            life_callback_sub=life_callback_sub,
            timer_callback_threshold=timer_callback_threshold,
            timer_callback_sub=timer_callback_sub,
            damageable=damageable,
            bullet_effect_floats=effect_floats,
            bullet_effect_ints=effect_ints,
        ),
        body_hazards=tuple(tuple(frame) for frame in body_hazards),
    )


def _forecast_ecl_births_with_life_callbacks(
    spawner: EnemySpawner,
    player_positions: tuple[tuple[float, float], ...],
    difficulty: int,
    rank: int,
    bullet_sizes: tuple[tuple[float, float], ...],
    frame_multiplier: float = 1.0,
    rng: RngState | None = None,
    allow_player_variables: bool = True,
    radial_births: bool = False,
    abstract_rng: bool = False,
    enemy_kill_all_is_noop: bool = False,
) -> EclForecast:
    """Forecast an emitter, branching over reachable hard life callbacks."""
    horizon = len(player_positions)
    callback_damage = (70 if spawner.damageable else 0) + (
        10 if spawner.collidable and not spawner.is_boss else 0
    )
    callback_gap = spawner.life - spawner.life_callback_threshold
    earliest_callback = (
        max(0, callback_gap // callback_damage + 1)
        if callback_damage > 0 and spawner.life_callback_threshold >= 0
        else horizon
    )
    should_branch = (
        abstract_rng
        and spawner.interactable
        and spawner.life_callback_threshold >= 0
        and 0 <= spawner.life_callback_sub < len(spawner.ecl_subroutines)
        and earliest_callback < horizon
    )
    if not should_branch:
        return _forecast_ecl_births_single(
            spawner,
            player_positions,
            difficulty,
            rank,
            bullet_sizes,
            frame_multiplier,
            rng,
            allow_player_variables,
            radial_births,
            abstract_rng,
            enemy_kill_all_is_noop,
        )

    program = {instruction.address: instruction for instruction in spawner.ecl_program}
    callback_address = spawner.ecl_subroutines[spawner.life_callback_sub]
    callback_instruction = program.get(callback_address)
    if callback_instruction is None:
        return EclForecast(
            tuple(() for _ in player_positions),
            0,
            "life callback instruction graph is not captured",
        )

    no_callback_spawner = _copy_spawner(
        spawner,
        life_callback_threshold=-1,
    )
    no_callback = _forecast_ecl_births_single(
        no_callback_spawner,
        player_positions,
        difficulty,
        rank,
        bullet_sizes,
        frame_multiplier,
        None,
        allow_player_variables,
        radial_births,
        abstract_rng,
        enemy_kill_all_is_noop,
    )
    births = [list(frame) for frame in no_callback.births]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    for index, frame_bodies in enumerate(no_callback.body_hazards):
        bodies[index].extend(frame_bodies)
    covered_frames = no_callback.covered_frames
    reason = no_callback.reason

    for callback_frame in range(earliest_callback, horizon):
        if callback_frame:
            prefix = _forecast_ecl_births_single(
                no_callback_spawner,
                player_positions[:callback_frame],
                difficulty,
                rank,
                bullet_sizes,
                frame_multiplier,
                None,
                allow_player_variables,
                radial_births,
                abstract_rng,
                enemy_kill_all_is_noop,
            )
            if prefix.covered_frames < callback_frame or prefix.next_spawner is None:
                branch_coverage = prefix.covered_frames
                if branch_coverage < covered_frames:
                    covered_frames = branch_coverage
                    reason = prefix.reason
                continue
            callback_source = prefix.next_spawner
        else:
            callback_source = no_callback_spawner
        callback_source = _copy_spawner(
            callback_source,
            life=spawner.life_callback_threshold,
            life_callback_threshold=-1,
            next_instruction=callback_instruction,
            ecl_time=0,
            ecl_time_float=0.0,
            ecl_stack=(),
            timer_callback_sub=callback_source.death_callback_sub,
            bullet_rank_speed_low=-0.5,
            bullet_rank_speed_high=0.5,
            bullet_rank_amount1_low=0,
            bullet_rank_amount1_high=0,
            bullet_rank_amount2_low=0,
            bullet_rank_amount2_high=0,
        )
        callback = _forecast_ecl_births_single(
            callback_source,
            player_positions[callback_frame:],
            difficulty,
            rank,
            bullet_sizes,
            frame_multiplier,
            None,
            allow_player_variables,
            radial_births,
            abstract_rng,
            enemy_kill_all_is_noop,
        )
        for index, frame_births in enumerate(callback.births, callback_frame):
            births[index].extend(frame_births)
        for index, frame_bodies in enumerate(callback.body_hazards, callback_frame):
            bodies[index].extend(frame_bodies)
        branch_coverage = callback_frame + callback.covered_frames
        if branch_coverage < covered_frames:
            covered_frames = branch_coverage
            reason = callback.reason

    return EclForecast(
        tuple(tuple(frame) for frame in births),
        covered_frames,
        reason if covered_frames < horizon else "",
        body_hazards=tuple(tuple(frame) for frame in bodies),
    )


def _life_callback_can_branch(
    spawner: EnemySpawner,
    horizon: int,
    abstract_rng: bool,
) -> bool:
    callback_damage = (70 if spawner.damageable else 0) + (
        10 if spawner.collidable and not spawner.is_boss else 0
    )
    callback_gap = spawner.life - spawner.life_callback_threshold
    earliest_callback = (
        max(0, callback_gap // callback_damage + 1)
        if callback_damage > 0 and spawner.life_callback_threshold >= 0
        else horizon
    )
    return (
        abstract_rng
        and spawner.interactable
        and spawner.life_callback_threshold >= 0
        and 0 <= spawner.life_callback_sub < len(spawner.ecl_subroutines)
        and earliest_callback < horizon
    )


def _forecast_abstract_integer_domains(
    spawner: EnemySpawner,
    player_positions: tuple[tuple[float, float], ...],
    difficulty: int,
    rank: int,
    bullet_sizes: tuple[tuple[float, float], ...],
    frame_multiplier: float,
    allow_player_variables: bool,
    radial_births: bool,
    enemy_kill_all_is_noop: bool,
) -> EclForecast:
    """Union every bounded source integer-RNG control-flow outcome."""
    pending: list[tuple[int, ...]] = [()]
    leaves: list[EclForecast] = []
    evaluated = 0
    while pending:
        choices = pending.pop()
        evaluated += 1
        if evaluated > MAX_ABSTRACT_INTEGER_RNG_EVALUATIONS:
            return EclForecast(
                tuple(() for _ in player_positions),
                0,
                "integer RNG branch budget exhausted",
            )
        forecast = _forecast_ecl_births_single(
            spawner,
            player_positions,
            difficulty,
            rank,
            bullet_sizes,
            frame_multiplier,
            None,
            allow_player_variables,
            radial_births,
            True,
            enemy_kill_all_is_noop,
            choices,
        )
        extent = forecast.unresolved_int_extent
        if extent:
            future_branch_count = len(pending) + len(leaves) + extent
            if future_branch_count > MAX_ABSTRACT_INTEGER_RNG_BRANCHES:
                return EclForecast(
                    tuple(() for _ in player_positions),
                    0,
                    f"integer RNG domain {extent} exceeds branch budget",
                )
            pending.extend(choices + (value,) for value in range(extent))
        else:
            leaves.append(forecast)

    births: list[list[Bullet]] = [[] for _ in player_positions]
    bodies: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    body_seen = [set() for _ in player_positions]
    for index in range(len(player_positions)):
        maximum_counts: Counter[Bullet] = Counter()
        for forecast in leaves:
            branch_counts = Counter(forecast.births[index])
            maximum_counts |= branch_counts
        for bullet, count in maximum_counts.items():
            births[index].extend((bullet,) * count)
    for forecast in leaves:
        for index, frame_bodies in enumerate(forecast.body_hazards):
            for body in frame_bodies:
                if body not in body_seen[index]:
                    body_seen[index].add(body)
                    bodies[index].append(body)
    covered_frames = min(
        (forecast.covered_frames for forecast in leaves),
        default=0,
    )
    reason = next(
        (
            forecast.reason for forecast in leaves
            if forecast.covered_frames == covered_frames
            and covered_frames < len(player_positions)
        ),
        "",
    )
    first_next = leaves[0].next_spawner if leaves else None
    common_next = (
        first_next
        if all(forecast.next_spawner == first_next for forecast in leaves)
        else None
    )
    return EclForecast(
        tuple(tuple(frame) for frame in births),
        covered_frames,
        reason,
        next_spawner=common_next,
        body_hazards=tuple(tuple(frame) for frame in bodies),
        finished=bool(leaves) and all(forecast.finished for forecast in leaves),
    )


def forecast_ecl_births(
    spawner: EnemySpawner,
    player_positions: tuple[tuple[float, float], ...],
    difficulty: int,
    rank: int,
    bullet_sizes: tuple[tuple[float, float], ...],
    frame_multiplier: float = 1.0,
    rng: RngState | None = None,
    allow_player_variables: bool = True,
    radial_births: bool = False,
    abstract_rng: bool = False,
    enemy_kill_all_is_noop: bool = False,
) -> EclForecast:
    """Forecast one emitter and preserve every bounded hard uncertainty."""
    if (
        abstract_rng
        and rng is None
        and not _life_callback_can_branch(
            spawner,
            len(player_positions),
            abstract_rng,
        )
    ):
        return _forecast_abstract_integer_domains(
            spawner,
            player_positions,
            difficulty,
            rank,
            bullet_sizes,
            frame_multiplier,
            allow_player_variables,
            radial_births,
            enemy_kill_all_is_noop,
        )
    return _forecast_ecl_births_with_life_callbacks(
        spawner,
        player_positions,
        difficulty,
        rank,
        bullet_sizes,
        frame_multiplier,
        rng,
        allow_player_variables,
        radial_births,
        abstract_rng,
        enemy_kill_all_is_noop,
    )
