"""Hard authority over hazards already present in native memory."""

from __future__ import annotations

import math

from .model import ACTIONS, Action, Bullet, SafeAction, Snapshot, action_from_input


MOVEMENT_LEFT = 8.0
MOVEMENT_RIGHT = 376.0
MOVEMENT_TOP = 16.0
MOVEMENT_BOTTOM = 432.0
PICKUP_DELAYS = (0, 1, 2)
COLLISION_MARGIN = 0.35
DYNAMIC_EX_FLAGS = 0xDF1
ACCELERATION_FLAG = 0x10
COMPLEX_MOTION_FLAGS = 0xDE1


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


def _hazard_box(bullet: Bullet, frame: int) -> tuple[float, float, float, float]:
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


def signed_clearance(
    player_x: float,
    player_y: float,
    player_half_width: float,
    player_half_height: float,
    hazard: tuple[float, float, float, float],
) -> float:
    left, top, right, bottom = hazard
    gap_x = max(left - (player_x + player_half_width), (player_x - player_half_width) - right)
    gap_y = max(top - (player_y + player_half_height), (player_y - player_half_height) - bottom)
    if gap_x <= 0.0 and gap_y <= 0.0:
        return max(gap_x, gap_y)
    return math.hypot(max(0.0, gap_x), max(0.0, gap_y))


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


def certify_actions(snapshot: Snapshot, horizon: int) -> tuple[SafeAction, ...]:
    hazards_by_frame = [
        tuple(_hazard_box(bullet, frame) for bullet in snapshot.bullets)
        for frame in range(1, horizon + 1)
    ]
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
                for hazard in hazards_by_frame[frame_index]:
                    clearance = signed_clearance(
                        x, y, snapshot.half_width, snapshot.half_height, hazard
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
