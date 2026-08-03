"""Synchronous global-target/local-path proposal values."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import ctypes
import math

from .hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from .hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from .hazards.geometry import signed_clearance
from .hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from .hazards.lasers import signed_laser_clearance
from .hazards.world import forecast_world_births
from .model import ACTIONS, Action, SafeAction, Snapshot, action_from_input
from .safety import (
    COLLISION_MARGIN,
    DELIVERY_DELAYS,
    _step_player,
    transition_actions,
)


@dataclass(frozen=True)
class TerminalGuidance:
    """Proposal-only terminal value for one Hard-certified first action."""

    terminal_count: int
    free_clearance: float
    free_x: float
    free_y: float
    target_distance_squared: float


def preferred_target_actions(
    guidance: dict[Action, TerminalGuidance],
    allowed: frozenset[Action],
) -> frozenset[Action]:
    """Keep maximum robust optionality, then approach the soft target."""
    reachable = {
        action: value
        for action, value in guidance.items()
        if (
            action in allowed
            and value.terminal_count > 0
            and math.isfinite(value.target_distance_squared)
        )
    }
    if not reachable:
        return frozenset()
    best_count = max(value.terminal_count for value in reachable.values())
    robust = {
        action: value
        for action, value in reachable.items()
        if value.terminal_count == best_count
    }
    best_distance = min(
        value.target_distance_squared for value in robust.values()
    )
    return frozenset(
        action
        for action, value in robust.items()
        if value.target_distance_squared == best_distance
    )


def terminal_guidance_scores(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    segment_length: int,
    horizon: int,
    target: tuple[float, float] | None = None,
    continuation_length: int | None = None,
) -> dict[Action, TerminalGuidance]:
    """Deduplicate nominal terminal positions behind each Hard first action."""
    if segment_length <= 0 or horizon < segment_length:
        raise ValueError("terminal guidance horizon must cover one segment")
    if continuation_length is None:
        continuation_length = segment_length
    if continuation_length <= 0:
        raise ValueError("continuation length must be positive")
    bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
    enemy_frames = enemy_hazards_by_frame(snapshot.enemies, horizon)
    laser_frames = laser_hazards_by_frame(snapshot.lasers, horizon)
    hard_births = forecast_world_births(
        snapshot, ((snapshot.x, snapshot.y),) * min(4, horizon)
    )
    nominal_births = forecast_world_births(
        snapshot,
        ((snapshot.x, snapshot.y),) * horizon,
        rng_mode="nominal",
    )
    uncovered = ((-10000.0, -10000.0, 10000.0, 10000.0),)
    aabb_frames = []
    for index in range(horizon):
        if index < 4:
            births = (
                hard_births.hazards[index]
                if index < hard_births.covered_frames
                else uncovered
            )
            bodies = (
                hard_births.body_hazards[index]
                if index < hard_births.covered_frames
                and hard_births.body_hazards
                else uncovered
            )
        else:
            births = (
                nominal_births.hazards[index]
                if index < nominal_births.covered_frames
                else ()
            )
            bodies = (
                nominal_births.body_hazards[index]
                if index < nominal_births.covered_frames
                and nominal_births.body_hazards
                else ()
            )
        aabb_frames.append(
            bullet_frames[index] + enemy_frames[index] + births + bodies
        )

    @lru_cache(maxsize=None)
    def safe_at(x: float, y: float, frame_index: int) -> bool:
        if any(
            signed_clearance(
                x,
                y,
                snapshot.half_width,
                snapshot.half_height,
                hazard,
            ) <= COLLISION_MARGIN
            for hazard in aabb_frames[frame_index]
        ):
            return False
        return not any(
            signed_laser_clearance(
                x,
                y,
                snapshot.half_width,
                snapshot.half_height,
                laser,
            ) <= COLLISION_MARGIN
            for laser in laser_frames[frame_index]
        )

    def step(x: float, y: float, action: Action) -> tuple[float, float]:
        next_x, next_y = _step_player(
            x,
            y,
            action,
            snapshot.focus_speed if action.focused else snapshot.normal_speed,
            (
                snapshot.focus_diagonal_speed
                if action.focused
                else snapshot.normal_diagonal_speed
            ),
        )
        return ctypes.c_float(next_x).value, ctypes.c_float(next_y).value

    @lru_cache(maxsize=None)
    def terminal_stats(start_x: float, start_y: float) -> TerminalGuidance:
        states = {(start_x, start_y)}
        for start_frame in range(
            segment_length, horizon, continuation_length
        ):
            end_frame = min(horizon, start_frame + continuation_length)
            next_states = set()
            for state_x, state_y in states:
                for action in ACTIONS:
                    x, y = state_x, state_y
                    for frame in range(start_frame + 1, end_frame + 1):
                        x, y = step(x, y, action)
                        if not safe_at(x, y, frame - 1):
                            break
                    else:
                        next_states.add((x, y))
            states = next_states
            if not states:
                break
        if not states:
            return TerminalGuidance(
                0, -math.inf, start_x, start_y, math.inf
            )

        free_clearance = -math.inf
        free_x, free_y = start_x, start_y
        target_distance_squared = math.inf
        terminal_frame = horizon - 1
        for x, y in states:
            clearance = min(x - 8.0, 376.0 - x, y - 16.0, 432.0 - y)
            for hazard in aabb_frames[terminal_frame]:
                clearance = min(
                    clearance,
                    signed_clearance(
                        x,
                        y,
                        snapshot.half_width,
                        snapshot.half_height,
                        hazard,
                    ),
                )
            for laser in laser_frames[terminal_frame]:
                clearance = min(
                    clearance,
                    signed_laser_clearance(
                        x,
                        y,
                        snapshot.half_width,
                        snapshot.half_height,
                        laser,
                    ),
                )
            if clearance > free_clearance:
                free_clearance = clearance
                free_x, free_y = x, y
            if target is not None:
                target_distance_squared = min(
                    target_distance_squared,
                    (x - target[0]) ** 2 + (y - target[1]) ** 2,
                )
        return TerminalGuidance(
            len(states),
            free_clearance,
            free_x,
            free_y,
            target_distance_squared,
        )

    current = action_from_input(snapshot.input_mask)
    result = {}
    for candidate in candidates:
        prefixes = transition_actions(current, candidate.action)
        worst_count = (1 << 31) - 1
        worst_free = math.inf
        worst_free_x, worst_free_y = snapshot.x, snapshot.y
        worst_distance = 0.0
        for delay in DELIVERY_DELAYS:
            branches = (None,) + prefixes if delay > 0 else (None,)
            for prefix in branches:
                x, y = snapshot.x, snapshot.y
                survived = True
                for frame in range(1, segment_length + 1):
                    if prefix is not None and frame == delay:
                        action = prefix
                    elif frame < delay or (prefix is None and frame <= delay):
                        action = current
                    else:
                        action = candidate.action
                    x, y = step(x, y, action)
                    if not safe_at(x, y, frame - 1):
                        survived = False
                        break
                branch = (
                    terminal_stats(x, y)
                    if survived
                    else TerminalGuidance(
                        0, -math.inf, x, y, math.inf
                    )
                )
                worst_count = min(worst_count, branch.terminal_count)
                if branch.free_clearance < worst_free:
                    worst_free = branch.free_clearance
                    worst_free_x, worst_free_y = branch.free_x, branch.free_y
                worst_distance = max(
                    worst_distance, branch.target_distance_squared
                )
        result[candidate.action] = TerminalGuidance(
            0 if worst_count == (1 << 31) - 1 else worst_count,
            worst_free,
            worst_free_x,
            worst_free_y,
            worst_distance,
        )
    return result


def terminal_reachability_counts(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    segment_length: int,
    horizon: int,
) -> dict[Action, int]:
    """Count exact terminal states after frame-granular continuation.

    The first segment retains every physical delivery/transition branch.
    Later frames use a proposal-only nominal focused choice at each frame,
    avoiding a replanning-relative turn grid. Every physical publication still
    requires fresh Hard delivery authority in the online solver.
    """
    guidance = terminal_guidance_scores(
        snapshot,
        candidates,
        segment_length,
        horizon,
        continuation_length=1,
    )
    return {
        action: value.terminal_count
        for action, value in guidance.items()
    }
