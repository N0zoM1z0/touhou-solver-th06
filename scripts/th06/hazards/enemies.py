"""Source-grounded current-body motion and collision boxes."""

from __future__ import annotations

import math
from typing import Protocol

from ..model import EnemyBody


class MovingEnemy(Protocol):
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


def _ease(value: float, mode: int) -> float:
    if mode == 0:
        return 1.0 - value
    if mode == 1:
        return 1.0 - value * value
    if mode == 2:
        return 1.0 - value * value * value * value
    if mode == 3:
        value = 1.0 - value
        return value * value
    if mode == 4:
        value = 1.0 - value
        return value * value * value * value
    raise ValueError(f"unsupported enemy movement ease {mode}")


def future_positions(
    enemy: MovingEnemy,
    horizon: int,
) -> list[tuple[float, float]]:
    """Follow Enemy::Move and the source's no-instruction motion update."""
    x = enemy.x
    y = enemy.y
    velocity_x = enemy.velocity_x
    velocity_y = enemy.velocity_y
    angle = enemy.angle
    speed = enemy.speed
    movement_mode = enemy.movement_mode
    move_timer = enemy.move_timer
    move_timer_float = enemy.move_timer_float
    result: list[tuple[float, float]] = []

    for _frame in range(horizon):
        x += -velocity_x if enemy.invert_x else velocity_x
        y += velocity_y

        if movement_mode == 1:
            angle += enemy.angular_velocity
            speed += enemy.acceleration
            velocity_x = math.cos(angle) * speed
            velocity_y = math.sin(angle) * speed
        elif movement_mode == 2:
            move_timer -= 1
            move_timer_float -= 1.0
            if enemy.move_start_time <= 0:
                raise ValueError("invalid active enemy interpolation time")
            interpolation = min(1.0, move_timer_float / enemy.move_start_time)
            interpolation = _ease(interpolation, enemy.movement_ease)
            velocity_x = interpolation * enemy.move_interp_x + enemy.move_start_x - x
            velocity_y = interpolation * enemy.move_interp_y + enemy.move_start_y - y
            if move_timer <= 0:
                movement_mode = 0
                x = enemy.move_start_x + enemy.move_interp_x
                y = enemy.move_start_y + enemy.move_interp_y
                velocity_x = 0.0
                velocity_y = 0.0
        result.append((x, y))
    return result


def future_boxes(
    enemy: EnemyBody,
    horizon: int,
) -> list[tuple[float, float, float, float]]:
    return [
        (
            x - enemy.half_width,
            y - enemy.half_height,
            x + enemy.half_width,
            y + enemy.half_height,
        )
        for x, y in future_positions(enemy, horizon)
    ]


def hazards_by_frame(
    enemies: tuple[EnemyBody, ...],
    horizon: int,
) -> list[tuple[tuple[float, float, float, float], ...]]:
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in range(horizon)
    ]
    for enemy in enemies:
        for index, hazard in enumerate(future_boxes(enemy, horizon)):
            frames[index].append(hazard)
    return [tuple(frame) for frame in frames]
