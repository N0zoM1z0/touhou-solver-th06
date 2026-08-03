"""Soft two-segment viability scores; never an action authority."""

from __future__ import annotations

from functools import lru_cache

from .hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from .hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from .hazards.geometry import signed_clearance
from .hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from .hazards.lasers import signed_laser_clearance
from .hazards.world import forecast_world_births
from .model import (
    ACTIONS,
    Action,
    SafeAction,
    Snapshot,
    action_from_input,
)
from .safety import (
    COLLISION_MARGIN,
    DELIVERY_DELAYS,
    _step_player,
    candidate_paths,
    transition_actions,
)


_MAX_POLICY_VOLUME = (1 << 31) - 1


def nominal_policy_scores(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    segment_length: int,
    horizon: int,
    continuation_actions: tuple[Action, ...] = ACTIONS,
) -> dict[Action, int]:
    """Count recursive fixed-segment MPC policies under nominal pickup.

    The first segment retains every physical delivery and transition branch.
    Later segments are proposal-only nominal continuations. Hard-4 remains the
    sole authority for the candidate set and for every published action.
    """
    if not 0 < segment_length < horizon:
        raise ValueError("segment length must be inside the horizon")
    bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
    enemy_frames = enemy_hazards_by_frame(snapshot.enemies, horizon)
    laser_frames = laser_hazards_by_frame(snapshot.lasers, horizon)
    hard_births = forecast_world_births(
        snapshot,
        ((snapshot.x, snapshot.y),) * min(4, horizon),
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
        return _step_player(
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

    @lru_cache(maxsize=None)
    def best_from(x: float, y: float, start_frame: int) -> int:
        if start_frame >= horizon:
            return 1
        end_frame = min(horizon, start_frame + segment_length)
        total = 0
        next_states: set[tuple[float, float]] = set()
        for action in continuation_actions:
            future_x, future_y = x, y
            survived = True
            for frame in range(start_frame + 1, end_frame + 1):
                future_x, future_y = step(future_x, future_y, action)
                if not safe_at(future_x, future_y, frame - 1):
                    survived = False
                    break
            endpoint = (future_x, future_y)
            if not survived or endpoint in next_states:
                continue
            next_states.add(endpoint)
            branch_count = (
                1
                if end_frame == horizon
                else best_from(future_x, future_y, end_frame)
            )
            total = min(_MAX_POLICY_VOLUME, total + branch_count)
        return total

    current = action_from_input(snapshot.input_mask)
    scores: dict[Action, int] = {}
    for candidate in candidates:
        prefixes = transition_actions(current, candidate.action)
        worst = _MAX_POLICY_VOLUME
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
                worst = min(
                    worst,
                    best_from(x, y, segment_length) if survived else 0,
                )
        scores[candidate.action] = 0 if worst == _MAX_POLICY_VOLUME else worst
    return scores


def replanning_scores(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    split: int = 4,
    horizon: int = 8,
    continuation_actions: tuple[Action, ...] = ACTIONS,
) -> dict[Action, int]:
    """Count second actions that survive both physical pickup delays."""
    if not 0 < split < horizon:
        raise ValueError("replanning split must be inside the horizon")
    bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
    enemy_frames = enemy_hazards_by_frame(snapshot.enemies, horizon)
    laser_frames = laser_hazards_by_frame(snapshot.lasers, horizon)
    scores: dict[Action, int] = {}
    for candidate in candidates:
        branch_counts = []
        evaluated_split_states = set()
        for first_delay in DELIVERY_DELAYS:
            for first_path in candidate_paths(
                snapshot, candidate.action, first_delay, split
            ):
                split_x, split_y = first_path[-1]
                split_state = (split_x, split_y)
                # Pickup delays and transition prefixes may clamp to the same
                # physical state.  The held candidate and all later physics
                # are identical there, so path multiplicity is not another
                # robustness branch.
                if split_state in evaluated_split_states:
                    continue
                evaluated_split_states.add(split_state)
                continuation_states = set()
                for continuation in continuation_actions:
                    survived = True
                    nominal_final = (split_x, split_y)
                    prefixes = transition_actions(candidate.action, continuation)
                    for continuation_delay in DELIVERY_DELAYS:
                        branch_prefixes = (None,) + prefixes if continuation_delay > 0 else (None,)
                        for prefix in branch_prefixes:
                            future_x, future_y = split_x, split_y
                            for frame in range(split + 1, horizon + 1):
                                elapsed = frame - split
                                if prefix is not None and elapsed == continuation_delay:
                                    step_action = prefix
                                elif elapsed < continuation_delay or (
                                    prefix is None and elapsed <= continuation_delay
                                ):
                                    step_action = candidate.action
                                else:
                                    step_action = continuation
                                future_x, future_y = _step_player(
                                    future_x,
                                    future_y,
                                    step_action,
                                    (
                                        snapshot.focus_speed
                                        if step_action.focused
                                        else snapshot.normal_speed
                                    ),
                                    (
                                        snapshot.focus_diagonal_speed
                                        if step_action.focused
                                        else snapshot.normal_diagonal_speed
                                    ),
                                )
                                hazards = bullet_frames[frame - 1] + enemy_frames[frame - 1]
                                if any(
                                    signed_clearance(
                                        future_x,
                                        future_y,
                                        snapshot.half_width,
                                        snapshot.half_height,
                                        hazard,
                                    )
                                    <= COLLISION_MARGIN
                                    for hazard in hazards
                                ) or any(
                                    signed_laser_clearance(
                                        future_x,
                                        future_y,
                                        snapshot.half_width,
                                        snapshot.half_height,
                                        laser,
                                    )
                                    <= COLLISION_MARGIN
                                    for laser in laser_frames[frame - 1]
                                ):
                                    survived = False
                                    break
                            if not survived:
                                break
                            if continuation_delay == 0 and prefix is None:
                                nominal_final = (future_x, future_y)
                        if not survived:
                            break
                    if survived:
                        continuation_states.add(nominal_final)
                branch_counts.append(len(continuation_states))
        scores[candidate.action] = min(branch_counts)
    return scores
