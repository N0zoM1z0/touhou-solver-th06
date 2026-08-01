"""Source-grounded future boxes for native TH06 bullets."""

from __future__ import annotations

import math

from ..model import Bullet, Snapshot
from .geometry import signed_clearance


DYNAMIC_EX_FLAGS = 0xDF1
ACCELERATION_FLAG = 0x10
COMPLEX_MOTION_FLAGS = 0xDE1


def hazard_box(bullet: Bullet, frame: int) -> tuple[float, float, float, float]:
    if (
        bullet.state == 1
        and bullet.ex_flags & ACCELERATION_FLAG
        and not bullet.ex_flags & COMPLEX_MOTION_FLAGS
    ):
        # BulletManager::OnUpdate adds one fixed ex4Acceleration vector before
        # position, until an internal timer clears 0x10. The timer is not yet
        # sensed, so enumerate every possible number of future acceleration
        # applications. Spawn-effect bits 0x2/0x4/0x8 are inert once fired.
        positions = []
        for applications in range(frame + 1):
            acceleration_factor = (
                applications * frame - applications * (applications - 1) / 2.0
            )
            positions.append(
                (
                    bullet.x + bullet.vx * frame + bullet.acceleration_x * acceleration_factor,
                    bullet.y + bullet.vy * frame + bullet.acceleration_y * acceleration_factor,
                )
            )
        return (
            min(x for x, _y in positions) - bullet.half_width,
            min(y for _x, y in positions) - bullet.half_height,
            max(x for x, _y in positions) + bullet.half_width,
            max(y for _x, y in positions) + bullet.half_height,
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


def hazards_by_frame(snapshot: Snapshot, horizon: int) -> list[tuple[tuple[float, float, float, float], ...]]:
    return [
        tuple(hazard_box(bullet, frame) for bullet in snapshot.bullets)
        for frame in range(1, horizon + 1)
    ]


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
