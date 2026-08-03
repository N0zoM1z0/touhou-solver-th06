"""Correctness sweep and mismatch reduction for source-derived barrages."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import time
from typing import Callable

from ..model import CONTROL_ACTIONS, Snapshot
from ..safety import COLLISION_MARGIN, certify_actions
from .assets import EclBulletOpcode
from .generator import BarrageCase, generate_barrage_case
from .oracle import certify_linear_source


Certifier = Callable[[Snapshot, int], tuple[str, ...]]


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


@dataclass(frozen=True)
class SweepMismatch:
    seed: int
    implementation: str
    expected: tuple[str, ...]
    actual: tuple[str, ...]
    snapshot: Snapshot


@dataclass(frozen=True)
class SweepSummary:
    seeds: int
    horizon: int
    generated_bullets: int
    safe_set_sizes: tuple[tuple[int, int], ...]
    elapsed_seconds: float


def shrink_mismatch(
    mismatch: SweepMismatch,
    horizon: int,
    certifier: Certifier,
) -> SweepMismatch:
    """Delete chunks while the source-oracle disagreement remains."""
    bullets = list(mismatch.snapshot.bullets)

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
    return replace(
        mismatch,
        expected=certify_linear_source(snapshot, horizon).actions,
        actual=certifier(snapshot, horizon),
        snapshot=snapshot,
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
                    seed, name, expected, actual, case.snapshot
                )
                return (
                    SweepSummary(
                        seed + 1, horizon, total_bullets,
                        tuple(sorted(safe_sizes.items())),
                        time.perf_counter() - started,
                    ),
                    shrink_mismatch(mismatch, horizon, certifier),
                )
    return (
        SweepSummary(
            seeds, horizon, total_bullets,
            tuple(sorted(safe_sizes.items())),
            time.perf_counter() - started,
        ),
        None,
    )
