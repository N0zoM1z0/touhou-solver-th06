#!/usr/bin/env python3
"""Measure planner rungs on one retained physical snapshot."""

from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
import ctypes
from itertools import chain
import json
from pathlib import Path
import statistics
import time

from th06.barrage_lab.corpus import load_failure_history
from th06.hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from th06.hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from th06.hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from th06.hazards.world import forecast_world_births
from th06.kernels.safety import NativeSafetyKernel, _Aabb
from th06.model import CONTROL_ACTIONS, action_from_input


DECISION_BUDGET_MS = 1000.0 / 60.0 * 0.75
TERMINAL_GUARD_MS = 1.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--budget-ms", type=float, default=1000.0)
    parser.add_argument("--pipelines-only", action="store_true")
    return parser.parse_args()


def timed(samples, name, function):
    started = time.perf_counter()
    result = function()
    samples[name].append((time.perf_counter() - started) * 1000.0)
    return result


def profile_components(samples, snapshot, horizon: int = 16) -> None:
    """Time the semantic pieces of one cold mixed Hard/nominal window."""
    bullet_frames = timed(
        samples,
        "component_bullets16",
        lambda: bullet_hazards_by_frame(snapshot, horizon),
    )
    enemy_frames = timed(
        samples,
        "component_enemies16",
        lambda: enemy_hazards_by_frame(snapshot.enemies, horizon),
    )
    hard_births = timed(
        samples,
        "component_hard_births4",
        lambda: forecast_world_births(
            snapshot,
            ((snapshot.x, snapshot.y),) * 4,
        ),
    )
    nominal_births = timed(
        samples,
        "component_nominal_births16",
        lambda: forecast_world_births(
            snapshot,
            ((snapshot.x, snapshot.y),) * horizon,
            rng_mode="nominal",
        ),
    )
    birth_frames = tuple(
        hard_births.hazards[index]
        if index < 4
        else nominal_births.hazards[index]
        for index in range(horizon)
    )
    body_frames = tuple(
        hard_births.body_hazards[index]
        if index < 4
        else nominal_births.body_hazards[index]
        for index in range(horizon)
    )
    aabb_frames = timed(
        samples,
        "component_merge16",
        lambda: tuple(
            bullet_frame + enemy_frame + birth_frame + body_frame
            for bullet_frame, enemy_frame, birth_frame, body_frame in zip(
                bullet_frames,
                enemy_frames,
                birth_frames,
                body_frames,
            )
        ),
    )
    timed(
        samples,
        "component_flatten_aabb16",
        lambda: NativeSafetyKernel._flatten(
            aabb_frames,
            _Aabb,
            lambda value: value,
        ),
    )
    timed(
        samples,
        "component_flatten_stream16",
        lambda: flatten_stream(aabb_frames, _Aabb, lambda value: value),
    )
    timed(
        samples,
        "component_lasers16",
        lambda: laser_hazards_by_frame(snapshot.lasers, horizon),
    )
    # The retained physical CE has no lasers, so their flatten cost is not
    # useful here; a laser-bearing artifact should be profiled separately.


def flatten_stream(frames, value_type, convert):
    """Allocation alternative measured here before touching the hot path."""
    offsets = [0]
    count = 0
    for frame in frames:
        count += len(frame)
        offsets.append(count)
    coordinates = array(
        "f",
        chain.from_iterable(map(convert, chain.from_iterable(frames))),
    )
    offset_array = (ctypes.c_uint32 * len(offsets))(*offsets)
    value_array_type = value_type * max(1, count)
    value_array = (
        value_array_type.from_buffer_copy(coordinates)
        if count
        else value_array_type()
    )
    return offset_array, value_array


def deadline_pipeline(snapshot, variant: str) -> tuple[int, float]:
    """Measure one complete Hard-first online scheduling hypothesis."""
    kernel = NativeSafetyKernel()
    started = time.perf_counter()
    held = action_from_input(snapshot.input_mask)
    hard, _age_zero, _held_safe = (
        kernel.certify_delivery_sets_with_selected(
            snapshot,
            4,
            5,
            (held,),
            collision_margin=0.35,
        )
    )
    if not hard:
        return 4, (time.perf_counter() - started) * 1000.0
    kernel.certify_selected_extended_delivery(
        snapshot,
        4,
        tuple(candidate.action for candidate in hard),
        collision_margin=0.35,
    )

    def remaining() -> float:
        return (
            DECISION_BUDGET_MS
            - (time.perf_counter() - started) * 1000.0
            - TERMINAL_GUARD_MS
        )

    completed = 4
    if variant == "split":
        kernel.prepare(snapshot, 8)
        available = remaining()
        base = (
            kernel.segment_terminal_counts_progressive(
                snapshot, hard, 4, 8, 8, 0.35, available
            )
            if available > 0.0
            else None
        )
        if base is None:
            return completed, (time.perf_counter() - started) * 1000.0
        completed = base[0]
        kernel.prepare(snapshot, 16)
        available = remaining()
        deep = (
            kernel.segment_terminal_counts_progressive(
                snapshot, hard, 4, 12, 16, 0.35, available
            )
            if available > 0.0
            else None
        )
        if deep is not None:
            completed = max(completed, deep[0])
    else:
        maximum = int(variant.removeprefix("unified"))
        kernel.prepare(snapshot, maximum)
        available = remaining()
        result = (
            kernel.segment_terminal_counts_progressive(
                snapshot, hard, 4, 8, maximum, 0.35, available
            )
            if available > 0.0
            else None
        )
        if result is not None:
            completed = result[0]
    return completed, (time.perf_counter() - started) * 1000.0


