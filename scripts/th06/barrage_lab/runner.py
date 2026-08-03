"""Correctness sweep and mismatch reduction for source-derived barrages."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import time
from typing import Callable

from ..guidance import terminal_guidance_scores
from ..model import CONTROL_ACTIONS, SafeAction, Snapshot
from ..safety import COLLISION_MARGIN, certify_actions
from .assets import EclBulletOpcode
from .generator import BarrageCase, generate_barrage_case
from .oracle import certify_linear_source
from .planner import source_terminal_counts


Certifier = Callable[[Snapshot, int], tuple[str, ...]]
Planner = Callable[
    [Snapshot, tuple[str, ...], int, int],
    tuple[tuple[str, int], ...],
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
    expected: tuple[tuple[str, int], ...]
    actual: tuple[tuple[str, int], ...]
    snapshot: Snapshot
    sources: tuple[tuple[str, int, int], ...]

    @property
    def differing_actions(self) -> tuple[str, ...]:
        expected = dict(self.expected)
        actual = dict(self.actual)
        return tuple(
            name for name in self.candidate_names
            if expected.get(name) != actual.get(name)
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
        expected = source_terminal_counts(
            snapshot, names, segment_length, candidate_horizon
        ).counts
        return expected, planner(
            snapshot, names, segment_length, candidate_horizon
        )

    for candidate_horizon in range(segment_length, horizon):
        expected, actual = evaluate(
            mismatch.snapshot, candidate_names, candidate_horizon
        )
        if expected != actual:
            horizon = candidate_horizon
            break

    expected, actual = evaluate(mismatch.snapshot, candidate_names, horizon)
    differing = tuple(
        name for name in candidate_names
        if dict(expected).get(name) != dict(actual).get(name)
    )
    for name in differing:
        one = (name,)
        one_expected, one_actual = evaluate(mismatch.snapshot, one, horizon)
        if one_expected != one_actual:
            candidate_names = one
            expected, actual = one_expected, one_actual
            break

    bullets = list(mismatch.snapshot.bullets)

    def differs(values) -> bool:
        snapshot = replace(mismatch.snapshot, bullets=tuple(values))
        expected_value, actual_value = evaluate(
            snapshot, candidate_names, horizon
        )
        return expected_value != actual_value

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
    extra_certifiers: tuple[tuple[str, Certifier], ...] = (),
) -> tuple[SweepSummary, SweepMismatch | None]:
    certifiers = (("python", python_action_names),) + extra_certifiers
    total_bullets = 0
    safe_sizes = Counter()
    started = time.perf_counter()
    for seed in range(seeds):
        case: BarrageCase = generate_barrage_case(catalogue, seed)
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
    extra_planners: tuple[tuple[str, Planner], ...] = (),
) -> tuple[PlannerSweepSummary, PlannerMismatch | None]:
    """Differentially test production planners on source-valid barrages."""
    planners = (("python", python_terminal_counts),) + extra_planners
    total_bullets = 0
    candidate_actions = 0
    viable_cases = 0
    best_sizes = Counter()
    expanded_states = 0
    generated_transitions = 0
    elapsed = {"oracle": 0.0, **{name: 0.0 for name, _ in planners}}

    for seed in range(seeds):
        case = generate_barrage_case(catalogue, seed)
        total_bullets += len(case.snapshot.bullets)
        candidate_names = certify_linear_source(
            case.snapshot, segment_length
        ).actions
        if not candidate_names:
            continue
        viable_cases += 1
        candidate_actions += len(candidate_names)
        started = time.perf_counter()
        oracle = source_terminal_counts(
            case.snapshot, candidate_names, segment_length, horizon
        )
        elapsed["oracle"] += time.perf_counter() - started
        expanded_states += oracle.expanded_states
        generated_transitions += oracle.generated_transitions
        scores = dict(oracle.counts)
        best = max(scores.values())
        best_sizes[sum(value == best for value in scores.values())] += 1

        for name, planner in planners:
            started = time.perf_counter()
            actual = planner(
                case.snapshot, candidate_names, segment_length, horizon
            )
            elapsed[name] += time.perf_counter() - started
            if actual != oracle.counts:
                mismatch = PlannerMismatch(
                    seed,
                    name,
                    segment_length,
                    horizon,
                    candidate_names,
                    oracle.counts,
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
                    shrink_planner_mismatch(mismatch, planner),
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
