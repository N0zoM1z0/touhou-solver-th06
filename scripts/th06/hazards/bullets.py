"""Source-grounded future boxes for native TH06 bullets."""

from __future__ import annotations

import math

from ..model import Bullet, Snapshot
from .geometry import signed_clearance


DYNAMIC_EX_FLAGS = 0xDF1
ACCELERATION_FLAG = 0x10
CURVE_ACCELERATION_FLAG = 0x20
COMPLEX_MOTION_FLAGS = 0xDE1
DIRECTION_ROTATION_FLAG = 0x40


def _direction_rotation_positions(
    bullet: Bullet,
    horizon: int,
) -> list[tuple[float, float]]:
    """Reproduce the source's timed 0x40 decelerate-and-rotate update."""
    x, y = bullet.x, bullet.y
    vx, vy = bullet.vx, bullet.vy
    angle = bullet.angle
    speed = bullet.speed
    timer = bullet.timer
    timer_float = bullet.timer_float
    direction_num_times = bullet.direction_num_times
    flags = bullet.ex_flags
    cosine = math.cos(angle)
    sine = math.sin(angle)
    result = []
    for _ in range(horizon):
        if flags & DIRECTION_ROTATION_FLAG:
            if timer >= bullet.direction_interval * (direction_num_times + 1):
                direction_num_times += 1
                if direction_num_times >= bullet.direction_max_times:
                    flags &= ~DIRECTION_ROTATION_FLAG
                angle += bullet.direction_rotation
                cosine = math.cos(angle)
                sine = math.sin(angle)
                speed = bullet.turn_speed
                bullet_speed = speed
            else:
                phase = timer_float - bullet.direction_interval * direction_num_times
                bullet_speed = speed - phase * speed / bullet.direction_interval
            vx = cosine * bullet_speed
            vy = sine * bullet_speed
        x += vx
        y += vy
        timer += 1
        timer_float += 1.0
        result.append((x, y))
    return result


def _direction_rotation_position(bullet: Bullet, frame: int) -> tuple[float, float]:
    return _direction_rotation_positions(bullet, frame)[-1]


def _curve_acceleration_positions(
    bullet: Bullet,
    horizon: int,
) -> list[tuple[float, float]]:
    """Reproduce source flag 0x20 angular and speed acceleration."""
    x, y = bullet.x, bullet.y
    vx, vy = bullet.vx, bullet.vy
    angle = bullet.angle
    speed = bullet.speed
    timer = bullet.timer
    active = True
    result = []
    for _ in range(horizon):
        if active:
            if timer >= bullet.acceleration_duration:
                active = False
            else:
                angle += bullet.curve_angular_velocity
                speed += bullet.curve_speed_acceleration
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed
        x += vx
        y += vy
        timer += 1
        result.append((x, y))
    return result


def _curve_acceleration_position(bullet: Bullet, frame: int) -> tuple[float, float]:
    return _curve_acceleration_positions(bullet, frame)[-1]


