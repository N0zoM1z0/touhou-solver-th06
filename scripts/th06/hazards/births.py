"""Source-exact deterministic periodic bullet births.

This module models only the resolved ``EnemyBulletShooter`` state already
stored on a live enemy. Future ECL instructions and RNG aim modes are not
silently guessed; callers can distinguish those unsupported cases before
using a long-horizon result.
"""

from __future__ import annotations

import math

from ..model import Bullet, BulletPattern, EnemySpawner
from .bullets import hazard_box
from .enemies import future_positions
from .rng import RngState


FAN_AIMED = 0
FAN = 1
CIRCLE_AIMED = 2
CIRCLE = 3
OFFSET_CIRCLE_AIMED = 4
OFFSET_CIRCLE = 5
RANDOM_ANGLE = 6
RANDOM_SPEED = 7
RANDOM = 8
DETERMINISTIC_AIM_MODES = frozenset(range(FAN_AIMED, OFFSET_CIRCLE + 1))


class UnsupportedBirthModel(ValueError):
    pass


def _normalize_angle(angle: float) -> float:
    return math.remainder(angle, math.tau)


def _pattern_angle(
    pattern: BulletPattern,
    index1: int,
    index2: int,
    aimed_angle: float,
) -> float:
    if pattern.aim_mode in (FAN_AIMED, FAN):
        if pattern.count1 & 1:
            angle = ((index1 + 1) // 2) * pattern.angle2
        else:
            angle = (index1 // 2) * pattern.angle2 + pattern.angle2 * 0.5
        if index1 & 1:
            angle = -angle
        if pattern.aim_mode == FAN_AIMED:
            angle += aimed_angle
        return _normalize_angle(angle + pattern.angle1)
    if pattern.aim_mode in (CIRCLE_AIMED, CIRCLE):
        angle = index1 * math.tau / pattern.count1
        angle += index2 * pattern.angle2 + pattern.angle1
        if pattern.aim_mode == CIRCLE_AIMED:
            angle += aimed_angle
        return _normalize_angle(angle)
    if pattern.aim_mode in (OFFSET_CIRCLE_AIMED, OFFSET_CIRCLE):
        angle = math.pi / pattern.count1
        angle += index1 * math.tau / pattern.count1 + pattern.angle1
        if pattern.aim_mode == OFFSET_CIRCLE_AIMED:
            angle += aimed_angle
        return _normalize_angle(angle)
    raise UnsupportedBirthModel(
        f"aim mode {pattern.aim_mode} requires future RNG state"
    )


def _spawned_bullet(
    pattern: BulletPattern,
    origin_x: float,
    origin_y: float,
    angle: float,
    speed: float,
) -> Bullet:
    acceleration_x = 0.0
    acceleration_y = 0.0
    acceleration_duration = 0
    curve_speed = 0.0
    curve_angular = 0.0
    turn_speed = 0.0
    direction_rotation = 0.0
    direction_interval = 0
    direction_max_times = 0
    if pattern.flags & 0x10:
        acceleration_angle = (
            angle if pattern.ex_floats[1] <= -999.0 else pattern.ex_floats[1]
        )
        acceleration_x = math.cos(acceleration_angle) * pattern.ex_floats[0]
        acceleration_y = math.sin(acceleration_angle) * pattern.ex_floats[0]
        acceleration_duration = (
            pattern.ex_ints[0] if pattern.ex_ints[0] > 0 else 99999
        )
    elif pattern.flags & 0x20:
        curve_speed = pattern.ex_floats[0]
        curve_angular = pattern.ex_floats[1]
        acceleration_duration = pattern.ex_ints[0]
    if pattern.flags & 0x1C0:
        direction_rotation = pattern.ex_floats[0]
        turn_speed = (
            pattern.ex_floats[1] if pattern.ex_floats[1] >= 0.0 else speed
        )
        direction_interval = pattern.ex_ints[0]
        direction_max_times = pattern.ex_ints[1]
    elif pattern.flags & 0xC00:
        turn_speed = pattern.ex_floats[0] if pattern.ex_floats[0] >= 0.0 else speed
        direction_max_times = pattern.ex_ints[0]
    state = 2 if pattern.flags & 0x02 else 3 if pattern.flags & 0x04 else 4 if pattern.flags & 0x08 else 1
    return Bullet(
        origin_x,
        origin_y,
        math.cos(angle) * speed,
        math.sin(angle) * speed,
        pattern.half_width,
        pattern.half_height,
        state,
        ex_flags=pattern.flags,
        speed=speed,
        turn_speed=turn_speed,
        acceleration_x=acceleration_x,
        acceleration_y=acceleration_y,
        angle=angle,
        direction_rotation=direction_rotation,
        acceleration_duration=acceleration_duration,
        direction_interval=direction_interval,
        direction_max_times=direction_max_times,
        curve_speed_acceleration=curve_speed,
        curve_angular_velocity=curve_angular,
    )


def spawn_pattern(
    pattern: BulletPattern,
    origin: tuple[float, float],
    player: tuple[float, float],
    rng: RngState | None = None,
) -> tuple[Bullet, ...]:
    """Reproduce SpawnBulletPattern, requiring explicit state for RNG modes."""
    if pattern.aim_mode not in DETERMINISTIC_AIM_MODES and rng is None:
        raise UnsupportedBirthModel(
            f"aim mode {pattern.aim_mode} requires future RNG state"
        )
    if pattern.count1 <= 0 or pattern.count2 <= 0:
        raise ValueError("resolved bullet counts must be positive")
    origin_x, origin_y = origin
    aimed_angle = math.atan2(player[1] - origin_y, player[0] - origin_x)
    bullets = []
    for index2 in range(pattern.count2):
        # The shipped source divides by count2, not count2 - 1.
        speed = pattern.speed1 - (
            (pattern.speed1 - pattern.speed2) * index2 / pattern.count2
        )
        for index1 in range(pattern.count1):
            if pattern.aim_mode == RANDOM_ANGLE:
                assert rng is not None
                angle = rng.f32_in_range(
                    pattern.angle1 - pattern.angle2
                ) + pattern.angle2
            elif pattern.aim_mode == RANDOM_SPEED:
                assert rng is not None
                speed = rng.f32_in_range(
                    pattern.speed1 - pattern.speed2
                ) + pattern.speed2
                angle = (
                    index1 * math.tau / pattern.count1
                    + index2 * pattern.angle2
                    + pattern.angle1
                )
            elif pattern.aim_mode == RANDOM:
                assert rng is not None
                angle = rng.f32_in_range(
                    pattern.angle1 - pattern.angle2
                ) + pattern.angle2
                speed = rng.f32_in_range(
                    pattern.speed1 - pattern.speed2
                ) + pattern.speed2
            else:
                angle = _pattern_angle(
                    pattern, index1, index2, aimed_angle
                )
            angle = _normalize_angle(angle)
            bullets.append(
                _spawned_bullet(pattern, origin_x, origin_y, angle, speed)
            )
    return tuple(bullets)


def periodic_births(
    spawner: EnemySpawner,
    player_positions: tuple[tuple[float, float], ...],
    frame_multiplier: float = 1.0,
) -> tuple[tuple[Bullet, ...], ...]:
    """Return bullets born on each future EnemyManager update."""
    horizon = len(player_positions)
    if (
        spawner.life <= 0
        or spawner.shooting_disabled
        or spawner.interval <= 0
    ):
        return ((),) * horizon
    if spawner.pattern is None:
        raise UnsupportedBirthModel("active periodic shooter has no bullet pattern")
    enemy_positions = future_positions(spawner, horizon)
    timer = spawner.timer
    subframe = spawner.timer_float - spawner.timer
    result: list[tuple[Bullet, ...]] = []
    for index, player in enumerate(player_positions):
        subframe += frame_multiplier
        while subframe >= 1.0:
            timer += 1
            subframe -= 1.0
        if timer >= spawner.interval:
            enemy_x, enemy_y = enemy_positions[index]
            result.append(spawn_pattern(
                spawner.pattern,
                (
                    enemy_x + spawner.shoot_offset_x,
                    enemy_y + spawner.shoot_offset_y,
                ),
                player,
            ))
            timer = 0
            subframe = 0.0
        else:
            result.append(())
    return tuple(result)


def periodic_hazards_by_frame(
    spawners: tuple[EnemySpawner, ...],
    player_positions: tuple[tuple[float, float], ...],
    frame_multiplier: float = 1.0,
) -> tuple[tuple[tuple[float, float, float, float], ...], ...]:
    """Project born bullets, including their source-defined spawn movement."""
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in player_positions
    ]
    for spawner in spawners:
        births = periodic_births(spawner, player_positions, frame_multiplier)
        for birth_index, bullets in enumerate(births):
            for frame_index in range(birth_index, len(frames)):
                age = frame_index - birth_index + 1
                frames[frame_index].extend(
                    hazard_box(bullet, age) for bullet in bullets
                )
    return tuple(tuple(frame) for frame in frames)
