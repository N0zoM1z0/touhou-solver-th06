"""Bounded, fail-closed ECL bullet-birth forecasting.

The forecaster interprets only source-audited emission instructions and the
small amount of control flow needed to reach them. Its coverage result is part
of the contract: callers must not treat frames after the first unsupported
instruction as modeled.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import struct

from ..model import Bullet, BulletPattern, EnemySpawner, EclInstruction
from .births import UnsupportedBirthModel, spawn_pattern, spawn_pattern_envelope
from .enemies import advance_position, finish_motion
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
OPCODE_MATH_INT_ADD = 13
OPCODE_MATH_INT_SUBTRACT = 14
OPCODE_MATH_INT_MULTIPLY = 15
OPCODE_MATH_INT_DIVIDE = 16
OPCODE_MATH_INT_MODULO = 17
OPCODE_MATH_INCREMENT = 18
OPCODE_MATH_DECREMENT = 19
OPCODE_MATH_FLOAT_ADD = 20
OPCODE_COMPARE_INT = 27
OPCODE_COMPARE_FLOAT = 28
OPCODE_JUMP_LESS = 29
OPCODE_JUMP_LESS_EQUAL = 30
OPCODE_JUMP_EQUAL = 31
OPCODE_JUMP_GREATER = 32
OPCODE_JUMP_GREATER_EQUAL = 33
OPCODE_JUMP_NOT_EQUAL = 34
OPCODE_MOVE_POSITION = 43
OPCODE_MOVE_AT_PLAYER = 51
OPCODE_MOVE_RANDOM = 49
OPCODE_MOVE_RANDOM_IN_BOUNDS = 50
OPCODE_BULLET_FIRST = 67
OPCODE_BULLET_LAST = 75
OPCODE_SHOOT_INTERVAL = 76
OPCODE_SHOOT_INTERVAL_DELAYED = 77
OPCODE_SHOOT_DISABLED = 78
OPCODE_SHOOT_ENABLED = 79
OPCODE_SHOOT_NOW = 80
OPCODE_SHOOT_OFFSET = 81
OPCODE_BULLET_EFFECTS = 82
OPCODE_BULLET_SOUND = 84
OPCODE_EFFECT_SOUND = 106


@dataclass(frozen=True)
class EclForecast:
    births: tuple[tuple[Bullet, ...], ...]
    covered_frames: int
    reason: str = ""
    next_spawner: EnemySpawner | None = None


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
    floats: list[float],
    difficulty: int,
    rank: int,
    life: int,
    enemy: tuple[float, float],
    player: tuple[float, float] | None,
) -> float:
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
            # Hard radial birth envelopes deliberately erase angle. NaN is a
            # taint value: only a bullet-angle consumer may absorb it.
            return math.nan
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


def _set_float_var(identifier: int, value: float, floats: list[float]) -> bool:
    if -10008 <= identifier <= -10005:
        floats[-10005 - identifier] = value
        return True
    return False


def _resolved_pattern(
    instruction: EclInstruction,
    spawner: EnemySpawner,
    current: BulletPattern | None,
    integers: list[int],
    floats: list[float],
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
    if not math.isfinite(speed1) or not math.isfinite(speed2_value):
        raise UnsupportedBirthModel("future player dependency reaches bullet speed")
    if speed1 != 0.0:
        speed1 = max(0.3, speed1 + speed_rank)
    speed2 = max(0.3, speed2_value + speed_rank / 2.0)
    angle1 = _float_var(
        raw[0x20:0x24], integers, floats, difficulty, rank, life, enemy, player
    )
    angle2 = _float_var(
        raw[0x24:0x28], integers, floats, difficulty, rank, life, enemy, player
    )
    if not math.isfinite(angle1) or not math.isfinite(angle2):
        if not radial_births:
            raise UnsupportedBirthModel("future player dependency reaches bullet angle")
        angle1 = angle2 = 0.0
    angle1 = math.remainder(angle1, math.tau)
    flags = struct.unpack_from("<I", raw, 0x28)[0]
    return BulletPattern(
        sprite,
        angle1,
        angle2,
        speed1,
        speed2,
        current.ex_floats if current is not None else (0.0, 0.0, 0.0, 0.0),
        current.ex_ints if current is not None else (0, 0, 0, 0),
        count1,
        count2,
        instruction.opcode - OPCODE_BULLET_FIRST,
        flags,
        half_width,
        half_height,
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
) -> EclForecast:
    """Forecast one emitter until the first unsupported source instruction."""
    horizon = len(player_positions)
    births: list[list[Bullet]] = [[] for _ in player_positions]
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
    pattern = spawner.pattern
    shooting_disabled = spawner.shooting_disabled
    interval = spawner.interval
    interval_timer = spawner.timer
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
    move_timer = spawner.move_timer
    move_timer_float = spawner.move_timer_float
    position_uncertainty = 0.0
    velocity_uncertainty = 0.0
    uncertain_heading = False

    def emit(
        resolved: BulletPattern,
        origin: tuple[float, float],
        player: tuple[float, float],
    ) -> tuple[Bullet, ...]:
        if radial_births:
            return tuple(
                replace(
                    bullet,
                    half_width=bullet.half_width + position_uncertainty,
                    half_height=bullet.half_height + position_uncertainty,
                )
                for bullet in spawn_pattern_envelope(resolved, origin)
            )
        return spawn_pattern(resolved, origin, player, rng)

    for frame_index, player in enumerate(player_positions):
        variable_player = player if allow_player_variables else None
        if velocity_uncertainty > 0.0:
            position_uncertainty += velocity_uncertainty
        else:
            positioned = advance_position(replace(
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
                move_timer=move_timer,
                move_timer_float=move_timer_float,
            ))
            enemy_x, enemy_y = positioned.x, positioned.y
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
            if instruction.opcode in (OPCODE_JUMP, OPCODE_JUMPDEC):
                jump_time, jump_offset, variable = struct.unpack_from("<iii", raw, 0x0C)
                take_jump = True
                if instruction.opcode == OPCODE_JUMPDEC:
                    value = _int_var(variable, integers, difficulty, rank, spawner.life) - 1
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
            if instruction.opcode == OPCODE_SET_INT:
                result, argument = struct.unpack_from("<ii", raw, 0x0C)
                value = _int_var(argument, integers, difficulty, rank, spawner.life)
                if not _set_int_var(result, value, integers):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported SETINT target"
                    )
            elif instruction.opcode == OPCODE_SET_FLOAT:
                result = struct.unpack_from("<i", raw, 0x0C)[0]
                value = _float_var(
                    raw[0x10:0x14], integers, floats, difficulty, rank,
                    spawner.life, enemy, variable_player,
                )
                if not _set_float_var(result, value, floats):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported SETFLOAT target"
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
                    if rng is None:
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "integer RNG requires a discrete uncertainty domain",
                        )
                    extent_raw = struct.unpack_from("<i", raw, 0x10)[0]
                    extent = _int_var(
                        extent_raw, integers, difficulty, rank, spawner.life
                    )
                    value = rng.u32_in_range(extent)
                    if instruction.opcode == OPCODE_SET_INT_RANDOM_MIN:
                        minimum_raw = struct.unpack_from("<i", raw, 0x14)[0]
                        value += _int_var(
                            minimum_raw, integers, difficulty, rank, spawner.life
                        )
                    if not _set_int_var(result, value, integers):
                        return EclForecast(
                            tuple(map(tuple, births)), frame_index, "unsupported random-int target"
                        )
                else:
                    extent = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    if rng is None:
                        if not abstract_rng:
                            return EclForecast(
                                tuple(map(tuple, births)),
                                frame_index,
                                "ECL random variable requires RNG state",
                            )
                        value = math.nan
                    else:
                        value = rng.f32_in_range(extent)
                        if instruction.opcode == OPCODE_SET_FLOAT_RANDOM_MIN:
                            value += _float_var(
                                raw[0x14:0x18], integers, floats, difficulty, rank,
                                spawner.life, enemy, variable_player,
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
                lhs = _int_var(lhs_raw, integers, difficulty, rank, spawner.life)
                rhs = _int_var(rhs_raw, integers, difficulty, rank, spawner.life)
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
                    target, integers, difficulty, rank, spawner.life
                )
                value += 1 if instruction.opcode == OPCODE_MATH_INCREMENT else -1
                if not _set_int_var(target, value, integers):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported increment target"
                    )
            elif instruction.opcode == OPCODE_MATH_FLOAT_ADD:
                target = struct.unpack_from("<i", raw, 0x0C)[0]
                lhs = _float_var(
                    raw[0x10:0x14], integers, floats, difficulty, rank,
                    spawner.life, enemy, variable_player,
                )
                rhs = _float_var(
                    raw[0x14:0x18], integers, floats, difficulty, rank,
                    spawner.life, enemy, variable_player,
                )
                if not _set_float_var(target, lhs + rhs, floats):
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "unsupported float-add target"
                    )
            elif instruction.opcode in (OPCODE_COMPARE_INT, OPCODE_COMPARE_FLOAT):
                if instruction.opcode == OPCODE_COMPARE_INT:
                    lhs_raw, rhs_raw = struct.unpack_from("<ii", raw, 0x0C)
                    lhs = _int_var(lhs_raw, integers, difficulty, rank, spawner.life)
                    rhs = _int_var(rhs_raw, integers, difficulty, rank, spawner.life)
                else:
                    lhs = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    rhs = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    if not math.isfinite(lhs) or not math.isfinite(rhs):
                        return EclForecast(
                            tuple(map(tuple, births)),
                            frame_index,
                            "future player dependency reaches ECL comparison",
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
            elif OPCODE_MOVE_POSITION <= instruction.opcode <= OPCODE_MOVE_AT_PLAYER:
                if instruction.opcode == OPCODE_MOVE_POSITION:
                    enemy_x = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                            spawner.life, enemy, variable_player,
                    )
                    enemy_y = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    enemy = (enemy_x, enemy_y)
                    stop_after_frame = "MOVEPOSITION needs uncaptured clamp bounds"
                elif instruction.opcode == OPCODE_MOVE_POSITION + 1:
                    velocity_x = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    velocity_y = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                            spawner.life, enemy, variable_player,
                    )
                    movement_mode = 0
                    uncertain_heading = False
                    velocity_uncertainty = 0.0
                elif instruction.opcode == OPCODE_MOVE_POSITION + 2:
                    angle = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    speed = _float_var(
                        raw[0x10:0x14], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    movement_mode = 1
                    if not math.isfinite(angle) and radial_births:
                        angle = 0.0
                        uncertain_heading = True
                    else:
                        uncertain_heading = False
                        velocity_uncertainty = 0.0
                elif instruction.opcode == OPCODE_MOVE_POSITION + 3:
                    angular_velocity = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    movement_mode = 1
                elif instruction.opcode == OPCODE_MOVE_POSITION + 4:
                    speed = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
                    )
                    movement_mode = 1
                elif instruction.opcode == OPCODE_MOVE_POSITION + 5:
                    acceleration = _float_var(
                        raw[0x0C:0x10], integers, floats, difficulty, rank,
                        spawner.life, enemy, variable_player,
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
                        stop_after_frame = "MOVERANDINBOUND needs uncaptured clamp bounds"
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
                        spawner.life, enemy, variable_player,
                    )
                    movement_mode = 1
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
            elif OPCODE_BULLET_FIRST <= instruction.opcode <= OPCODE_BULLET_LAST:
                try:
                    pattern = _resolved_pattern(
                        instruction,
                        spawner,
                        pattern,
                        integers,
                        floats,
                        difficulty,
                        rank,
                        spawner.life,
                        enemy,
                        variable_player,
                        bullet_sizes,
                        radial_births,
                    )
                    if not shooting_disabled:
                        births[frame_index].extend(emit(
                            pattern,
                            (
                                enemy[0] + spawner.shoot_offset_x,
                                enemy[1] + spawner.shoot_offset_y,
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
                interval_subframe = 0.0
            elif instruction.opcode == OPCODE_SHOOT_INTERVAL_DELAYED:
                return EclForecast(
                    tuple(map(tuple, births)), frame_index, "delayed interval requires future RNG"
                )
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
                            enemy[0] + spawner.shoot_offset_x,
                            enemy[1] + spawner.shoot_offset_y,
                        ),
                        player,
                    ))
                except UnsupportedBirthModel as error:
                    return EclForecast(tuple(map(tuple, births)), frame_index, str(error))
            elif instruction.opcode in (OPCODE_BULLET_SOUND, OPCODE_EFFECT_SOUND):
                pass
            else:
                return EclForecast(
                    tuple(map(tuple, births)),
                    frame_index,
                    f"unsupported ECL opcode {instruction.opcode}",
                )
            instruction_address = next_address
        else:
            return EclForecast(
                tuple(map(tuple, births)), frame_index, "ECL instruction budget exhausted"
            )

        motion = finish_motion(replace(
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
            move_timer=move_timer,
            move_timer_float=move_timer_float,
        ))
        enemy_x, enemy_y = motion.x, motion.y
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

        if spawner.life > 0 and interval > 0:
            interval_subframe += frame_multiplier
            while interval_subframe >= 1.0:
                interval_timer += 1
                interval_subframe -= 1.0
            if interval_timer >= interval:
                if pattern is None:
                    return EclForecast(
                        tuple(map(tuple, births)), frame_index, "periodic shooter has no resolved pattern"
                    )
                try:
                    births[frame_index].extend(emit(
                        pattern,
                        (
                            enemy[0] + spawner.shoot_offset_x,
                            enemy[1] + spawner.shoot_offset_y,
                        ),
                        player,
                    ))
                except UnsupportedBirthModel as error:
                    return EclForecast(tuple(map(tuple, births)), frame_index, str(error))
                interval_timer = 0
                interval_subframe = 0.0
        time_subframe += frame_multiplier
        while time_subframe >= 1.0:
            current_time += 1
            time_subframe -= 1.0
        if stop_after_frame:
            return EclForecast(
                tuple(map(tuple, births)), frame_index + 1, stop_after_frame
            )
    next_instruction = program.get(instruction_address)
    return EclForecast(
        tuple(map(tuple, births)),
        horizon,
        next_spawner=replace(
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
            move_timer=move_timer,
            move_timer_float=move_timer_float,
            shooting_disabled=shooting_disabled,
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
        ),
    )
