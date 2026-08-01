"""Cheap long-horizon laser proposal; never an action authority."""

from __future__ import annotations

import math
from dataclasses import replace

from .model import Action, Snapshot, action_from_input


LASER_EFFORT_HORIZON = 24
LASER_SPEED_HORIZON = 40


def needs_normal_speed(snapshot: Snapshot) -> bool:
    """Whether an active beam sweeps faster than focused tangential motion."""
    for laser in snapshot.lasers:
        if laser.state != 1 or abs(laser.angular_velocity) <= 1e-6:
            continue
        radius = math.hypot(snapshot.x - laser.x, snapshot.y - laser.y)
        future_end = laser.end_offset + max(0.0, laser.speed) * LASER_SPEED_HORIZON
        if radius < laser.start_offset or radius > future_end:
            continue
        if radius * abs(laser.angular_velocity) > snapshot.focus_speed + 0.1:
            return True
    return False


def needs_active_mixed_replan(snapshot: Snapshot, effort_horizon: int) -> bool:
    """Spend the long mixed budget only in the low-density active phase."""
    return (
        16 <= effort_horizon < LASER_EFFORT_HORIZON
        and any(
            laser.state == 1 and abs(laser.angular_velocity) > 1e-6
            for laser in snapshot.lasers
        )
    )


def isolate_lasers(snapshot: Snapshot) -> Snapshot:
    """Keep native timing/player state while removing non-laser work."""
    return replace(
        snapshot,
        bullets=(),
        enemies=(),
        despawning_bullets=(),
    )


def retained_current_corridor(
    snapshot: Snapshot,
    hard_actions: frozenset[Action],
    laser_survivors: frozenset[Action],
) -> Action | None:
    """Retain, but never enter, a long-lived laser corridor."""
    current = action_from_input(snapshot.input_mask)
    if current in hard_actions and current in laser_survivors:
        return current
    return None
