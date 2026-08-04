"""Independent scalar oracle for the first exact barrage-lab rung."""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from ..model import Action, CONTROL_ACTIONS, Snapshot


_CONTROL_BITS = (0x20, 0x04, 0x40, 0x80, 0x10)
_DELAYS = (0, 1, 2, 3)
_DYNAMIC_FLAGS = 0xDF1
_EXACT_DYNAMIC_FLAGS = 0x071
_SPAWN_DIVISOR = {2: 2.0, 3: 2.5, 4: 3.0}
_SPAWN_FINAL_TIMER = {2: 9, 3: 15, 4: 31}


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _decode(mask: int) -> Action:
    dy = -1 if mask & 0x10 else 1 if mask & 0x20 else 0
    dx = 0
    if mask & 0x40:
        dx = -1
    if mask & 0x80:
        dx = 1
    return Action("oracle", dx, dy, bool(mask & 0x04))


def _mask(action: Action) -> int:
    mask = 0x04 if action.focused else 0
    if action.dx < 0:
        mask |= 0x40
    elif action.dx > 0:
        mask |= 0x80
    if action.dy < 0:
        mask |= 0x10
    elif action.dy > 0:
        mask |= 0x20
    return mask


def _same(left: Action, right: Action) -> bool:
    return (left.dx, left.dy, left.focused) == (
        right.dx, right.dy, right.focused
    )


def _transitions(current_mask: int, target: Action) -> tuple[Action, ...]:
    current_mask &= 0xF4
    target_mask = _mask(target) & 0xF4
    current = _decode(current_mask)
    prefix_mask = current_mask
    result = []
    for release in (True, False):
        for bit in _CONTROL_BITS:
            changed = (
                bool(current_mask & bit) and not bool(target_mask & bit)
                if release else
                bool(target_mask & bit) and not bool(current_mask & bit)
            )
            if not changed:
                continue
            prefix_mask = (
                prefix_mask & ~bit if release else prefix_mask | bit
            )
            prefix = _decode(prefix_mask)
            if (
                not _same(prefix, current)
                and not _same(prefix, target)
                and not any(_same(prefix, value) for value in result)
            ):
                result.append(prefix)
    return tuple(result)


def _step_player(snapshot: Snapshot, x: float, y: float, action: Action):
    diagonal = bool(action.dx and action.dy)
    if action.focused:
        speed = (
            snapshot.focus_diagonal_speed if diagonal else snapshot.focus_speed
        )
    else:
        speed = (
            snapshot.normal_diagonal_speed if diagonal else snapshot.normal_speed
        )
    x = _f32(x + _f32(action.dx * speed))
    y = _f32(y + _f32(action.dy * speed))
    return min(376.0, max(8.0, x)), min(432.0, max(16.0, y))