def hazard_box(bullet: Bullet, frame: int) -> tuple[float, float, float, float]:
    if (
        bullet.state == 1
        and bullet.ex_flags & DIRECTION_ROTATION_FLAG
        and not bullet.ex_flags & (COMPLEX_MOTION_FLAGS & ~DIRECTION_ROTATION_FLAG)
    ):
        x, y = _direction_rotation_position(bullet, frame)
        return (
            x - bullet.half_width,
            y - bullet.half_height,
            x + bullet.half_width,
            y + bullet.half_height,
        )
    if (
        bullet.state == 1
        and bullet.ex_flags & ACCELERATION_FLAG
        and not bullet.ex_flags & COMPLEX_MOTION_FLAGS
        and bullet.acceleration_duration > 0
    ):
        # BulletManager::OnUpdate applies ex4Acceleration before position only
        # while timer.current < ex5Int0. Spawn-effect bits are inert once fired.
        applications = min(
            frame,
            max(0, bullet.acceleration_duration - bullet.timer),
        )
        acceleration_factor = (
            applications * frame - applications * (applications - 1) / 2.0
        )
        x = bullet.x + bullet.vx * frame + bullet.acceleration_x * acceleration_factor
        y = bullet.y + bullet.vy * frame + bullet.acceleration_y * acceleration_factor
        return (
            x - bullet.half_width,
            y - bullet.half_height,
            x + bullet.half_width,
            y + bullet.half_height,
        )
    if (
        bullet.state == 1
        and bullet.ex_flags & CURVE_ACCELERATION_FLAG
        and not bullet.ex_flags & (COMPLEX_MOTION_FLAGS & ~CURVE_ACCELERATION_FLAG)
    ):
        x, y = _curve_acceleration_position(bullet, frame)
        return (
            x - bullet.half_width,
            y - bullet.half_height,
            x + bullet.half_width,
            y + bullet.half_height,
        )
    if bullet.ex_flags & DYNAMIC_EX_FLAGS:
        # Extended bullets may accelerate, turn, home, or bounce, but do not
        # teleport. Cover every direction using the source-visible speed fields.
        base_speed = max(math.hypot(bullet.vx, bullet.vy), abs(bullet.speed), abs(bullet.turn_speed))
        reach = (base_speed + 5.0) * frame + 0.5 * abs(bullet.acceleration) * frame * frame
        return (
            bullet.x - bullet.half_width - reach,
            bullet.y - bullet.half_height - reach,
            bullet.x + bullet.half_width + reach,
            bullet.y + bullet.half_height + reach,
        )

    if bullet.state == 1:
        minimum_factor = 1.0
    elif bullet.state == 2:
        minimum_factor = 0.5
    elif bullet.state == 3:
        minimum_factor = 0.4
    else:
        minimum_factor = 1.0 / 3.0
    x0 = bullet.x + bullet.vx * frame * minimum_factor
    y0 = bullet.y + bullet.vy * frame * minimum_factor
    x1 = bullet.x + bullet.vx * frame
    y1 = bullet.y + bullet.vy * frame
    return (
        min(x0, x1) - bullet.half_width,
        min(y0, y1) - bullet.half_height,
        max(x0, x1) + bullet.half_width,
        max(y0, y1) + bullet.half_height,
    )


def radial_hazard_box(
    bullet: Bullet,
    frame: int,
) -> tuple[float, float, float, float]:
    """Enclose a newborn bullet without assuming its future aim angle."""
    base_speed = max(
        math.hypot(bullet.vx, bullet.vy),
        abs(bullet.speed),
        abs(bullet.turn_speed),
    )
    acceleration = max(
        abs(bullet.acceleration),
        math.hypot(bullet.acceleration_x, bullet.acceleration_y),
        abs(bullet.curve_speed_acceleration),
    )
    reach = base_speed * frame + acceleration * frame * (frame + 1) / 2.0
    if bullet.ex_flags & (DYNAMIC_EX_FLAGS & ~(
        ACCELERATION_FLAG | CURVE_ACCELERATION_FLAG | DIRECTION_ROTATION_FLAG
    )):
        # Source-visible extended modes may turn, home, or bounce. The existing
        # hard model bounds those modes by five extra pixels per update.
        reach += 5.0 * frame
    return (
        bullet.x - bullet.half_width - reach,
        bullet.y - bullet.half_height - reach,
        bullet.x + bullet.half_width + reach,
        bullet.y + bullet.half_height + reach,
    )


