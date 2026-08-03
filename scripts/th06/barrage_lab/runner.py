"""Correctness sweep and mismatch reduction for source-derived barrages."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import math
import time
from typing import Callable

from ..guidance import terminal_guidance_scores
from ..model import CONTROL_ACTIONS, SafeAction, Snapshot
from ..safety import COLLISION_MARGIN, certify_actions
from .assets import EclBulletOpcode
from .generator import (
    BarrageCase,
    RuntimeBarrageTemplate,
    generate_barrage_case,
    stress_player_position,
)
from .oracle import certify_linear_source
from .planner import PlannerGuidanceValue, source_terminal_counts


Certifier = Callable[[Snapshot, int], tuple[str, ...]]
PlannerValue = int | tuple[int, float, float, float]
Planner = Callable[
    [Snapshot, tuple[str, ...], int, int],
    tuple[tuple[str, PlannerValue], ...],
]


_ACTION_BY_NAME = {action.name: action for action in CONTROL_ACTIONS}


def python_action_names(snapshot: Snapshot, horizon: int) -> tuple[str, ...]:
    return tuple(
        value.action.name for value in certify_actions(
            snapshot, horizon, actions=CONTROL_ACTIONS
        )
    )


def native_action_names(kernel) -> Certifier:
    def certify(snapshot: Snapshot, horizon: int) -> tuple[str, ...]:
        return tuple(
            value.action.name for value in kernel.certify_selected(
                snapshot, horizon, CONTROL_ACTIONS, COLLISION_MARGIN
            )
        )
    return certify


def _candidate_values(
    snapshot: Snapshot, candidate_names: tuple[str, ...]
) -> tuple[SafeAction, ...]:
    return tuple(
        SafeAction(_ACTION_BY_NAME[name], 0.0, snapshot.x, snapshot.y)
        for name in candidate_names
    )


def python_terminal_counts(
    snapshot: Snapshot,
    candidate_names: tuple[str, ...],
    segment_length: int,
    horizon: int,
) -> tuple[tuple[str, int], ...]:
    values = terminal_guidance_scores(
        snapshot,
        _candidate_values(snapshot, candidate_names),
        segment_length,
        horizon,
    )
    return tuple(
        (name, values[_ACTION_BY_NAME[name]].terminal_count)
        for name in candidate_names
    )


def _guidance_value(value) -> tuple[int, float, float, float]:
    return (
        value.terminal_count,
        round(value.free_clearance, 4),
        round(value.free_x, 4),
        round(value.free_y, 4),
    )


def _planner_value_equal(left: PlannerValue, right: PlannerValue) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, int) or isinstance(right, int):
        return left == right
    if left[0] == right[0] == 0:
        # An empty terminal set has no usable soft endpoint; its placeholder
        # coordinate is intentionally irrelevant.
        return True
    return (
        left[0] == right[0]
        and all(
            first == second
            or math.isclose(first, second, abs_tol=0.005)
            for first, second in zip(left[1:], right[1:])
        )
    )


def _planner_results_equal(left, right) -> bool:
    if tuple(name for name, _value in left) != tuple(
        name for name, _value in right
    ):
        return False
    return all(
        _planner_value_equal(first, second)
        for (_name, first), (_other, second) in zip(left, right)
    )


def source_terminal_guidance(
    snapshot: Snapshot,
    candidate_names: tuple[str, ...],
    segment_length: int,
    horizon: int,
) -> tuple[tuple[str, PlannerValue], ...]:
    values = source_terminal_counts(
        snapshot,
        candidate_names,
        segment_length,
        horizon,
        include_guidance=True,
    ).counts
    return tuple(
        (name, _guidance_value(value))
        for name, value in values
    )


def python_terminal_guidance(
    snapshot: Snapshot,
    candidate_names: tuple[str, ...],
    segment_length: int,
    horizon: int,
) -> tuple[tuple[str, PlannerValue], ...]:
    values = terminal_guidance_scores(
        snapshot,
        _candidate_values(snapshot, candidate_names),
        segment_length,
        horizon,
    )
    return tuple(
        (name, _guidance_value(values[_ACTION_BY_NAME[name]]))
        for name in candidate_names
    )


def native_terminal_counts(kernel) -> Planner:
    def plan(
        snapshot: Snapshot,
        candidate_names: tuple[str, ...],
        segment_length: int,
        horizon: int,
    ) -> tuple[tuple[str, int], ...]:
        values = kernel.terminal_counts(
            snapshot,
            _candidate_values(snapshot, candidate_names),
            segment_length,
            horizon,
            COLLISION_MARGIN,
        )
        return tuple(
            (name, values[_ACTION_BY_NAME[name]])
            for name in candidate_names
        )
    return plan


def native_progressive_terminal_counts(
    kernel, *, budget_ms: float = 1000.0
) -> Planner:
    """Exercise the complete progressive entry point used by production."""
    def plan(
        snapshot: Snapshot,
        candidate_names: tuple[str, ...],
        segment_length: int,
        horizon: int,
    ) -> tuple[tuple[str, int], ...]:
        result = kernel.segment_terminal_counts_progressive(
            snapshot,
            _candidate_values(snapshot, candidate_names),
            segment_length,
            horizon,
            horizon,
            COLLISION_MARGIN,
            budget_ms,
        )
        if result is None:
            return tuple((name, -1) for name in candidate_names)
        completed_horizon, values, reached_maximum = result
        if completed_horizon != horizon or not reached_maximum:
            return tuple((name, -2) for name in candidate_names)
        return tuple(
            (name, values[_ACTION_BY_NAME[name]])
            for name in candidate_names
        )
    return plan


def native_progressive_terminal_guidance(
    kernel, *, budget_ms: float = 1000.0
) -> Planner:
    """Fuzz optional guidance aggregated after survival publication."""
    def plan(
        snapshot: Snapshot,
        candidate_names: tuple[str, ...],
        segment_length: int,
        horizon: int,
    ) -> tuple[tuple[str, PlannerValue], ...]:
        candidates = _candidate_values(snapshot, candidate_names)
        values = []
        for name in candidate_names:
            action = _ACTION_BY_NAME[name]
            result = kernel.segment_terminal_guidance_progressive(
                snapshot,
                candidates,
                segment_length,
                horizon,
                horizon,
                action,
                COLLISION_MARGIN,
                budget_ms,
            )
            if result is None or result[0] != horizon or not result[2]:
                values.append((name, (-1, -math.inf, 0.0, 0.0)))
                continue
            guidance = result[3]
            if guidance is None:
                values.append((
                    name,
                    (
                        result[1][action],
                        -math.inf,
                        0.0,
                        0.0,
                    ),
                ))
                continue
            values.append((name, _guidance_value(guidance)))
        return tuple(values)
    return plan


@dataclass(frozen=True)
class SweepMismatch:
    seed: int
    implementation: str
    horizon: int
    expected: tuple[str, ...]
    actual: tuple[str, ...]
    snapshot: Snapshot
    sources: tuple[tuple[str, int, int], ...]

    @property
    def differing_actions(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.expected) ^ set(self.actual)))


@dataclass(frozen=True)
class SweepSummary:
    seeds: int
    horizon: int
    generated_bullets: int
    safe_set_sizes: tuple[tuple[int, int], ...]
    elapsed_seconds: float


@dataclass(frozen=True)
class PlannerMismatch:
    seed: int
    implementation: str
    segment_length: int
    horizon: int
    candidate_names: tuple[str, ...]
    expected: tuple[tuple[str, PlannerValue], ...]
    actual: tuple[tuple[str, PlannerValue], ...]
    snapshot: Snapshot
    sources: tuple[tuple[str, int, int], ...]

    @property
    def differing_actions(self) -> tuple[str, ...]:
        expected = dict(self.expected)
        actual = dict(self.actual)
        return tuple(
            name for name in self.candidate_names
            if not _planner_value_equal(
                expected.get(name),
                actual.get(name),
            )
        )


@dataclass(frozen=True)
class PlannerSweepSummary:
    seeds: int
    viable_cases: int
    segment_length: int
    horizon: int
    generated_bullets: int
    candidate_actions: int
    best_action_sizes: tuple[tuple[int, int], ...]
    oracle_expanded_states: int
    oracle_generated_transitions: int
    implementation_seconds: tuple[tuple[str, float], ...]


def shrink_mismatch(
    mismatch: SweepMismatch,
    certifier: Certifier,
) -> SweepMismatch:
    """Minimize horizon first, then delete bullet chunks with provenance."""
    bullets = list(mismatch.snapshot.bullets)

    horizon = mismatch.horizon
    for candidate_horizon in range(1, horizon):
        expected = certify_linear_source(
            mismatch.snapshot, candidate_horizon
        ).actions
        if expected != certifier(mismatch.snapshot, candidate_horizon):
            horizon = candidate_horizon
            break

    def differs(values) -> bool:
        snapshot = replace(mismatch.snapshot, bullets=tuple(values))
        return (
            certify_linear_source(snapshot, horizon).actions
            != certifier(snapshot, horizon)
        )

    granularity = 2
    while len(bullets) >= 2:
        chunk = max(1, (len(bullets) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(bullets), chunk):
            candidate = bullets[:start] + bullets[start + chunk:]
            if candidate and differs(candidate):
                bullets = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(bullets):
            break
        granularity = min(len(bullets), granularity * 2)
    snapshot = replace(mismatch.snapshot, bullets=tuple(bullets))
    source_by_slot = {
        bullet.slot: source
        for bullet, source in zip(mismatch.snapshot.bullets, mismatch.sources)
    }
    return replace(
        mismatch,
        horizon=horizon,
        expected=certify_linear_source(snapshot, horizon).actions,
        actual=certifier(snapshot, horizon),
        snapshot=snapshot,
        sources=tuple(source_by_slot[bullet.slot] for bullet in bullets),
    )


def shrink_planner_mismatch(
    mismatch: PlannerMismatch,
    planner: Planner,
    oracle_planner: Planner | None = None,
) -> PlannerMismatch:
    """Minimize horizon, independent candidate branches, then bullets."""
    segment_length = mismatch.segment_length
    horizon = mismatch.horizon
    candidate_names = mismatch.candidate_names

    def evaluate(
        snapshot: Snapshot,
        names: tuple[str, ...],
        candidate_horizon: int,
    ) -> tuple[
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
    ]:
        expected = (
            source_terminal_counts(
                snapshot,
                names,
                segment_length,
                candidate_horizon,
            ).counts
            if oracle_planner is None
            else oracle_planner(
                snapshot,
                names,
                segment_length,
                candidate_horizon,
            )
        )
        return expected, planner(
            snapshot, names, segment_length, candidate_horizon
        )

    # Progressive native entries require at least one frame beyond the
    # physical delivery segment; keep reduced cases replayable by every
    # planner implementation under comparison.
    for candidate_horizon in range(segment_length + 1, horizon):
        expected, actual = evaluate(
            mismatch.snapshot, candidate_names, candidate_horizon
        )
        if not _planner_results_equal(expected, actual):
            horizon = candidate_horizon
            break

    expected, actual = evaluate(mismatch.snapshot, candidate_names, horizon)
    differing = tuple(
        name for name in candidate_names
        if not _planner_value_equal(
            dict(expected).get(name),
            dict(actual).get(name),
        )
    )
    for name in differing:
        one = (name,)
        one_expected, one_actual = evaluate(mismatch.snapshot, one, horizon)
        if not _planner_results_equal(one_expected, one_actual):
            candidate_names = one
            expected, actual = one_expected, one_actual
            break

    bullets = list(mismatch.snapshot.bullets)

    def differs(values) -> bool:
        snapshot = replace(mismatch.snapshot, bullets=tuple(values))
        expected_value, actual_value = evaluate(
            snapshot, candidate_names, horizon
        )
        return not _planner_results_equal(expected_value, actual_value)

    granularity = 2
    while len(bullets) >= 2:
        chunk = max(1, (len(bullets) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(bullets), chunk):
            candidate = bullets[:start] + bullets[start + chunk:]
            if candidate and differs(candidate):
                bullets = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if reduced:
            continue
        if granularity >= len(bullets):
            break
        granularity = min(len(bullets), granularity * 2)

    snapshot = replace(mismatch.snapshot, bullets=tuple(bullets))
    expected, actual = evaluate(snapshot, candidate_names, horizon)
    source_by_slot = {
        bullet.slot: source
        for bullet, source in zip(mismatch.snapshot.bullets, mismatch.sources)
    }
    return replace(
        mismatch,
        horizon=horizon,
        candidate_names=candidate_names,
        expected=expected,
        actual=actual,
        snapshot=snapshot,
        sources=tuple(source_by_slot[bullet.slot] for bullet in bullets),
    )


def run_sweep(
    catalogue: tuple[EclBulletOpcode, ...],
    *,
    seeds: int,
    horizon: int,
    placement: str = "interior",
    runtime_templates: tuple[RuntimeBarrageTemplate, ...] = (),
    extra_certifiers: tuple[tuple[str, Certifier], ...] = (),
) -> tuple[SweepSummary, SweepMismatch | None]:
    certifiers = (("python", python_action_names),) + extra_certifiers
    total_bullets = 0
    safe_sizes = Counter()
    started = time.perf_counter()
    for seed in range(seeds):
        case: BarrageCase = generate_barrage_case(
            catalogue,
            seed,
            player_position=(
                None
                if runtime_templates
                else stress_player_position(seed, placement)
            ),
            runtime_template=(
                runtime_templates[
                    (seed * 1_315_423_911) % len(runtime_templates)
                ]
                if runtime_templates else None
            ),
        )
        total_bullets += len(case.snapshot.bullets)
        expected = certify_linear_source(case.snapshot, horizon).actions
        safe_sizes[len(expected)] += 1
        for name, certifier in certifiers:
            actual = certifier(case.snapshot, horizon)
            if actual != expected:
                mismatch = SweepMismatch(
                    seed, name, horizon, expected, actual,
                    case.snapshot, case.sources,
                )
                return (
                    SweepSummary(
                        seed + 1, horizon, total_bullets,
                        tuple(sorted(safe_sizes.items())),
                        time.perf_counter() - started,
                    ),
                    shrink_mismatch(mismatch, certifier),
                )
    return (
        SweepSummary(
            seeds, horizon, total_bullets,
            tuple(sorted(safe_sizes.items())),
            time.perf_counter() - started,
        ),
        None,
    )


def run_planner_sweep(
    catalogue: tuple[EclBulletOpcode, ...],
    *,
    seeds: int,
    segment_length: int,
    horizon: int,
    placement: str = "interior",
    runtime_templates: tuple[RuntimeBarrageTemplate, ...] = (),
    oracle_planner: Planner | None = None,
    base_planners: tuple[tuple[str, Planner], ...] = (
        ("python", python_terminal_counts),
    ),
    extra_planners: tuple[tuple[str, Planner], ...] = (),
    one_candidate: bool = False,
) -> tuple[PlannerSweepSummary, PlannerMismatch | None]:
    """Differentially test production planners on source-valid barrages."""
    planners = base_planners + extra_planners
    total_bullets = 0
    candidate_actions = 0
    viable_cases = 0
    best_sizes = Counter()
    expanded_states = 0
    generated_transitions = 0
    elapsed = {"oracle": 0.0, **{name: 0.0 for name, _ in planners}}

    for seed in range(seeds):
        case = generate_barrage_case(
            catalogue,
            seed,
            player_position=(
                None
                if runtime_templates
                else stress_player_position(seed, placement)
            ),
            runtime_template=(
                runtime_templates[
                    (seed * 1_315_423_911) % len(runtime_templates)
                ]
                if runtime_templates else None
            ),
        )
        total_bullets += len(case.snapshot.bullets)
        candidate_names = certify_linear_source(
            case.snapshot, segment_length
        ).actions
        if not candidate_names:
            continue
        if one_candidate:
            candidate_names = (
                candidate_names[seed % len(candidate_names)],
            )
        viable_cases += 1
        candidate_actions += len(candidate_names)
        started = time.perf_counter()
        oracle = source_terminal_counts(
            case.snapshot,
            candidate_names,
            segment_length,
            horizon,
            include_guidance=(oracle_planner is source_terminal_guidance),
        )
        expected = (
            oracle.counts
            if oracle_planner is None
            else tuple(
                (name, _guidance_value(value))
                for name, value in oracle.counts
            )
            if oracle_planner is source_terminal_guidance
            else oracle_planner(
                case.snapshot,
                candidate_names,
                segment_length,
                horizon,
            )
        )
        elapsed["oracle"] += time.perf_counter() - started
        expanded_states += oracle.expanded_states
        generated_transitions += oracle.generated_transitions
        scores = {
            name: value if isinstance(value, int) else value[0]
            for name, value in expected
        }
        best = max(scores.values())
        best_sizes[sum(value == best for value in scores.values())] += 1

        for name, planner in planners:
            started = time.perf_counter()
            actual = planner(
                case.snapshot, candidate_names, segment_length, horizon
            )
            elapsed[name] += time.perf_counter() - started
            if not _planner_results_equal(actual, expected):
                mismatch = PlannerMismatch(
                    seed,
                    name,
                    segment_length,
                    horizon,
                    candidate_names,
                    expected,
                    actual,
                    case.snapshot,
                    case.sources,
                )
                return (
                    PlannerSweepSummary(
                        seed + 1,
                        viable_cases,
                        segment_length,
                        horizon,
                        total_bullets,
                        candidate_actions,
                        tuple(sorted(best_sizes.items())),
                        expanded_states,
                        generated_transitions,
                        tuple(elapsed.items()),
                    ),
                    shrink_planner_mismatch(
                        mismatch,
                        planner,
                        oracle_planner,
                    ),
                )

    return (
        PlannerSweepSummary(
            seeds,
            viable_cases,
            segment_length,
            horizon,
            total_bullets,
            candidate_actions,
            tuple(sorted(best_sizes.items())),
            expanded_states,
            generated_transitions,
            tuple(elapsed.items()),
        ),
        None,
    )
