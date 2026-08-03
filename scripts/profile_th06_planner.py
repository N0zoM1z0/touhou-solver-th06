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
from th06.model import CONTROL_ACTIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--budget-ms", type=float, default=1000.0)
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
    for _ in range(args.iterations):
        profile_components(samples, snapshot)
        kernel = NativeSafetyKernel()
        hard = timed(samples, "hard4", lambda: kernel.certify_selected(
            snapshot,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        ))
        timed(samples, "prepare8", lambda: kernel.prepare(snapshot, 8))
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
