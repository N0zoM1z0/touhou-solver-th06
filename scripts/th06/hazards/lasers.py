"""Exact TH06 laser phase, segment, and rotated hitbox model."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..model import Laser
from .geometry import signed_clearance


@dataclass(frozen=True)
class LaserHazard:
    origin_x: float
    origin_y: float
    angle: float
    center_offset: float
    size_x: float
    size_y: float


def _geometry(
    laser: Laser,
    start_offset: float,
    end_offset: float,
    size_x: float,
) -> LaserHazard:
    return LaserHazard(
        laser.x,
        laser.y,
        laser.angle,
        (end_offset - start_offset) / 2.0 + start_offset,
        max(0.0, size_x),
        laser.width / 2.0,
    )


def future_hazards(laser: Laser, horizon: int) -> list[tuple[LaserHazard, ...]]:
    start_offset = laser.start_offset
    end_offset = laser.end_offset
    state = laser.state
    timer = laser.timer
    timer_float = laser.timer_float
    active = True
    result: list[tuple[LaserHazard, ...]] = []

    for _frame in range(horizon):
        if not active:
            result.append(())
            continue
        end_offset += laser.speed
        if laser.start_length < end_offset - start_offset:
            start_offset = end_offset - laser.start_length
        start_offset = max(0.0, start_offset)
        full_length = max(0.0, end_offset - start_offset)
        frame_hazards: list[LaserHazard] = []
        state_one_size_x = full_length

        if state == 0:
            if laser.flags & 1:
                size_x = full_length
            else:
                res = min(laser.start_time, 30)
                if laser.start_time - res < timer:
                    width_now = timer_float * laser.width / max(1, laser.start_time)
                else:
                    width_now = 1.2
                # Shipped bug: BulletManager assigns this to laserSize.x,
                # producing a small midpoint hitbox during warmup.
                size_x = width_now / 2.0
            if timer >= laser.hitbox_start_time:
                frame_hazards.append(_geometry(laser, start_offset, end_offset, size_x))
            if timer >= laser.start_time:
                state = 1
                timer = 0
                timer_float = 0.0
                # Shipped switch fallthrough does not restore the full length
                # after the warmup branch overwrites laserSize.x.
                state_one_size_x = size_x
            else:
                timer += 1
                timer_float += 1.0
                result.append(tuple(frame_hazards))
                continue

        if state == 1:
            frame_hazards.append(_geometry(laser, start_offset, end_offset, state_one_size_x))
            if timer >= laser.duration:
                state = 2
                timer = 0
                timer_float = 0.0
                if laser.despawn_duration == 0:
                    active = False

        if state == 2 and active:
            if laser.flags & 1:
                size_x = full_length
            else:
                width_now = laser.width
                if laser.despawn_duration > 0:
                    width_now -= timer_float * laser.width / laser.despawn_duration
                # Same shipped midpoint-hitbox bug during despawn.
                size_x = width_now / 2.0
            if timer < laser.hitbox_end_delay:
                frame_hazards.append(_geometry(laser, start_offset, end_offset, size_x))
            if timer >= laser.despawn_duration:
                active = False

        if start_offset >= 640.0:
            active = False
        if active:
            timer += 1
            timer_float += 1.0
        result.append(tuple(frame_hazards))
    return result


def hazards_by_frame(lasers: tuple[Laser, ...], horizon: int) -> list[tuple[LaserHazard, ...]]:
    frames: list[list[LaserHazard]] = [[] for _ in range(horizon)]
    for laser in lasers:
        for index, hazards in enumerate(future_hazards(laser, horizon)):
            frames[index].extend(hazards)
    return [tuple(frame) for frame in frames]


def signed_laser_clearance(
    player_x: float,
    player_y: float,
    player_half_width: float,
    player_half_height: float,
    laser: LaserHazard,
) -> float:
    dx = player_x - laser.origin_x
    dy = player_y - laser.origin_y
    sine = math.sin(laser.angle)
    cosine = math.cos(laser.angle)
    local_x = cosine * dx + sine * dy
    local_y = cosine * dy - sine * dx
    hazard = (
        laser.center_offset - laser.size_x / 2.0,
        -laser.size_y / 2.0,
        laser.center_offset + laser.size_x / 2.0,
        laser.size_y / 2.0,
    )
    return signed_clearance(
        local_x, local_y, player_half_width, player_half_height, hazard
    )
