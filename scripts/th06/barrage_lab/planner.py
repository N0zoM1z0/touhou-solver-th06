"""Independent exhaustive planner oracle over source-stepped barrages."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import ACTIONS, CONTROL_ACTIONS, Action, Snapshot
from .oracle import (
    _DELAYS,
    _bullet_boxes,
    _decode,
    _step_player,
    _transitions,
    _within_margin,
)


_ACTION_BY_NAME = {action.name: action for action in CONTROL_ACTIONS}


@dataclass(frozen=True)
class PlannerOracleResult:
    """Per-first-action terminal volume plus slow-oracle work counters."""

    counts: tuple[tuple[str, int], ...]
    expanded_states: int
    generated_transitions: int


def _safe_at(
    snapshot: Snapshot,
    frames,
    x: float,
    y: float,
    frame_index: int,
    collision_margin: float,
) -> bool:
    return not any(
        _within_margin(
            x,
            y,
            snapshot.half_width,
            snapshot.half_height,
            box,
            collision_margin,
        )
        for box in frames[frame_index]
    )


def source_terminal_counts(
    snapshot: Snapshot,
    candidate_names: tuple[str, ...],
    segment_length: int,
    horizon: int,
    *,
    collision_margin: float = 0.35,
    continuation_length: int | None = None,
    continuation_actions: tuple[Action, ...] = ACTIONS,
) -> PlannerOracleResult:
    """Exhaust physical delivery, then deduplicate exact reachable positions.

    This deliberately does not call the production hazard or planning code.
    It advances source-shaped Bullet state through the scalar oracle, retains
    every observed delivery/transition branch in the first segment, and takes
    the worst terminal cardinality across those physical branches.
    """
    if segment_length <= 0 or horizon < segment_length:
        raise ValueError("planner horizon must cover one positive segment")
    if continuation_length is None:
        continuation_length = segment_length
    if continuation_length <= 0:
        raise ValueError("continuation length must be positive")
    if len(set(candidate_names)) != len(candidate_names):
        raise ValueError("candidate names must be unique")
    try:
        candidates = tuple(_ACTION_BY_NAME[name] for name in candidate_names)
    except KeyError as error:
        raise ValueError(f"unknown control action {error.args[0]!r}") from error

    frames = _bullet_boxes(snapshot, horizon)
    current = _decode(snapshot.input_mask)
    expanded_states = 0
    generated_transitions = 0
    safety_cache: dict[tuple[float, float, int], bool] = {}
    terminal_cache: dict[tuple[float, float], int] = {}

    def safe_at(x: float, y: float, frame_index: int) -> bool:
        key = (x, y, frame_index)
        value = safety_cache.get(key)
        if value is None:
            value = _safe_at(
                snapshot,
                frames,
                x,
                y,
                frame_index,
                collision_margin,
            )
            safety_cache[key] = value
        return value

    def terminal_count(start_x: float, start_y: float) -> int:
        nonlocal expanded_states, generated_transitions
        cache_key = (start_x, start_y)
        cached = terminal_cache.get(cache_key)
        if cached is not None:
            return cached
        states = {(start_x, start_y)}
        for start_frame in range(
            segment_length, horizon, continuation_length
        ):
            end_frame = min(horizon, start_frame + continuation_length)
            next_states: set[tuple[float, float]] = set()
            expanded_states += len(states)
            for state_x, state_y in states:
                for action in continuation_actions:
                    generated_transitions += 1
                    x, y = state_x, state_y
                    for frame in range(start_frame + 1, end_frame + 1):
                        x, y = _step_player(snapshot, x, y, action)
                        if not safe_at(x, y, frame - 1):
                            break
                    else:
                        next_states.add((x, y))
            states = next_states
            if not states:
                break
        count = len(states)
        terminal_cache[cache_key] = count
        return count

    counts = []
    for candidate in candidates:
        prefixes = _transitions(snapshot.input_mask, candidate)
        worst = None
        for delay in _DELAYS:
            branches = (None,) + (prefixes if delay > 0 else ())
            for prefix in branches:
                x, y = snapshot.x, snapshot.y
                survived = True
                for frame in range(1, segment_length + 1):
                    if prefix is not None:
                        action = (
                            current
                            if frame < delay
                            else prefix
                            if frame == delay
                            else candidate
                        )
                    else:
                        action = current if frame <= delay else candidate
                    x, y = _step_player(snapshot, x, y, action)
                    if not safe_at(x, y, frame - 1):
                        survived = False
                        break
                branch_count = terminal_count(x, y) if survived else 0
                worst = (
                    branch_count
                    if worst is None
                    else min(worst, branch_count)
                )
        counts.append((candidate.name, 0 if worst is None else worst))
    return PlannerOracleResult(
        tuple(counts), expanded_states, generated_transitions
    )
