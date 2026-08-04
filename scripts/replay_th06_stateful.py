#!/usr/bin/env python3
"""Replay physical transitions and fuzz source-stepped solver sequences."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from functools import partial
import json
from pathlib import Path
import time

from th06.barrage_lab.assets import load_ecl_bullet_catalogue
from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.generator import (
    BARRAGE_FAMILIES,
    horizontal_band_count,
    runtime_barrage_template,
)
from th06.barrage_lab.stateful import (
    ExactTerminalPolicy,
    NativeTerminalPolicy,
    PolicyAdvantage,
    TERMINAL_METRICS,
    derive_nominal_battle_worlds,
    physical_step_parity,
    run_closed_loop,
    run_stateful_sweep,
    shrink_horizon_advantage,
    shrink_policy_advantage,
    step_closed_world,
    sweep_initial_snapshot,
)
from th06.model import CONTROL_ACTIONS


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
        "--barrage-family", choices=BARRAGE_FAMILIES, default="mixed",
        help="source-geometry family for mature barrages and future births",
    )
    parser.add_argument(
        "--physical-initial-world", action="store_true",
        help=(
            "start each seed from a complete captured bullet world instead "
            "of regenerating only its density/context"
        ),
    )
    parser.add_argument(
        "--physical-battle-world", action="store_true",
        help=(
            "retain captured bullets, emitters, bodies, RNG, and timeline; "
            "requires --native and --birth-events 0"
        ),
    )
    parser.add_argument(
        "--initial-frames",
        help=(
            "comma-separated captured frames used as physical initial "
            "worlds (defaults to the retained history)"
        ),
    )
    parser.add_argument(
        "--battle-warmup-frames", type=int, default=0,
        help=(
            "derive each physical battle corpus case through a varied 1..N "
            "frame Hard-safe nominal rollout before measuring it"
        ),
    )
    parser.add_argument(
        "--minimum-horizontal-bands", type=int, default=0,
        help=(
            "retain only physical battle roots with at least this many "
            "mature lateral strips (corpus coverage only)"
        ),
    )
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
        "--continuation",
        choices=("segment", "frame", "hybrid"),
        default="segment",
        help="proposal continuation granularity after physical delivery",
    )
    parser.add_argument(
        "--compare-metrics",
        help="comma-separated terminal metrics to run on identical cases",
    )
    parser.add_argument(
        "--shrink", action="store_true",
        help="minimize the first closed-loop deeper-horizon advantage",
    )
    parser.add_argument(
        "--shrink-comparison", choices=TERMINAL_METRICS,
        help="minimize the first win over the first compared metric",
    )
    parser.add_argument(
        "--shrink-seed", type=int,
        help="specific winning comparison seed to minimize",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    horizons = tuple(int(value) for value in args.horizons.split(","))
    if (
        args.seeds <= 0
        or args.frames <= 0
        or args.birth_events < 0
        or args.battle_warmup_frames < 0
        or args.minimum_horizontal_bands < 0
    ):
        raise ValueError("seeds and frames must be positive")
    if args.corpus_density_scale <= 0.0:
        raise ValueError("corpus density scale must be positive")
    if args.physical_initial_world and args.physical_battle_world:
        raise ValueError("choose one physical initial-world mode")
    if (
        args.battle_warmup_frames or args.minimum_horizontal_bands
    ) and not args.physical_battle_world:
        raise ValueError(
            "battle warmup and band filtering require --physical-battle-world"
        )
    if args.physical_battle_world and (
        not args.native or args.birth_events != 0
    ):
        raise ValueError(
            "physical battle replay requires --native --birth-events 0"
        )
    if args.physical_battle_world and (
        args.shrink or args.shrink_comparison is not None
    ):
        raise ValueError(
            "battle-world shrinking is not implemented; select fixed frames"
        )

    history = load_failure_history(args.artifact)
    if args.initial_frames:
        if not (args.physical_initial_world or args.physical_battle_world):
            raise ValueError("--initial-frames requires a physical world mode")
        requested = tuple(
            int(value) for value in args.initial_frames.split(",")
        )
        by_frame = {snapshot.frame: snapshot for snapshot in history}
        missing = set(requested) - set(by_frame)
        if not requested or missing:
            raise ValueError(
                f"physical initial frames missing from artifact: "
                f"{sorted(missing)}"
            )
        selected_history = tuple(by_frame[frame] for frame in requested)
    else:
        selected_history = history
    if args.minimum_horizontal_bands:
        selected_history = tuple(
            snapshot for snapshot in selected_history
            if horizontal_band_count(snapshot.bullets)
            >= args.minimum_horizontal_bands
        )
        if not selected_history:
            raise ValueError(
                "no physical battle root meets the horizontal-band minimum"
            )
    output = {
        "artifact": str(args.artifact),
        "physical_step_parity": asdict(physical_step_parity(history)),
        "stateful_sweep": None,
        "first_advantage": None,
    }
    if args.archive is not None:
        metrics = (
            tuple(args.compare_metrics.split(","))
            if args.compare_metrics
            else (args.metric,)
        )
        if not metrics or len(set(metrics)) != len(metrics):
            raise ValueError("comparison metrics must be unique")
        unknown = set(metrics) - set(TERMINAL_METRICS)
        if unknown:
            raise ValueError(f"unknown terminal metrics: {sorted(unknown)}")
        if args.native:
            from th06.kernels.safety import NativeSafetyKernel
            kernel = NativeSafetyKernel()
        raw = json.loads(args.artifact.read_text(encoding="utf-8"))
        raw_history = raw.get("snapshot_history") or (raw["snapshot"],)
        templates = (
            ()
            if args.physical_initial_world or args.physical_battle_world
            else tuple(
                runtime_barrage_template(item, args.corpus_density_scale)
                for item in raw_history
            )
        )
        physical_worlds = (
            selected_history if args.physical_initial_world else ()
        )
        battle_worlds = (
            selected_history if args.physical_battle_world else ()
        )
        battle_derivation = None
        if battle_worlds and args.battle_warmup_frames:
            battle_worlds, battle_derivation = derive_nominal_battle_worlds(
                battle_worlds,
                cases=args.seeds,
                maximum_warmup_frames=args.battle_warmup_frames,
                certifier=lambda snapshot: kernel.certify_selected(
                    snapshot,
                    4,
                    CONTROL_ACTIONS,
                    collision_margin=0.35,
                ),
            )
            if not battle_worlds:
                raise RuntimeError(
                    "no nominal battle warmup retained fresh Hard authority"
                )
        catalogue = load_ecl_bullet_catalogue(args.archive)
        comparisons = {}
        summaries = {}
        factories = {}
        selected = None
        for metric in metrics:
            policy_factory = (
                partial(
                    NativeTerminalPolicy,
                    kernel=kernel,
                    metric=metric,
                    continuation=args.continuation,
                )
                if args.native
                else partial(
                    ExactTerminalPolicy,
                    metric=metric,
                    continuation=args.continuation,
                )
            )
            factories[metric] = policy_factory
            started = time.perf_counter()
            summary, advantage = run_stateful_sweep(
                catalogue,
                seeds=args.seeds,
                frames=args.frames,
                horizons=horizons,
                runtime_templates=templates,
                physical_initial_worlds=physical_worlds,
                physical_battle_worlds=battle_worlds,
                policy_factory=policy_factory,
                birth_events_per_case=args.birth_events,
                barrage_family=args.barrage_family,
            )
            comparisons[metric] = {
                "elapsed_seconds": time.perf_counter() - started,
                "summary": asdict(summary),
            }
            summaries[metric] = summary
            if selected is None or metric == args.metric:
                selected = (metric, summary, advantage, policy_factory)
        baseline_metric = metrics[0]
        baseline_summary = summaries[baseline_metric]
        baseline_by_horizon = {
            horizon: {seed: values for seed, *values in cases}
            for horizon, cases in baseline_summary.case_metrics
        }
        for metric in metrics[1:]:
            paired = []
            for horizon, cases in summaries[metric].case_metrics:
                baseline = baseline_by_horizon[horizon]
                wins = []
                losses = []
                survival_delta = 0
                command_delta = 0
                minimum_clearance_delta = 0.0
                for seed, _outcome, survived, commands, clearance in cases:
                    (
                        _base_outcome,
                        base_survived,
                        base_commands,
                        base_clearance,
                    ) = baseline[seed]
                    survival_delta += survived - base_survived
                    command_delta += commands - base_commands
                    minimum_clearance_delta += clearance - base_clearance
                    if survived > base_survived:
                        wins.append(seed)
                    elif survived < base_survived:
                        losses.append(seed)
                paired.append({
                    "horizon": horizon,
                    "wins": wins,
                    "losses": losses,
                    "ties": len(cases) - len(wins) - len(losses),
                    "survival_frame_delta": survival_delta,
                    "command_delta": command_delta,
                    "minimum_clearance_delta": minimum_clearance_delta,
                })
            comparisons[metric]["paired_vs_first"] = paired
        if args.shrink_comparison:
            candidate_metric = args.shrink_comparison
            if candidate_metric == baseline_metric or candidate_metric not in metrics:
                raise ValueError(
                    "shrink comparison must be a non-baseline compared metric"
                )
            paired = comparisons[candidate_metric]["paired_vs_first"]
            first_win = next(
                (
                    (
                        item["horizon"],
                        args.shrink_seed
                        if args.shrink_seed is not None
                        else item["wins"][0],
                    )
                    for item in paired
                    if (
                        args.shrink_seed in item["wins"]
                        if args.shrink_seed is not None
                        else bool(item["wins"])
                    )
                ),
                None,
            )
            if args.shrink_seed is not None and first_win is None:
                raise ValueError("requested shrink seed is not a policy win")
            if first_win is not None:
                from th06.barrage_lab.generator import (
                    generate_barrage_births,
                )
                horizon, seed = first_win
                snapshot = sweep_initial_snapshot(
                    catalogue,
                    seed,
                    runtime_templates=templates,
                    physical_initial_worlds=physical_worlds,
                    barrage_family=args.barrage_family,
                )
                schedule = generate_barrage_births(
                    catalogue,
                    seed,
                    snapshot,
                    frames=args.frames,
                    events=args.birth_events,
                    barrage_family=args.barrage_family,
                )
                baseline_result = run_closed_loop(
                    snapshot,
                    factories[baseline_metric](horizon),
                    frames=args.frames,
                    delivery_seed=seed,
                    birth_schedule=schedule,
                )
                candidate_result = run_closed_loop(
                    snapshot,
                    factories[candidate_metric](horizon),
                    frames=args.frames,
                    delivery_seed=seed,
                    birth_schedule=schedule,
                )
                reduced = shrink_policy_advantage(
                    PolicyAdvantage(
                        seed,
                        horizon,
                        baseline_metric,
                        candidate_metric,
                        baseline_result,
                        candidate_result,
                        snapshot,
                        schedule,
                    ),
                    frames=args.frames,
                    delivery_seed=seed,
                    baseline_factory=factories[baseline_metric],
                    candidate_factory=factories[candidate_metric],
                )
                output["reduced_policy_advantage"] = {
                    "seed": reduced.seed,
                    "horizon": reduced.horizon,
                    "baseline_metric": reduced.baseline_name,
                    "candidate_metric": reduced.candidate_name,
                    "baseline": asdict(reduced.baseline),
                    "candidate": asdict(reduced.candidate),
                    "snapshot": asdict(reduced.snapshot),
                    "birth_schedule": [
                        asdict(event) for event in reduced.birth_schedule
                    ],
                }
                decision_divergence = next(
                    (
                        (left, right)
                        for left, right in zip(
                            reduced.baseline.decision_trace,
                            reduced.candidate.decision_trace,
                        )
                        if left != right
                    ),
                    None,
                )
                if decision_divergence is not None and args.native:
                    left, right = decision_divergence
                    decision_frame = min(left[0], right[0])
                    state = reduced.snapshot
                    births_by_update = {
                        update: tuple(
                            (event.pattern, event.origin)
                            for event in reduced.birth_schedule
                            if event.update == update
                        )
                        for update in {
                            event.update for event in reduced.birth_schedule
                        }
                    }
                    action_by_name = {
                        action.name: action for action in CONTROL_ACTIONS
                    }
                    for update in range(
                        decision_frame - reduced.snapshot.frame
                    ):
                        state = step_closed_world(
                            state,
                            action_by_name[reduced.baseline.actions[update]],
                            births_by_update.get(update, ()),
                        )
                    hard = kernel.certify_selected(
                        state,
                        4,
                        CONTROL_ACTIONS,
                        collision_margin=0.35,
                    )
                    counts = kernel.terminal_counts(
                        state,
                        hard,
                        4,
                        horizon,
                        collision_margin=0.35,
                    )
                    guidance = kernel.terminal_guidance(
                        state,
                        hard,
                        4,
                        horizon,
                        collision_margin=0.35,
                    )
                    output["reduced_policy_advantage"][
                        "first_decision_divergence"
                    ] = {
                        "baseline": left,
                        "candidate": right,
                        "x": state.x,
                        "y": state.y,
                        "bullets": len(state.bullets),
                        "terminal": {
                            action.name: {
                                "count": counts[action],
                                "free_clearance": guidance[action].free_clearance,
                            }
                            for action in counts
                        },
                    }
        output["stateful_comparisons"] = comparisons
        metric, summary, advantage, policy_factory = selected
        output["stateful_sweep"] = asdict(summary)
        output["terminal_metric"] = metric
        output["continuation"] = args.continuation
        output["barrage_family"] = args.barrage_family
        output["initial_world"] = (
            "physical-battle-nominal"
            if args.physical_battle_world
            else "physical-bullet-ablation"
            if args.physical_initial_world
            else "source-generated"
        )
        output["runtime_worlds"] = len(
            battle_worlds
            if battle_worlds
            else physical_worlds if physical_worlds else templates
        )
        output["minimum_horizontal_bands"] = args.minimum_horizontal_bands
        output["battle_warmup"] = (
            {
                "requested_cases": battle_derivation.requested_cases,
                "generated_cases": battle_derivation.generated_cases,
                "maximum_warmup_frames": (
                    battle_derivation.maximum_warmup_frames
                ),
                "outcomes": battle_derivation.outcomes,
                "total_warmup_updates": (
                    battle_derivation.total_warmup_updates
                ),
                "total_born_bullets": battle_derivation.total_born_bullets,
                "source_root_frames": battle_derivation.source_root_frames,
            }
            if battle_derivation is not None
            else None
        )
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
