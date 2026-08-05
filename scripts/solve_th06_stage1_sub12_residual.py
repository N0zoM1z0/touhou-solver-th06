#!/usr/bin/env python3
"""Compile and hold out Stage 1/sub12 residual hazard-conditioned tubes.

Each retained physical t61 workload contributes a demonstrated policy basin.
The generated runtime state uses stable source time, player feedback, and the
fresh Hard-4 action mask; physical frame and delivery seed remain provenance.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from th06.barrage_lab.feedback import (
    CompiledFeedbackPolicy,
    FeedbackSample,
    HARD_MASK_MISMATCH_PENALTY,
    HELD_MISMATCH_PENALTY,
    HistoricalClearDemonstrator,
    POSITION_SCALE,
    parse_seed_range,
    samples_by_time,
)
from th06.barrage_lab.assets import load_stage_ecl_program
from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.stateful import run_closed_loop
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
        self.reference = CompiledFeedbackPolicy(
            samples,
            _sub12_time,
            hazard_conditioned=True,
        )
        self.distances = self.reference.feedback_distances

    def __call__(self, snapshot):
        return self.reference(snapshot)


def _python_data(
    samples: tuple[FeedbackSample, ...],
    *,
    workloads: tuple[tuple[str, int], ...],
    ecl_sha256: str,
    training_seeds: tuple[int, ...],
    holdout_max_distance_sq: int,
    maximum_feedback_distance_sq: int,
) -> str:
    grouped = samples_by_time(samples)
    lines = [
        '"""Generated Stage 1/sub12 hazard-conditioned feedback policy."""',
        "",
        "# Regenerate with ``scripts/solve_th06_stage1_sub12_residual.py",
        "# --emit-python``. Physical frame and delivery-seed identities are",
        "# provenance only and never runtime branch keys.  The online hazard",
        "# signature is the already-computed fresh Hard-4 action mask.",
        "",
        "POLICY_SCHEMA = 2",
        f"WORKLOADS = {workloads!r}",
        f'ECL_SHA256 = "{ecl_sha256}"',
        f"TRAINING_DELIVERY_SEEDS = {training_seeds!r}",
        f"POSITION_SCALE = {POSITION_SCALE}",
        f"HELD_MISMATCH_PENALTY = {HELD_MISMATCH_PENALTY}",
        f"HARD_MASK_MISMATCH_PENALTY = {HARD_MASK_MISMATCH_PENALTY}",
        f"HOLDOUT_MAX_DISTANCE_SQ = {holdout_max_distance_sq}",
        f"MAX_FEEDBACK_DISTANCE_SQ = {maximum_feedback_distance_sq}",
        "# local_time -> (x_scaled, y_scaled, held_action, proposal, Hard-4 mask)",
        "SAMPLES = (",
    ]
    for local_time, values in grouped.items():
        encoded = tuple(
            (
                sample.x_quarter,
                sample.y_quarter,
                sample.held_action,
                sample.proposed_action,
                sample.hard_mask,
            )
            for sample in values
        )
        lines.append(f"    ({local_time}, {encoded!r}),")
    lines.extend((")", ""))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path, nargs="+")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--entry-frame",
        type=int,
        action="append",
        help=(
            "retained t61 root corresponding to each artifact; defaults to "
            "6070 for the original single-workload invocation"
        ),
    )
    parser.add_argument("--training-seeds", default="0,1,2,3")
    parser.add_argument("--holdout-seeds", default="16:48")
    parser.add_argument("--emit-python", action="store_true")
    args = parser.parse_args()

    training_seeds = parse_seed_range(args.training_seeds)
    holdout_seeds = parse_seed_range(args.holdout_seeds)
    if not training_seeds or not holdout_seeds:
        raise ValueError("training and holdout delivery sets cannot be empty")
    entry_frames = tuple(args.entry_frame or (6070,))
    if len(entry_frames) != len(args.artifact):
        raise ValueError("provide one --entry-frame for each workload artifact")
    roots = []
    workloads = []
    for artifact, entry_frame in zip(args.artifact, entry_frames, strict=True):
        history = load_failure_history(artifact)
        try:
            root = next(
                snapshot for snapshot in history if snapshot.frame == entry_frame
            )
        except StopIteration as exc:
            raise ValueError(
                f"entry frame {entry_frame} is not retained by {artifact}"
            ) from exc
        boss = _sub12_boss(root)
        if boss.ecl_time != START_LOCAL_TIME:
            raise ValueError("sub12 workload does not begin at residual t61")
        roots.append(root)
        workloads.append((
            hashlib.sha256(artifact.read_bytes()).hexdigest(),
            entry_frame,
        ))

    samples: list[FeedbackSample] = []
    training = tuple(
        (
            root.frame,
            seed,
            run_residual(
                root,
                HistoricalClearDemonstrator(
                    samples,
                    _sub12_time,
                    capture_hard_mask=True,
                ),
                seed,
            ),
        )
        for root in roots
        for seed in training_seeds
    )
    if any(result.outcome != "phase-exit" for _, _, result in training):
        raise RuntimeError("historical controller failed the training residual")
    compiled_samples = tuple(
        sample for sample in samples
        if START_LOCAL_TIME <= sample.local_time < EXIT_LOCAL_TIME
    )

    holdout = []
    distances: list[int] = []
    for root in roots:
        for seed in holdout_seeds:
            policy = TrackingCompiledPolicy(compiled_samples)
            holdout.append((root.frame, seed, run_residual(root, policy, seed)))
            distances.extend(policy.distances)
    if any(result.outcome != "phase-exit" for _, _, result in holdout):
        raise RuntimeError("compiled policy failed a disjoint delivery holdout")
    if not distances:
        raise RuntimeError("holdout produced no feedback-distance evidence")
    holdout_max_distance_sq = max(distances)
    maximum_feedback_distance_sq = 1 << (holdout_max_distance_sq - 1).bit_length()

    if args.emit_python:
        program = load_stage_ecl_program(args.archive, 1)
        print(_python_data(
            compiled_samples,
            workloads=tuple(workloads),
            ecl_sha256=program.sha256,
            training_seeds=training_seeds,
            holdout_max_distance_sq=holdout_max_distance_sq,
            maximum_feedback_distance_sq=maximum_feedback_distance_sq,
        ), end="")
        return 0

    print(json.dumps({
        "entries": tuple({
            "frame": root.frame,
            "subroutine": SUBROUTINE,
            "local_time": _sub12_time(root),
        } for root in roots),
        "training": {
            "delivery_seeds": training_seeds,
            "outcomes": dict(Counter(
                result.outcome for _, _, result in training
            )),
            "worst_clearance": min(
                result.minimum_clearance for _, _, result in training
            ),
            "maximum_commands": max(
                result.commands for _, _, result in training
            ),
        },
        "compiled": {
            "samples": len(compiled_samples),
            "source_clocks": len(samples_by_time(compiled_samples)),
            "holdout_max_distance_sq": holdout_max_distance_sq,
            "maximum_feedback_distance_sq": maximum_feedback_distance_sq,
        },
        "holdout": {
            "delivery_seeds": holdout_seeds,
            "outcomes": dict(Counter(
                result.outcome for _, _, result in holdout
            )),
            "outcomes_by_entry": {
                str(root.frame): dict(Counter(
                    result.outcome
                    for frame, _, result in holdout
                    if frame == root.frame
                ))
                for root in roots
            },
            "minimum_survived_frames": min(
                result.survived_frames for _, _, result in holdout
            ),
            "worst_clearance": min(
                result.minimum_clearance for _, _, result in holdout
            ),
            "maximum_commands": max(
                result.commands for _, _, result in holdout
            ),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
