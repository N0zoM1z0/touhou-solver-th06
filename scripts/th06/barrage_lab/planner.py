"""Independent exhaustive planner oracle over source-stepped barrages."""

from __future__ import annotations

from dataclasses import dataclass
import math

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

    counts: tuple[tuple[str, int | PlannerGuidanceValue], ...]
    expanded_states: int
    generated_transitions: int


@dataclass(frozen=True)
class PlannerGuidanceValue:
    terminal_count: int
    free_clearance: float
    free_x: float
    free_y: float


def _signed_clearance(
    snapshot: Snapshot,
    x: float,
    y: float,
    box: tuple[float, float, float, float],
) -> float:
    left, top, right, bottom = box
    gap_x = max(
        left - (x + snapshot.half_width),
        (x - snapshot.half_width) - right,
    )
    gap_y = max(
        top - (y + snapshot.half_height),
        (y - snapshot.half_height) - bottom,
    )
    if gap_x <= 0.0 and gap_y <= 0.0:
        return max(gap_x, gap_y)
    return math.hypot(max(0.0, gap_x), max(0.0, gap_y))


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
    include_guidance: bool = False,
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
    terminal_cache: dict[
        tuple[float, float],
        PlannerGuidanceValue,
    ] = {}

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

    def terminal_stats(
        start_x: float,
        start_y: float,
    ) -> PlannerGuidanceValue:
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
        free_clearance = -math.inf
        free_x, free_y = start_x, start_y
        if include_guidance:
            terminal_frame = frames[horizon - 1]
            for x, y in sorted(states):
                clearance = min(
                    x - 8.0,
                    376.0 - x,
                    y - 16.0,
                    432.0 - y,
                )
                for box in terminal_frame:
                    clearance = min(
                        clearance,
                        _signed_clearance(snapshot, x, y, box),
                    )
                if clearance > free_clearance:
                    free_clearance = clearance
                    free_x, free_y = x, y
        result = PlannerGuidanceValue(
            len(states),
            free_clearance,
            free_x,
            free_y,
        )
        terminal_cache[cache_key] = result
        return result

    counts = []
    guidance = []
    for candidate in candidates:
        prefixes = _transitions(snapshot.input_mask, candidate)
        worst = None
        worst_free = math.inf
        worst_free_x, worst_free_y = snapshot.x, snapshot.y
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
                branch_stats = (
                    terminal_stats(x, y)
                    if survived
                    else PlannerGuidanceValue(0, -math.inf, x, y)
                )
                branch_count = branch_stats.terminal_count
                worst = (
                    branch_count
                    if worst is None
                    else min(worst, branch_count)
                )
                if branch_stats.free_clearance < worst_free:
                    worst_free = branch_stats.free_clearance
                    worst_free_x = branch_stats.free_x
                    worst_free_y = branch_stats.free_y
        counts.append((candidate.name, 0 if worst is None else worst))
        if include_guidance:
            guidance.append((
                candidate.name,
                PlannerGuidanceValue(
                    0 if worst is None else worst,
                    worst_free,
                    worst_free_x,
                    worst_free_y,
                ),
            ))
    return PlannerOracleResult(
        tuple(counts), expanded_states, generated_transitions
    ) if not include_guidance else PlannerOracleResult(
        tuple(guidance), expanded_states, generated_transitions
    )
