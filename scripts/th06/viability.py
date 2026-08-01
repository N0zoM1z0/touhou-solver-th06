"""Soft two-segment viability scores; never an action authority."""

from __future__ import annotations

from .hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from .hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from .hazards.geometry import signed_clearance
from .hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from .hazards.lasers import signed_laser_clearance
from .model import ACTIONS, Action, SafeAction, Snapshot
from .safety import COLLISION_MARGIN, _step_player


def replanning_scores(
    snapshot: Snapshot,
    candidates: tuple[SafeAction, ...],
    split: int = 4,
    horizon: int = 8,
) -> dict[Action, int]:
    """Count nominal second actions after one hard-authorized first action."""
    if not 0 < split < horizon:
        raise ValueError("replanning split must be inside the horizon")
    bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
    enemy_frames = enemy_hazards_by_frame(snapshot.enemies, horizon)
    laser_frames = laser_hazards_by_frame(snapshot.lasers, horizon)
    scores: dict[Action, int] = {}
    for candidate in candidates:
        x, y = snapshot.x, snapshot.y
        for _frame in range(1, split + 1):
            x, y = _step_player(
                x,
                y,
                candidate.action,
                snapshot.focus_speed,
                snapshot.focus_diagonal_speed,
            )
        continuation_count = 0
        for continuation in ACTIONS:
            future_x, future_y = x, y
            survived = True
            for frame in range(split + 1, horizon + 1):
                future_x, future_y = _step_player(
                    future_x,
                    future_y,
                    continuation,
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
            continuation_count += int(survived)
        scores[candidate.action] = continuation_count
    return scores
