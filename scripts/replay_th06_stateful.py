#!/usr/bin/env python3
"""Replay physical transitions and fuzz source-stepped solver sequences."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from th06.barrage_lab.assets import load_ecl_bullet_catalogue
from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.generator import runtime_barrage_template
from th06.barrage_lab.stateful import (
    ExactTerminalPolicy,
    NativeTerminalPolicy,
    TERMINAL_METRICS,
    physical_step_parity,
    run_stateful_sweep,
    shrink_horizon_advantage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "artifact", type=Path,
        help="online failure artifact containing snapshot_history",
    )
    parser.add_argument(
        "--archive", type=Path,
        help="installed TH06 ST.DAT; enables stateful generated fuzzing",
    )
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument(
        "--birth-events", type=int, default=3,
        help="source-valid synthetic ECL volleys scheduled per sequence",
    )
    parser.add_argument(
        "--horizons", default="8,12,16",
        help="sorted exact terminal horizons to compare",
    )
    parser.add_argument("--corpus-density-scale", type=float, default=1.0)
    parser.add_argument(
        "--native", action="store_true",
        help="use the parity-checked native planner for the stateful sweep",
    )
    parser.add_argument(
        "--metric", choices=TERMINAL_METRICS, default="count",
        help="soft terminal ranking to evaluate in the closed loop",
    )
    parser.add_argument(
        "--shrink", action="store_true",
        help="minimize the first closed-loop deeper-horizon advantage",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    horizons = tuple(int(value) for value in args.horizons.split(","))
    if args.seeds <= 0 or args.frames <= 0 or args.birth_events < 0:
        raise ValueError("seeds and frames must be positive")
    if args.corpus_density_scale <= 0.0:
        raise ValueError("corpus density scale must be positive")

    history = load_failure_history(args.artifact)
    output = {
        "artifact": str(args.artifact),
        "physical_step_parity": asdict(physical_step_parity(history)),
        "stateful_sweep": None,
        "first_advantage": None,
    }
    if args.archive is not None:
        if args.native:
            from th06.kernels.safety import NativeSafetyKernel
            kernel = NativeSafetyKernel()
            policy_factory = lambda horizon: NativeTerminalPolicy(
                horizon, kernel, args.metric
            )
        else:
            policy_factory = lambda horizon: ExactTerminalPolicy(
                horizon, args.metric
            )
        raw = json.loads(args.artifact.read_text(encoding="utf-8"))
        raw_history = raw.get("snapshot_history") or (raw["snapshot"],)
        templates = tuple(
            runtime_barrage_template(item, args.corpus_density_scale)
            for item in raw_history
        )
        catalogue = load_ecl_bullet_catalogue(args.archive)
        summary, advantage = run_stateful_sweep(
            catalogue,
            seeds=args.seeds,
            frames=args.frames,
            horizons=horizons,
            runtime_templates=templates,
            policy_factory=policy_factory,
            birth_events_per_case=args.birth_events,
        )
        output["stateful_sweep"] = asdict(summary)
        output["terminal_metric"] = args.metric
        if advantage is not None and args.shrink:
            advantage = shrink_horizon_advantage(
                advantage,
                frames=args.frames,
                delivery_seed=advantage.seed,
                policy_factory=policy_factory,
            )
        if advantage is not None:
            output["first_advantage"] = {
                "seed": advantage.seed,
                "shallow_horizon": advantage.shallow_horizon,
                "deep_horizon": advantage.deep_horizon,
                "shallow": asdict(advantage.shallow),
                "deep": asdict(advantage.deep),
                "reduced_bullets": len(advantage.snapshot.bullets),
                "birth_schedule": (
                    [asdict(event) for event in advantage.birth_schedule]
                    if args.shrink else len(advantage.birth_schedule)
                ),
                "snapshot": asdict(advantage.snapshot) if args.shrink else None,
            }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
