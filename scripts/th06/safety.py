"""Hard authority over hazards already present in native memory."""

from __future__ import annotations

from .hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from .hazards.bullets import nearest_current_clearance
from .hazards.geometry import signed_clearance
from .hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from .hazards.lasers import signed_laser_clearance
from .model import ACTIONS, Action, SafeAction, Snapshot, action_from_input


MOVEMENT_LEFT = 8.0
MOVEMENT_RIGHT = 376.0
MOVEMENT_TOP = 16.0
MOVEMENT_BOTTOM = 432.0
PICKUP_DELAYS = (0, 1, 2)
COLLISION_MARGIN = 0.35


def _step_player(
    x: float,
    y: float,
    action: Action,
    cardinal_speed: float,
    diagonal_speed: float,
) -> tuple[float, float]:
    speed = diagonal_speed if action.dx and action.dy else cardinal_speed
    x = min(MOVEMENT_RIGHT, max(MOVEMENT_LEFT, x + action.dx * speed))
    y = min(MOVEMENT_BOTTOM, max(MOVEMENT_TOP, y + action.dy * speed))
    return x, y


def candidate_path(snapshot: Snapshot, action: Action, delay: int, horizon: int) -> list[tuple[float, float]]:
    current = action_from_input(snapshot.input_mask)
    current_focus = bool(snapshot.input_mask & 0x04)
    current_cardinal = snapshot.focus_speed if current_focus else snapshot.normal_speed
    current_diagonal = snapshot.focus_diagonal_speed if current_focus else snapshot.normal_diagonal_speed
    x, y = snapshot.x, snapshot.y
    path: list[tuple[float, float]] = []
    for frame in range(1, horizon + 1):
        if frame <= delay:
            step_action = current
            cardinal = current_cardinal
            diagonal = current_diagonal
        else:
            step_action = action
            cardinal = snapshot.focus_speed
            diagonal = snapshot.focus_diagonal_speed
        x, y = _step_player(x, y, step_action, cardinal, diagonal)
        path.append((x, y))
    return path


def certify_actions(snapshot: Snapshot, horizon: int) -> tuple[SafeAction, ...]:
    bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
    laser_frames = laser_hazards_by_frame(snapshot.lasers, horizon)
    certified: list[SafeAction] = []
    for action in ACTIONS:
        action_clearance = 999.0
        valid = True
        final_x = snapshot.x
        final_y = snapshot.y
        for delay in PICKUP_DELAYS:
            path = candidate_path(snapshot, action, delay, horizon)
            if delay == PICKUP_DELAYS[-1]:
                final_x, final_y = path[-1]
            for frame_index, (x, y) in enumerate(path):
                for hazard in bullet_frames[frame_index]:
                    clearance = signed_clearance(
                        x, y, snapshot.half_width, snapshot.half_height, hazard
                    )
                    action_clearance = min(action_clearance, clearance)
                    if clearance <= COLLISION_MARGIN:
                        valid = False
                        break
                if valid:
                    for laser in laser_frames[frame_index]:
                        clearance = signed_laser_clearance(
                            x, y, snapshot.half_width, snapshot.half_height, laser
                        )
                        action_clearance = min(action_clearance, clearance)
                        if clearance <= COLLISION_MARGIN:
                            valid = False
                            break
                if not valid:
                    break
            if not valid:
                break
        if valid:
            certified.append(SafeAction(action, action_clearance, final_x, final_y))
    return tuple(certified)
