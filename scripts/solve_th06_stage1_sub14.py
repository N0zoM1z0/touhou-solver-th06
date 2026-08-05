#!/usr/bin/env python3
"""Compile and hold out a Stage 1/sub14 feedback tube.

The expensive demonstrator is the small controller that physically cleared
Stage 1 at ``b5fecb9``, but every one of its actions is re-certified by the
current source/Hard model.  Multiple command-delivery branches are rolled out
through the complete source phase.  Their state/action samples are quantized
and distilled into a nearest-tube feedback policy whose online cost is a few
integer distance comparisons, not an h16 search.

This is deliberately phase-specific.  It is offline tooling and has no action
authority in the online runtime.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from th06.barrage_lab.assets import load_stage_ecl_program
from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.stateful import run_closed_loop
from th06.model import ACTIONS, CONTROL_ACTIONS, Action, Snapshot, action_from_input
from th06.ranking import ProposalRanker
from th06.routes.phase import ecl_subroutine_index
from th06.safety import (
    MOVEMENT_BOTTOM,
    MOVEMENT_LEFT,
    MOVEMENT_RIGHT,
    MOVEMENT_TOP,
    certify_actions,
)
from th06.viability import replanning_scores


POSITION_SCALE = 4
HELD_MISMATCH_PENALTY = 16 * POSITION_SCALE * POSITION_SCALE
SUBROUTINE = 14
EXIT_LOCAL_TIME = 200


def _boundary_room(x: float, y: float) -> float:
    return min(
        x - MOVEMENT_LEFT,
        MOVEMENT_RIGHT - x,
        y - MOVEMENT_TOP,
        MOVEMENT_BOTTOM - y,
    )


@dataclass(frozen=True)
class FeedbackSample:
    local_time: int
    x_quarter: int
    y_quarter: int
    held_action: int
    proposed_action: int


class LegacyDemonstrationPolicy:
    """The b5 route heuristic, evaluated only offline under current Hard."""

    def __init__(self, samples: list[FeedbackSample]) -> None:
        self.samples = samples
        self.repair_action: Action | None = None
        self.repair_until_frame: int | None = None

    def __call__(self, snapshot: Snapshot) -> Action | None:
        hard = certify_actions(snapshot, 4, actions=ACTIONS)
        if not hard:
            return None
        durable = certify_actions(
            snapshot,
            16,
            actions=tuple(candidate.action for candidate in hard),
        )
        durable_actions = frozenset(candidate.action for candidate in durable)
        repairable_actions: frozenset[Action] = frozenset()
        if not durable_actions:
            scores = replanning_scores(snapshot, hard, 4, 8)
            best = max(scores.values(), default=0)
            if best:
                repairable_actions = frozenset(
                    action for action, score in scores.items() if score == best
                )

        current = action_from_input(snapshot.input_mask)
        candidate_actions = frozenset(candidate.action for candidate in hard)
        continued_repair = (
            self.repair_action
            if self.repair_action in candidate_actions
            and self.repair_until_frame is not None
            and snapshot.frame < self.repair_until_frame
            else None
        )
        current_room = _boundary_room(snapshot.x, snapshot.y)

        def score(candidate) -> tuple:
            useful_position = -0.04 * math.hypot(
                candidate.final_x - 192.0,
                candidate.final_y - 380.0,
            )
            continuity = 0.15 if candidate.action == current else 0.0
            return (
                candidate.action in durable_actions,
                candidate.action == continued_repair,
                candidate.action in repairable_actions,
                _boundary_room(candidate.final_x, candidate.final_y)
                > current_room + 0.25,
                min(80.0, candidate.clearance) + useful_position + continuity,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(hard, key=score)
        selective_repair = (
            repairable_actions
            and len(repairable_actions) < len(candidate_actions)
            and chosen.action in repairable_actions
        )
        if selective_repair and continued_repair != chosen.action:
            self.repair_action = chosen.action
            self.repair_until_frame = snapshot.frame + 4
        elif continued_repair is not None and chosen.action != continued_repair:
            self.repair_action = None
            self.repair_until_frame = None

        boss = _sub14_boss(snapshot)
        self.samples.append(FeedbackSample(
            boss.ecl_time,
            round(snapshot.x * POSITION_SCALE),
            round(snapshot.y * POSITION_SCALE),
            CONTROL_ACTIONS.index(current),
            ACTIONS.index(chosen.action),
        ))
        return chosen.action


def _sub14_boss(snapshot: Snapshot):
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    if len(bosses) != 1 or ecl_subroutine_index(bosses[0]) != SUBROUTINE:
        raise ValueError("workload root is not the unique Stage 1 sub14 boss")
    return bosses[0]


def _left_sub14(snapshot: Snapshot) -> bool:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    return len(bosses) != 1 or ecl_subroutine_index(bosses[0]) != SUBROUTINE


def run_sub14(snapshot: Snapshot, policy, delivery_seed: int):
    """Run until a stable source transition, not an arbitrary frame count."""
    boss = _sub14_boss(snapshot)
    return run_closed_loop(
        snapshot,
        policy,
        frames=EXIT_LOCAL_TIME - boss.ecl_time + 2,
        delivery_seed=delivery_seed,
        battle_world=True,
        stop_when=_left_sub14,
        stop_outcome="phase-exit",
    )


def samples_by_time(
    samples: tuple[FeedbackSample, ...],
) -> dict[int, tuple[FeedbackSample, ...]]:
    grouped: dict[int, list[FeedbackSample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.local_time].append(sample)
    return {
        local_time: tuple(values)
        for local_time, values in sorted(grouped.items())
    }


class CompiledFeedbackPolicy:
    """Reference implementation of the constant-time online policy."""

    def __init__(self, samples: tuple[FeedbackSample, ...]) -> None:
        self.samples = samples_by_time(samples)
        self.ranker = ProposalRanker()

    def __call__(self, snapshot: Snapshot) -> Action | None:
        boss = _sub14_boss(snapshot)
        hard = certify_actions(snapshot, 4, actions=CONTROL_ACTIONS)
        if not hard:
            return None
        current = action_from_input(snapshot.input_mask)
        x_quarter = round(snapshot.x * POSITION_SCALE)
        y_quarter = round(snapshot.y * POSITION_SCALE)
        allowed = frozenset(candidate.action for candidate in hard)
        nearest_by_action: dict[Action, int] = {}
        for sample in self.samples.get(boss.ecl_time, ()):
            proposed = ACTIONS[sample.proposed_action]
            if proposed not in allowed:
                continue
            distance = (
                (sample.x_quarter - x_quarter) ** 2
                + (sample.y_quarter - y_quarter) ** 2
                + (
                    0
                    if CONTROL_ACTIONS[sample.held_action] == current
                    else HELD_MISMATCH_PENALTY
                )
            )
            nearest_by_action[proposed] = min(
                distance,
                nearest_by_action.get(proposed, distance),
            )
        selected = (
            min(nearest_by_action, key=lambda action: (
                nearest_by_action[action], action.name
            ))
            if nearest_by_action
            else None
        )
        preferred = frozenset((selected,)) if selected is not None else frozenset()
        return self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=1,
        ).action


def _seed_range(value: str) -> tuple[int, ...]:
    if ":" in value:
        start, stop = (int(part) for part in value.split(":", 1))
        return tuple(range(start, stop))
    return tuple(int(part) for part in value.split(",") if part)


def _python_data(
    samples: tuple[FeedbackSample, ...],
    *,
    artifact_sha256: str,
    ecl_sha256: str,
    training_seeds: tuple[int, ...],
) -> str:
    grouped = samples_by_time(samples)
    lines = [
        '"""Generated Stage 1/sub14 feedback-tube policy data."""',
        "",
        "# Regenerate with ``scripts/solve_th06_stage1_sub14.py --emit-python``.  The",
        "# checked-in asset contains only semantic source clocks and quarter-pixel",
        "# feedback state; physical frame and delivery-seed identities are provenance,",
        "# never runtime branch keys.  Delivery seeds 16..47 are a disjoint holdout.",
        "",
        "POLICY_SCHEMA = 1",
        f'ARTIFACT_SHA256 = "{artifact_sha256}"',
        f'ECL_SHA256 = "{ecl_sha256}"',
        f"TRAINING_DELIVERY_SEEDS = {training_seeds!r}",
        f"POSITION_SCALE = {POSITION_SCALE}",
        f"HELD_MISMATCH_PENALTY = {HELD_MISMATCH_PENALTY}",
        "# local_time -> (x_quarter, y_quarter, held_action, proposal)",
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
    parser.add_argument("--entry-frame", type=int, default=6162)
    parser.add_argument("--training-seeds", default="0,1,2,3")
    parser.add_argument("--holdout-seeds", default="16:48")
    parser.add_argument("--emit-python", action="store_true")
    args = parser.parse_args()

    training_seeds = _seed_range(args.training_seeds)
    holdout_seeds = _seed_range(args.holdout_seeds)
    if not training_seeds or (not holdout_seeds and not args.emit_python):
        raise ValueError("training and holdout delivery sets cannot be empty")
    history = load_failure_history(args.artifact)
    try:
        root = next(snapshot for snapshot in history if snapshot.frame == args.entry_frame)
    except StopIteration as exc:
        raise ValueError(f"entry frame {args.entry_frame} is not retained") from exc
    boss = _sub14_boss(root)
    if not 0 < boss.ecl_time < EXIT_LOCAL_TIME:
        raise ValueError("sub14 entry clock is outside the authored phase")
    phase_frames = EXIT_LOCAL_TIME - boss.ecl_time

    samples: list[FeedbackSample] = []
    training = []
    for seed in training_seeds:
        result = run_sub14(root, LegacyDemonstrationPolicy(samples), seed)
        training.append(result)
    if any(result.outcome != "phase-exit" for result in training):
        raise RuntimeError("legacy seed failed the complete training phase")

    # The online route gives the source t200 dispatch its own one-update
    # policy state.  Compile only the attack/residual tube through t199 so the
    # offline asset cannot leak a demonstration commitment across that phase
    # boundary.
    compiled_samples = tuple(
        sample for sample in samples if sample.local_time < EXIT_LOCAL_TIME
    )
    if args.emit_python:
        program = load_stage_ecl_program(args.archive, 1)
        print(_python_data(
            compiled_samples,
            artifact_sha256=hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
            ecl_sha256=program.sha256,
            training_seeds=training_seeds,
        ), end="")
        return 0

    holdout = tuple(
        run_sub14(root, CompiledFeedbackPolicy(compiled_samples), seed)
        for seed in holdout_seeds
    )

    print(json.dumps({
        "entry": {
            "frame": root.frame,
            "subroutine": SUBROUTINE,
            "local_time": boss.ecl_time,
            "phase_frames": phase_frames,
        },
        "training": {
            "delivery_seeds": training_seeds,
            "outcomes": dict(Counter(result.outcome for result in training)),
            "worst_clearance": min(result.minimum_clearance for result in training),
            "maximum_commands": max(result.commands for result in training),
        },
        "compiled": {
            "samples": len(compiled_samples),
            "source_clocks": len(samples_by_time(compiled_samples)),
        },
        "holdout": {
            "delivery_seeds": holdout_seeds,
            "outcomes": dict(Counter(result.outcome for result in holdout)),
            "minimum_survived_frames": min(
                result.survived_frames for result in holdout
            ),
            "worst_clearance": min(result.minimum_clearance for result in holdout),
            "maximum_commands": max(result.commands for result in holdout),
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
