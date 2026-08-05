#!/usr/bin/env python3
"""Screen complete Stage 1/sub22 spell policies from a physical root.

The installed Stage 1 ECL makes sub22 a repeated source-clock cycle, not an
isolated barrage: four Hard attack groups at local t122..t128 are followed by
the t228 random movement and a jump back into the attack body.  This workload
therefore stops only when the physical battle world leaves sub22/spell state
(or reaches the source timer bound), rather than declaring success after a
short arbitrary window.

Every candidate selects only among actions certified by the unchanged native
Hard kernel.  This script is offline evidence and has no runtime authority.
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


SUBROUTINE = 22
ATTACK_START = 120
TIMER_LIMIT = 1500
BOTTOM_CENTER = (192.0, 380.0)


@dataclass(frozen=True)
class Candidate:
    metric: str
    horizon: int
    target: tuple[float, float] | None = None


CANDIDATES = {
    "production": Candidate("production", 10),
    "bottom-h4": Candidate("policy-volume", 4, BOTTOM_CENTER),
    "pv6": Candidate("policy-volume", 6),
    "pv8": Candidate("policy-volume", 8),
    "pv10": Candidate("policy-volume", 10),
    "pv12": Candidate("policy-volume", 12),
    "bottom-pv6": Candidate("policy-volume", 6, BOTTOM_CENTER),
    "bottom-pv8": Candidate("policy-volume", 8, BOTTOM_CENTER),
    "cc6": Candidate("count-clearance", 6),
    "cc8": Candidate("count-clearance", 8),
    "cfc6": Candidate("constant-frontier-count", 6),
    "cfc8": Candidate("constant-frontier-count", 8),
}


def _boss(snapshot: Snapshot):
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    if len(bosses) != 1:
        raise ValueError("workload root does not have one stable boss")
    return bosses[0]


def _spell_active(snapshot: Snapshot) -> bool:
    return bool(snapshot.player_attack and snapshot.player_attack.spell_active)


def _left_spell(snapshot: Snapshot) -> bool:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    return (
        len(bosses) != 1
        or ecl_subroutine_index(bosses[0]) != SUBROUTINE
        or not _spell_active(snapshot)
    )


def _root(path: Path, entry_frame: int | None) -> Snapshot:
    history = load_failure_history(path)
    candidates = tuple(
        snapshot
        for snapshot in history
        if len(tuple(item for item in snapshot.spawners if item.is_boss)) == 1
        and ecl_subroutine_index(_boss(snapshot)) == SUBROUTINE
        and _spell_active(snapshot)
        and _boss(snapshot).ecl_time >= ATTACK_START
    )
    if entry_frame is not None:
        candidates = tuple(
            snapshot for snapshot in candidates if snapshot.frame == entry_frame
        )
    if not candidates:
        suffix = "" if entry_frame is None else f" at frame {entry_frame}"
        raise ValueError(f"artifact has no active sub22 attack root{suffix}")
    return candidates[-1]


class TimedPolicy:
    def __init__(self, policy) -> None:
        self.policy = policy
        self.elapsed_ms: list[float] = []

    def __call__(self, snapshot: Snapshot):
        started = time.perf_counter()
        action = self.policy(snapshot)
        self.elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        return action


class ProductionPolicy:
    """Run the real route adapter, deadline, and common publication ranker."""

    def __init__(self) -> None:
        self.solver = Solver()
        self.reasons: Counter[str] = Counter()
        self.sources: Counter[str] = Counter()

    def __call__(self, snapshot: Snapshot):
        decision = self.solver.decide(snapshot)
        self.reasons[decision.reason] += 1
        self.sources[decision.proposal_source or ""] += 1
        return decision.action


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _phase_identity(snapshot: Snapshot) -> str:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    spell = int(_spell_active(snapshot))
    if len(bosses) != 1:
        return f"bosses={len(bosses)}:spell={spell}"
    boss = bosses[0]
    return (
        f"sub={ecl_subroutine_index(boss)}:t={boss.ecl_time}:"
        f"life={boss.life}:timer={boss.timer}:"
        f"timer_cb={boss.timer_callback_sub}:spell={spell}"
    )


def _parse_candidates(raw: str) -> tuple[str, ...]:
    names = tuple(value.strip() for value in raw.split(",") if value.strip())
    unknown = set(names) - set(CANDIDATES)
    if not names or unknown:
        raise ValueError(f"unknown/empty candidates: {sorted(unknown)}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--entry-frame", type=int)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument(
        "--candidates",
        default="bottom-h4,pv6,pv8,cc6,cfc6",
        help=f"comma-separated names from {','.join(CANDIDATES)}",
    )
    args = parser.parse_args()
    if args.seeds <= 0:
        raise ValueError("seeds must be positive")

    names = _parse_candidates(args.candidates)
    root = _root(args.artifact, args.entry_frame)
    boss = _boss(root)
    maximum_frames = max(1, TIMER_LIMIT - boss.ecl_time + 4)
    kernel = NativeSafetyKernel()
    output: dict[str, object] = {
        "entry": {
            "frame": root.frame,
            "x": root.x,
            "y": root.y,
            "subroutine": SUBROUTINE,
            "local_time": boss.ecl_time,
            "life": boss.life,
            "timer_callback_sub": boss.timer_callback_sub,
            "maximum_frames": maximum_frames,
        },
        "source_contract": {
            "attack_times": (122, 124, 126, 128),
            "random_movement_time": 228,
            "timer_limit": TIMER_LIMIT,
        },
        "candidates": {},
    }

    for name in names:
        candidate = CANDIDATES[name]
        results = []
        case_rows = []
        timings: list[float] = []
        exits = []
        reasons: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        started = time.perf_counter()
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            selected_policy = (
                ProductionPolicy()
                if candidate.metric == "production"
                else NativeTerminalPolicy(
                    candidate.horizon,
                    kernel=kernel,
                    metric=candidate.metric,
                    target=candidate.target,
                )
            )
            policy = TimedPolicy(selected_policy)
            states: list[Snapshot] = []
            result = run_closed_loop(
                root,
                policy,
                frames=maximum_frames,
                delivery_seed=seed,
                battle_world=True,
                state_sink=states.append,
                stop_when=_left_spell,
                stop_outcome="phase-exit",
            )
            results.append(result)
            case_rows.append({
                "seed": seed,
                "outcome": result.outcome,
                "survived_frames": result.survived_frames,
                "minimum_clearance": result.minimum_clearance,
                "commands": result.commands,
                "born_bullets": result.born_bullets,
            })
            timings.extend(policy.elapsed_ms)
            if isinstance(selected_policy, ProductionPolicy):
                reasons.update(selected_policy.reasons)
                sources.update(selected_policy.sources)
            exits.append(_phase_identity(states[-1] if states else root))
        output["candidates"][name] = {
            "metric": candidate.metric,
            "horizon": candidate.horizon,
            "target": candidate.target,
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
            "born_bullets": tuple(result.born_bullets for result in results),
            "decision_ms": {
                "count": len(timings),
                "median": statistics.median(timings) if timings else 0.0,
                "p90": _percentile(timings, 0.90),
                "p99": _percentile(timings, 0.99),
                "maximum": max(timings, default=0.0),
            },
            "decision_reasons": dict(reasons),
            "proposal_sources": dict(sources),
            "elapsed_seconds": time.perf_counter() - started,
            "exit_identities": dict(Counter(exits)),
        }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