def _hazard_boxes(
    bullet: Bullet,
    horizon: int,
) -> list[tuple[float, float, float, float]]:
    """Project one bullet once while preserving ``hazard_box`` semantics."""
    state = bullet.state
    flags = bullet.ex_flags
    half_width = bullet.half_width
    half_height = bullet.half_height
    if (
        state == 1
        and flags & DIRECTION_ROTATION_FLAG
        and not flags & (COMPLEX_MOTION_FLAGS & ~DIRECTION_ROTATION_FLAG)
    ):
        return [
            (x - half_width, y - half_height, x + half_width, y + half_height)
            for x, y in _direction_rotation_positions(bullet, horizon)
        ]
    if (
        state == 1
        and flags & CURVE_ACCELERATION_FLAG
        and not flags & (COMPLEX_MOTION_FLAGS & ~CURVE_ACCELERATION_FLAG)
    ):
        return [
            (x - half_width, y - half_height, x + half_width, y + half_height)
            for x, y in _curve_acceleration_positions(bullet, horizon)
        ]
    frames = range(1, horizon + 1)
    if (
        state == 1
        and flags & ACCELERATION_FLAG
        and not flags & COMPLEX_MOTION_FLAGS
        and bullet.acceleration_duration > 0
    ):
        remaining = max(0, bullet.acceleration_duration - bullet.timer)
        boxes = []
        for frame in frames:
            applications = min(frame, remaining)
            factor = (
                applications * frame - applications * (applications - 1) / 2.0
            )
            x = bullet.x + bullet.vx * frame + bullet.acceleration_x * factor
            y = bullet.y + bullet.vy * frame + bullet.acceleration_y * factor
            boxes.append((
                x - half_width,
                y - half_height,
                x + half_width,
                y + half_height,
            ))
        return boxes
    if flags & DYNAMIC_EX_FLAGS:
        base_speed = max(
            math.hypot(bullet.vx, bullet.vy),
            abs(bullet.speed),
            abs(bullet.turn_speed),
        )
        acceleration = abs(bullet.acceleration)
        boxes = []
        for frame in frames:
            reach = (base_speed + 5.0) * frame + 0.5 * acceleration * frame * frame
            boxes.append((
                bullet.x - half_width - reach,
                bullet.y - half_height - reach,
                bullet.x + half_width + reach,
                bullet.y + half_height + reach,
            ))
        return boxes
    if state == 1:
        x = bullet.x
        y = bullet.y
        vx = bullet.vx
        vy = bullet.vy
        return [
            (
                x + vx * frame - half_width,
                y + vy * frame - half_height,
                x + vx * frame + half_width,
                y + vy * frame + half_height,
            )
            for frame in frames
        ]
    if state == 2:
        minimum_factor = 0.5
    elif state == 3:
        minimum_factor = 0.4
    else:
        minimum_factor = 1.0 / 3.0
    boxes = []
    for frame in frames:
        x0 = bullet.x + bullet.vx * frame * minimum_factor
        y0 = bullet.y + bullet.vy * frame * minimum_factor
        x1 = bullet.x + bullet.vx * frame
        y1 = bullet.y + bullet.vy * frame
        boxes.append((
            min(x0, x1) - half_width,
            min(y0, y1) - half_height,
            max(x0, x1) + half_width,
            max(y0, y1) + half_height,
        ))
    return boxes


def hazards_by_frame(snapshot: Snapshot, horizon: int) -> list[tuple[tuple[float, float, float, float], ...]]:
    frames: list[list[tuple[float, float, float, float]]] = [
        [] for _ in range(horizon)
    ]
    for bullet in snapshot.bullets:
        for frame, box in zip(frames, _hazard_boxes(bullet, horizon)):
            frame.append(box)
    return [tuple(frame) for frame in frames]


def nearest_current_clearance(snapshot: Snapshot) -> float:
    nearest = 999.0
    for bullet in snapshot.bullets:
        hazard = (
            bullet.x - bullet.half_width,
            bullet.y - bullet.half_height,
            bullet.x + bullet.half_width,
            bullet.y + bullet.half_height,
        )
        nearest = min(
            nearest,
            signed_clearance(snapshot.x, snapshot.y, snapshot.half_width, snapshot.half_height, hazard),
        )
    return nearest