def _bullet_boxes(snapshot: Snapshot, horizon: int):
    states = []
    for bullet in snapshot.bullets:
        if (
            bullet.state not in (1, 2, 3, 4)
            or bullet.ex_flags & (_DYNAMIC_FLAGS & ~_EXACT_DYNAMIC_FLAGS)
        ):
            raise ValueError("oracle does not support this bullet motion")
        states.append([
            _f32(bullet.x), _f32(bullet.y),
            _f32(bullet.vx), _f32(bullet.vy),
            _f32(bullet.half_width), _f32(bullet.half_height),
            _f32(bullet.angle), _f32(bullet.speed), bullet.ex_flags,
            bullet.timer, _f32(bullet.timer_float),
            _f32(bullet.acceleration_x), _f32(bullet.acceleration_y),
            bullet.acceleration_duration,
            _f32(bullet.curve_speed_acceleration),
            _f32(bullet.curve_angular_velocity),
            _f32(bullet.turn_speed), _f32(bullet.direction_rotation),
            bullet.direction_interval, bullet.direction_num_times,
            bullet.direction_max_times,
            bullet.state,
        ])
    frames = []
    for _ in range(horizon):
        boxes = []
        for state in states:
            if state[21] in _SPAWN_DIVISOR:
                divisor = _SPAWN_DIVISOR[state[21]]
                state[0] = _f32(state[0] + _f32(state[2] / divisor))
                state[1] = _f32(state[1] + _f32(state[3] / divisor))
                if state[9] < _SPAWN_FINAL_TIMER[state[21]]:
                    state[9] += 1
                    state[10] = _f32(state[10] + 1.0)
                    continue
                # The source changes state, resets the timer, and falls
                # through into the fired update on the completion tick.
                state[21] = 1
                state[9] = 0
                state[10] = 0.0
            if state[8] & 0x01:
                if state[9] <= 16:
                    deceleration = _f32(
                        5.0 - _f32(state[10] * 5.0 / 16.0)
                    )
                    current_speed = _f32(deceleration + state[7])
                    state[2] = _f32(math.cos(state[6]) * current_speed)
                    state[3] = _f32(math.sin(state[6]) * current_speed)
                else:
                    state[8] ^= 0x01
            elif state[8] & 0x10:
                if state[9] >= state[13]:
                    state[8] &= ~0x10
                else:
                    state[2] = _f32(state[2] + state[11])
                    state[3] = _f32(state[3] + state[12])
                    state[6] = _f32(math.atan2(state[3], state[2]))
            elif state[8] & 0x20:
                if state[9] >= state[13]:
                    state[8] &= ~0x20
                else:
                    state[6] = _f32(math.remainder(
                        _f32(state[6] + state[15]), math.tau
                    ))
                    state[7] = _f32(state[7] + state[14])
                    state[2] = _f32(math.cos(state[6]) * state[7])
                    state[3] = _f32(math.sin(state[6]) * state[7])
            if state[8] & 0x40:
                if state[9] >= state[18] * (state[19] + 1):
                    state[19] += 1
                    if state[19] >= state[20]:
                        state[8] &= ~0x40
                    state[6] = _f32(state[6] + state[17])
                    state[7] = state[16]
                    current_speed = state[7]
                else:
                    phase = _f32(state[10] - state[18] * state[19])
                    current_speed = _f32(
                        state[7] - _f32(phase * state[7] / state[18])
                    )
                state[2] = _f32(math.cos(state[6]) * current_speed)
                state[3] = _f32(math.sin(state[6]) * current_speed)
            state[0] = _f32(state[0] + state[2])
            state[1] = _f32(state[1] + state[3])
            boxes.append((
                _f32(state[0] - state[4]), _f32(state[1] - state[5]),
                _f32(state[0] + state[4]), _f32(state[1] + state[5]),
            ))
            state[9] += 1
            state[10] = _f32(state[10] + 1.0)
        frames.append(tuple(boxes))
    return tuple(frames)


def _within_margin(
    x: float, y: float, half_width: float, half_height: float,
    box: tuple[float, float, float, float], margin: float,
) -> bool:
    left, top, right, bottom = box
    gap_x = max(
        _f32(left - _f32(x + half_width)),
        _f32(_f32(x - half_width) - right),
    )
    gap_y = max(
        _f32(top - _f32(y + half_height)),
        _f32(_f32(y - half_height) - bottom),
    )
    positive_x = max(0.0, gap_x)
    positive_y = max(0.0, gap_y)
    distance_squared = _f32(
        _f32(positive_x * positive_x) + _f32(positive_y * positive_y)
    )
    return distance_squared <= _f32(margin * margin)


@dataclass(frozen=True)
class OracleResult:
    actions: tuple[str, ...]
    terminal_positions: tuple[tuple[str, float, float], ...]


def certify_linear_source(
    snapshot: Snapshot,
    horizon: int,
    *,
    collision_margin: float = 0.35,
    actions: tuple[Action, ...] = CONTROL_ACTIONS,
    delivery_delays: tuple[int, ...] = _DELAYS,
) -> OracleResult:
    """Reproduce source update order and hard delivery branches, slowly."""
    frames = _bullet_boxes(snapshot, horizon)
    current = _decode(snapshot.input_mask)
    safe_names = []
    terminals = []
    for target in actions:
        valid = True
        terminal_x, terminal_y = snapshot.x, snapshot.y
        prefixes = _transitions(snapshot.input_mask, target)
        for delay in delivery_delays:
            branches = (None,) + (prefixes if delay > 0 else ())
            for prefix in branches:
                x, y = _f32(snapshot.x), _f32(snapshot.y)
                for frame in range(1, horizon + 1):
                    if prefix is not None:
                        action = (
                            current if frame < delay
                            else prefix if frame == delay
                            else target
                        )
                    else:
                        action = current if frame <= delay else target
                    x, y = _step_player(snapshot, x, y, action)
                    if any(
                        _within_margin(
                            x, y, snapshot.half_width, snapshot.half_height,
                            box, collision_margin,
                        )
                        for box in frames[frame - 1]
                    ):
                        valid = False
                        break
                if prefix is None and delay == delivery_delays[-1]:
                    terminal_x, terminal_y = x, y
                if not valid:
                    break
            if not valid:
                break
        if valid:
            safe_names.append(target.name)
            terminals.append((target.name, terminal_x, terminal_y))
    return OracleResult(tuple(safe_names), tuple(terminals))