def main() -> int:
    args = parse_args()
    if args.iterations <= 0 or args.budget_ms <= 0.0:
        raise ValueError("profile dimensions must be positive")
    snapshot = next(
        item for item in load_failure_history(args.artifact)
        if item.frame == args.frame
    )
    samples = defaultdict(list)
    results = defaultdict(list)
    pipeline_variants = ("split", "unified12", "unified16")
    for iteration in range(args.iterations):
        # Rotate ordering so cache warmth and scheduler noise do not always
        # favor one online pipeline.
        offset = iteration % len(pipeline_variants)
        for variant in pipeline_variants[offset:] + pipeline_variants[:offset]:
            completed, elapsed = deadline_pipeline(snapshot, variant)
            results[f"pipeline_{variant}_completed"].append(completed)
            samples[f"pipeline_{variant}"].append(elapsed)
        if args.pipelines_only:
            continue
        profile_components(samples, snapshot)
        reserved_kernel = NativeSafetyKernel()
        held = action_from_input(snapshot.input_mask)
        reserved_authority = timed(
            samples,
            "reserved_hard8",
            lambda: reserved_kernel.certify_delivery_sets_with_selected_reserved(
                snapshot, 4, 5, 8, (held,), 0.35
            ),
        )
        reserved_hard = reserved_authority[0]
        timed(
            samples,
            "reserved_extended4",
            lambda: reserved_kernel.certify_selected_extended_delivery(
                snapshot,
                4,
                tuple(candidate.action for candidate in reserved_hard),
                0.35,
            ),
        )
        timed(
            samples,
            "reserved_boolean8",
            lambda: reserved_kernel.delivery_segment_viability_progressive(
                snapshot,
                reserved_hard,
                4,
                8,
                8,
                0.35,
                args.budget_ms,
            ),
        )
        timed(
            samples,
            "reserved_terminal8",
            lambda: reserved_kernel.segment_terminal_counts_progressive(
                snapshot,
                reserved_hard,
                4,
                8,
                8,
                0.35,
                args.budget_ms,
            ),
        )
        kernel = NativeSafetyKernel()
        hard = timed(samples, "hard4", lambda: kernel.certify_selected(
            snapshot,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        ))
        timed(samples, "prepare8", lambda: kernel.prepare(snapshot, 8))
        replanning_viability = timed(
            samples,
            "replanning_viability8",
            lambda: kernel.replanning_viability_budgeted(
                snapshot, hard, 4, 8, 0.35, args.budget_ms
            ),
        )
        replanning_scores = timed(
            samples,
            "replanning_scores8",
            lambda: kernel.replanning_scores_progressive_budgeted(
                snapshot, hard, 4, 8, 0.35, args.budget_ms
            ),
        )
        boolean8 = timed(
            samples,
            "boolean8",
            lambda: kernel.delivery_segment_viability_progressive(
                snapshot, hard, 4, 8, 8, 0.35, args.budget_ms
            ),
        )
        base = timed(
            samples,
            "progressive8",
            lambda: kernel.segment_terminal_counts_progressive(
                snapshot, hard, 4, 8, 8, 0.35, args.budget_ms
            ),
        )
        timed(samples, "extend16", lambda: kernel.prepare(snapshot, 16))
        deep = timed(
            samples,
            "progressive12_16",
            lambda: kernel.segment_terminal_counts_progressive(
                snapshot, hard, 4, 12, 16, 0.35, args.budget_ms
            ),
        )

        combined_kernel = NativeSafetyKernel()
        combined_hard = timed(
            samples,
            "combined_hard4",
            lambda: combined_kernel.certify_selected(
                snapshot,
                4,
                CONTROL_ACTIONS,
                collision_margin=0.35,
            ),
        )
        timed(
            samples,
            "combined_extend16",
            lambda: combined_kernel.prepare(snapshot, 16),
        )
        combined = timed(
            samples,
            "progressive8_16",
            lambda: combined_kernel.segment_terminal_counts_progressive(
                snapshot,
                combined_hard,
                4,
                8,
                16,
                0.35,
                args.budget_ms,
            ),
        )
        results["base_completed"].append(base[0])
        results["deep_completed"].append(deep[0])
        results["combined_completed"].append(combined[0])

        prefetch_kernel = NativeSafetyKernel()
        prefetch_prepared = timed(
            samples,
            "prefetch_prepare16",
            lambda: prefetch_kernel._prepare_window(
                snapshot,
                0,
                16,
                fail_closed_horizon=5,
            ),
        )
        prefetch_kernel._prepared_snapshot = snapshot
        prefetch_kernel._prepared_horizon = 16
        prefetch_kernel._prepared_hazards = prefetch_prepared
        prefetch_hard = timed(
            samples,
            "prefetch_hard4",
            lambda: prefetch_kernel._certify_prepared(
                snapshot,
                4,
                0.35,
                prefetch_prepared,
            )[0],
        )
        prefetch = timed(
            samples,
            "prefetch_progressive8_16",
            lambda: prefetch_kernel.segment_terminal_counts_progressive(
                snapshot,
                prefetch_hard,
                4,
                8,
                16,
                0.35,
                args.budget_ms,
            ),
        )
        results["prefetch_completed"].append(prefetch[0])
        prefetch_flexible = timed(
            samples,
            "prefetch_flexible8_16",
            lambda: prefetch_kernel.flexible_terminal_counts_progressive(
                snapshot,
                prefetch_hard,
                4,
                8,
                16,
                0.35,
                args.budget_ms,
            ),
        )
        prefetch_boolean = timed(
            samples,
            "prefetch_boolean8_16",
            lambda: prefetch_kernel.boolean_reachability_progressive(
                snapshot,
                prefetch_hard,
                4,
                8,
                16,
                0.35,
                args.budget_ms,
            ),
        )
        results["prefetch_flexible_completed"].append(prefetch_flexible[0])
        results["prefetch_boolean_completed"].append(prefetch_boolean[0])

        combined12_kernel = NativeSafetyKernel()
        combined12_hard = timed(
            samples,
            "combined12_hard4",
            lambda: combined12_kernel.certify_selected(
                snapshot,
                4,
                CONTROL_ACTIONS,
                collision_margin=0.35,
            ),
        )
        timed(
            samples,
            "combined_extend12",
            lambda: combined12_kernel.prepare(snapshot, 12),
        )
        combined12 = timed(
            samples,
            "progressive8_12",
            lambda: combined12_kernel.segment_terminal_counts_progressive(
                snapshot,
                combined12_hard,
                4,
                8,
                12,
                0.35,
                args.budget_ms,
            ),
        )
        results["combined12_completed"].append(combined12[0])

    if args.pipelines_only:
        print(json.dumps({
            "artifact": str(args.artifact),
            "frame": args.frame,
            "iterations": args.iterations,
            "median_ms": {
                name: statistics.median(values)
                for name, values in samples.items()
            },
            "p90_ms": {
                name: sorted(values)[
                    max(0, int(len(values) * 0.9) - 1)
                ]
                for name, values in samples.items()
            },
            "completed_horizons": {
                name: {
                    str(horizon): values.count(horizon)
                    for horizon in sorted(set(values))
                }
                for name, values in results.items()
            },
        }, indent=2))
        return 0

    output = {
        "artifact": str(args.artifact),
        "frame": args.frame,
        "iterations": args.iterations,
        "hard_actions": len(hard),
        "median_ms": {
            name: statistics.median(values)
            for name, values in samples.items()
        },
        "p90_ms": {
            name: sorted(values)[max(0, int(len(values) * 0.9) - 1)]
            for name, values in samples.items()
        },
        "completed_horizons": {
            name: sorted(set(values)) for name, values in results.items()
        },
        "preferred": {
            "replanning_viable_h8": [
                action.name for action, score in replanning_viability.items()
                if score > 0
            ],
            "replanning_robust_h8": [
                action.name for action, score in replanning_scores[0].items()
                if score == max(replanning_scores[0].values())
            ],
            "boolean_h8": [
                action.name for action, score in boolean8[1].items()
                if score > 0
            ],
            "h8": [
                action.name for action, score in base[1].items()
                if score == max(base[1].values())
            ],
            "h12": [
                action.name for action, score in combined12[1].items()
                if score == max(combined12[1].values())
            ],
            "h16": [
                action.name for action, score in combined[1].items()
                if score == max(combined[1].values())
            ],
            "flexible_h16": [
                action.name for action, score in prefetch_flexible[1].items()
                if score == max(prefetch_flexible[1].values())
            ],
            "boolean_h16": [
                action.name for action, score in prefetch_boolean[1].items()
                if score > 0
            ],
        },
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
