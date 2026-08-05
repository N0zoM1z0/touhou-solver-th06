#!/usr/bin/env python3
"""Screen the complete Stage 1 second-nonspell source family.

The retained physical root is sub16 immediately after the first-spell timer
callback.  Sub16 contains a source-authored no-birth entry through t199 and
CALLs sub18 at t200.  Sub18/19/20/21 then form an RNG-selected attack family
until the life or timer callback enters sub23.  A case succeeds only at that
stable source boundary; short fixed-frame survival is not accepted.

All policies rank actions inside the unchanged native Hard set.  Results are
offline evidence, never action authority or a physical clear.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
import time

from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.stateful import NativeTerminalPolicy, run_closed_loop
from th06.kernels.safety import NativeSafetyKernel
from th06.model import Snapshot
from th06.routes.phase import ecl_subroutine_index
from th06.solver import Solver


ENTRY_SUBROUTINE = 16
ATTACK_SUBROUTINES = frozenset((18, 19, 20, 21))
PHASE_SUBROUTINES = ATTACK_SUBROUTINES | {ENTRY_SUBROUTINE}
ENTRY_ATTACK_TIME = 200
TIMER_LIMIT = 1800
BOTTOM_CENTER = (192.0, 380.0)


@dataclass(frozen=True)
class Candidate:
    metric: str
    horizon: int


CANDIDATES = {
    "production": Candidate("production", 8),
    "pv6": Candidate("policy-volume", 6),
    "pv8": Candidate("policy-volume", 8),
    "pv10": Candidate("policy-volume", 10),
    "pv12": Candidate("policy-volume", 12),
    "cc6": Candidate("count-clearance", 6),
    "cc8": Candidate("count-clearance", 8),
    "cfc8": Candidate("constant-frontier-count", 8),
}


def _boss(snapshot: Snapshot):
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    if len(bosses) != 1:
        raise ValueError("workload state does not have one stable boss")
    return bosses[0]


def _spell_active(snapshot: Snapshot) -> bool:
    return bool(snapshot.player_attack and snapshot.player_attack.spell_active)


def _left_phase(snapshot: Snapshot) -> bool:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    return (
        len(bosses) != 1
        or ecl_subroutine_index(bosses[0]) not in PHASE_SUBROUTINES
        or _spell_active(snapshot)
    )


def _roots(
    paths: tuple[Path, ...],
    entry_frame: int | None,
) -> tuple[tuple[Path, Snapshot], ...]:
    selected = []
    for path in paths:
        history = load_failure_history(path)
        candidates = []
        for snapshot in history:
            bosses = tuple(
                spawner for spawner in snapshot.spawners if spawner.is_boss
            )
            if len(bosses) != 1 or _spell_active(snapshot):
                continue
            subroutine = ecl_subroutine_index(bosses[0])
            stable_family = (
                subroutine in ATTACK_SUBROUTINES
                and not snapshot.despawning_bullets
                and snapshot.player_attack is not None
            )
            clean_entry = (
                subroutine == ENTRY_SUBROUTINE
                and bosses[0].ecl_time < ENTRY_ATTACK_TIME
                and not snapshot.despawning_bullets
                and snapshot.player_attack is not None
            )
            if (
                (stable_family or clean_entry)
                and (entry_frame is None or snapshot.frame == entry_frame)
            ):
                candidates.append(snapshot)
        if not candidates:
            suffix = "" if entry_frame is None else f" at frame {entry_frame}"
            raise ValueError(
                f"{path} has no exactly step-able second-nonspell root{suffix}"
            )
        selected.append((path, candidates[0]))
    return tuple(selected)


class FamilyPolicy:
    """Keep proposal commitment private to each source subroutine."""

    def __init__(self, kernel, candidate: Candidate) -> None:
        self.entry = NativeTerminalPolicy(
            4, kernel=kernel, metric="policy-volume", target=BOTTOM_CENTER
        )
        self.attacks = {
            subroutine: NativeTerminalPolicy(
                candidate.horizon,
                kernel=kernel,
                metric=candidate.metric,
            )
            for subroutine in ATTACK_SUBROUTINES
        }

    def __call__(self, snapshot: Snapshot):
        subroutine = ecl_subroutine_index(_boss(snapshot))
        if subroutine == ENTRY_SUBROUTINE:
            return self.entry(snapshot)
        return self.attacks[subroutine](snapshot)


class ProductionPolicy:
    def __init__(self) -> None:
        self.solver = Solver()
        self.reasons: Counter[str] = Counter()
        self.sources: Counter[str] = Counter()

    def __call__(self, snapshot: Snapshot):
        decision = self.solver.decide(snapshot)
        self.reasons[decision.reason] += 1
        self.sources[decision.proposal_source or ""] += 1
        return decision.action


class TimedPolicy:
    def __init__(self, policy) -> None:
        self.policy = policy
        self.elapsed_ms: list[float] = []

    def __call__(self, snapshot: Snapshot):
        started = time.perf_counter()
        action = self.policy(snapshot)
        self.elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        return action


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _parse_candidates(raw: str) -> tuple[str, ...]:
    names = tuple(value.strip() for value in raw.split(",") if value.strip())
    unknown = set(names) - set(CANDIDATES)
    if not names or unknown:
        raise ValueError(f"unknown/empty candidates: {sorted(unknown)}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path, nargs="+")
    parser.add_argument("--entry-frame", type=int)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument(
        "--candidates",
        default="pv6,pv8,pv10,cc6,cc8,cfc8",
        help=f"comma-separated names from {','.join(CANDIDATES)}",
    )
    args = parser.parse_args()
    if args.seeds <= 0:
        raise ValueError("seeds must be positive")

    roots = _roots(tuple(args.artifacts), args.entry_frame)
    names = _parse_candidates(args.candidates)
    kernel = NativeSafetyKernel()
    output: dict[str, object] = {
        "entries": tuple({
            "artifact": str(path),
            "frame": root.frame,
            "subroutine": ecl_subroutine_index(_boss(root)),
            "local_time": _boss(root).ecl_time,
            "boss_timer": _boss(root).boss_timer,
            "life": _boss(root).life,
            "x": root.x,
            "y": root.y,
        } for path, root in roots),
        "source_contract": {
            "entry_attack_time": ENTRY_ATTACK_TIME,
            "attack_subroutines": tuple(sorted(ATTACK_SUBROUTINES)),
            "exit_subroutine": 23,
        },
        "candidates": {},
    }

    for name in names:
        candidate = CANDIDATES[name]
        results = []
        case_rows = []
        timings: list[float] = []
        reasons: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        started = time.perf_counter()
        for path, root in roots:
            frames = max(1, TIMER_LIMIT - _boss(root).boss_timer + 4)
            for seed in range(args.seed_start, args.seed_start + args.seeds):
                selected = (
                    ProductionPolicy()
                    if candidate.metric == "production"
                    else FamilyPolicy(kernel, candidate)
                )
                policy = TimedPolicy(selected)
                result = run_closed_loop(
                    root,
                    policy,
                    frames=frames,
                    delivery_seed=seed,
                    battle_world=True,
                    stop_when=_left_phase,
                    stop_outcome="phase-exit",
                )
                results.append(result)
                timings.extend(policy.elapsed_ms)
                if isinstance(selected, ProductionPolicy):
                    reasons.update(selected.reasons)
                    sources.update(selected.sources)
                case_rows.append({
                    "artifact": path.name,
                    "frame": root.frame,
                    "seed": seed,
                    "outcome": result.outcome,
                    "survived_frames": result.survived_frames,
                    "minimum_clearance": result.minimum_clearance,
                    "commands": result.commands,
                    "born_bullets": result.born_bullets,
                })
        output["candidates"][name] = {
            "metric": candidate.metric,
            "horizon": candidate.horizon,
            "outcomes": dict(Counter(result.outcome for result in results)),
            "cases": case_rows,
            "minimum_survived_frames": min(
                result.survived_frames for result in results
            ),
            "worst_clearance": min(
                result.minimum_clearance for result in results
            ),
            "maximum_commands": max(result.commands for result in results),
            "mean_commands": statistics.fmean(
                result.commands for result in results
            ),
            "decision_ms": {
                "count": len(timings),
                "median": statistics.median(timings),
                "p90": _percentile(timings, 0.90),
                "p99": _percentile(timings, 0.99),
                "maximum": max(timings),
            },
            "decision_reasons": dict(reasons),
            "proposal_sources": dict(sources),
            "elapsed_seconds": time.perf_counter() - started,
        }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
