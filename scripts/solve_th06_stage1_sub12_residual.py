#!/usr/bin/env python3
"""Compile and hold out the Stage 1/sub12 residual feedback tube."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from th06.barrage_lab.feedback import (
    CompiledFeedbackPolicy,
    FeedbackSample,
    HELD_MISMATCH_PENALTY,
    HistoricalClearDemonstrator,
    POSITION_SCALE,
    parse_seed_range,
    samples_by_time,
)
from th06.barrage_lab.assets import load_stage_ecl_program
from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.stateful import run_closed_loop
from th06.model import CONTROL_ACTIONS, action_from_input
from th06.routes.phase import ecl_subroutine_index


SUBROUTINE = 12
START_LOCAL_TIME = 61
EXIT_LOCAL_TIME = 180


def _sub12_boss(snapshot):
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    if len(bosses) != 1 or ecl_subroutine_index(bosses[0]) != SUBROUTINE:
        raise ValueError("workload state is not the unique Stage 1 sub12 boss")
    return bosses[0]


def _left_sub12(snapshot) -> bool:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    return len(bosses) != 1 or ecl_subroutine_index(bosses[0]) != SUBROUTINE


def _sub12_time(snapshot) -> int:
    return _sub12_boss(snapshot).ecl_time


def run_residual(snapshot, policy, delivery_seed: int):
    boss = _sub12_boss(snapshot)
    return run_closed_loop(
        snapshot,
        policy,
        frames=EXIT_LOCAL_TIME - boss.ecl_time + 2,
        delivery_seed=delivery_seed,
        battle_world=True,
        stop_when=_left_sub12,
        stop_outcome="phase-exit",
    )


class TrackingCompiledPolicy:
    def __init__(self, samples: tuple[FeedbackSample, ...]) -> None:
        self.samples = samples_by_time(samples)
        self.reference = CompiledFeedbackPolicy(samples, _sub12_time)
        self.distances: list[int] = []

    def __call__(self, snapshot):
        boss = _sub12_boss(snapshot)
        current = action_from_input(snapshot.input_mask)
        x_scaled = round(snapshot.x * POSITION_SCALE)
        y_scaled = round(snapshot.y * POSITION_SCALE)
        distances = tuple(
            (sample.x_quarter - x_scaled) ** 2
            + (sample.y_quarter - y_scaled) ** 2
            + (
                0
                if CONTROL_ACTIONS[sample.held_action] == current
                else HELD_MISMATCH_PENALTY
            )
            for sample in self.samples.get(boss.ecl_time, ())
        )
        if distances:
            self.distances.append(min(distances))
        return self.reference(snapshot)


def _python_data(
    samples: tuple[FeedbackSample, ...],
    *,
    artifact_sha256: str,
    ecl_sha256: str,
    training_seeds: tuple[int, ...],
    holdout_max_distance_sq: int,
    maximum_feedback_distance_sq: int,
) -> str:
    grouped = samples_by_time(samples)
    lines = [
        '"""Generated Stage 1/sub12 residual feedback-tube policy data."""',
        "",
        "# Regenerate with ``scripts/solve_th06_stage1_sub12_residual.py",
        "# --emit-python``. Physical frame and delivery-seed identities are",
        "# provenance only and never runtime branch keys.",
        "",
        "POLICY_SCHEMA = 1",
        f'ARTIFACT_SHA256 = "{artifact_sha256}"',
        f'ECL_SHA256 = "{ecl_sha256}"',
        f"TRAINING_DELIVERY_SEEDS = {training_seeds!r}",
        f"POSITION_SCALE = {POSITION_SCALE}",
        f"HELD_MISMATCH_PENALTY = {HELD_MISMATCH_PENALTY}",
        f"HOLDOUT_MAX_DISTANCE_SQ = {holdout_max_distance_sq}",
        f"MAX_FEEDBACK_DISTANCE_SQ = {maximum_feedback_distance_sq}",
        "# local_time -> (x_scaled, y_scaled, held_action, proposal)",
        "SAMPLES = (",
    ]
    for local_time, values in grouped.items():
        encoded = tuple(
            (
                sample.x_quarter,
                sample.y_quarter,
                sample.held_action,
                sample.proposed_action,
            )
            for sample in values
        )
        lines.append(f"    ({local_time}, {encoded!r}),")
    lines.extend((")", ""))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--entry-frame", type=int, default=6070)
    parser.add_argument("--training-seeds", default="0,1,2,3")
    parser.add_argument("--holdout-seeds", default="16:48")
    parser.add_argument("--emit-python", action="store_true")
    args = parser.parse_args()

    training_seeds = parse_seed_range(args.training_seeds)
    holdout_seeds = parse_seed_range(args.holdout_seeds)
    if not training_seeds or not holdout_seeds:
        raise ValueError("training and holdout delivery sets cannot be empty")
    history = load_failure_history(args.artifact)
    try:
        root = next(
            snapshot for snapshot in history if snapshot.frame == args.entry_frame
        )
    except StopIteration as exc:
        raise ValueError(f"entry frame {args.entry_frame} is not retained") from exc
    boss = _sub12_boss(root)
    if boss.ecl_time != START_LOCAL_TIME:
        raise ValueError("sub12 workload does not begin at residual t61")

    samples: list[FeedbackSample] = []
    training = tuple(
        run_residual(
            root,
            HistoricalClearDemonstrator(samples, _sub12_time),
            seed,
        )
        for seed in training_seeds
    )
    if any(result.outcome != "phase-exit" for result in training):
        raise RuntimeError("historical controller failed the training residual")
    compiled_samples = tuple(
        sample for sample in samples
        if START_LOCAL_TIME <= sample.local_time < EXIT_LOCAL_TIME
    )

    holdout = []
    distances: list[int] = []
    for seed in holdout_seeds:
        policy = TrackingCompiledPolicy(compiled_samples)
        holdout.append(run_residual(root, policy, seed))
        distances.extend(policy.distances)
    if any(result.outcome != "phase-exit" for result in holdout):
        raise RuntimeError("compiled policy failed a disjoint delivery holdout")
    if not distances:
        raise RuntimeError("holdout produced no feedback-distance evidence")
    holdout_max_distance_sq = max(distances)
    maximum_feedback_distance_sq = 1 << (holdout_max_distance_sq - 1).bit_length()

    if args.emit_python:
        program = load_stage_ecl_program(args.archive, 1)
        print(_python_data(
            compiled_samples,
            artifact_sha256=hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
            ecl_sha256=program.sha256,
            training_seeds=training_seeds,
            holdout_max_distance_sq=holdout_max_distance_sq,
            maximum_feedback_distance_sq=maximum_feedback_distance_sq,
        ), end="")
        return 0

    print(json.dumps({
        "entry": {
            "frame": root.frame,
            "subroutine": SUBROUTINE,
            "local_time": boss.ecl_time,
        },
        "training": {
            "delivery_seeds": training_seeds,
            "outcomes": dict(Counter(result.outcome for result in training)),
            "worst_clearance": min(
                result.minimum_clearance for result in training
            ),
            "maximum_commands": max(result.commands for result in training),
        },
        "compiled": {
            "samples": len(compiled_samples),
            "source_clocks": len(samples_by_time(compiled_samples)),
            "holdout_max_distance_sq": holdout_max_distance_sq,
            "maximum_feedback_distance_sq": maximum_feedback_distance_sq,
        },
        "holdout": {
            "delivery_seeds": holdout_seeds,
            "outcomes": dict(Counter(result.outcome for result in holdout)),
            "minimum_survived_frames": min(
                result.survived_frames for result in holdout
            ),
            "worst_clearance": min(
                result.minimum_clearance for result in holdout
            ),
            "maximum_commands": max(result.commands for result in holdout),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
