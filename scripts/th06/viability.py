"""Soft two-segment viability scores; never an action authority."""

from __future__ import annotations

from .hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from .hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from .hazards.geometry import signed_clearance
from .hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from .hazards.lasers import signed_laser_clearance
from .model import ACTIONS, Action, SafeAction, Snapshot
from .safety import (
    COLLISION_MARGIN,
    DELIVERY_DELAYS,
    _step_player,
    candidate_paths,
    transition_actions,
)


def replanning_scores(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    split: int = 4,
    horizon: int = 8,
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
        for first_delay in DELIVERY_DELAYS:
            for first_path in candidate_paths(
                snapshot, candidate.action, first_delay, split
            ):
                split_x, split_y = first_path[-1]
                continuation_count = 0
                for continuation in ACTIONS:
                    survived = True
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
                                    snapshot.focus_speed,
                                    snapshot.focus_diagonal_speed,
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
                        if not survived:
                            break
                    continuation_count += int(survived)
                branch_counts.append(continuation_count)
        scores[candidate.action] = min(branch_counts)
    return scores
