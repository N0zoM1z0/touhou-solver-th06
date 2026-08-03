#!/usr/bin/env python3
"""Inspect exact native continuation frontiers on retained physical frames."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time

from th06.barrage_lab.corpus import load_failure_history
from th06.kernels.safety import NativeSafetyKernel
from th06.model import CONTROL_ACTIONS, action_from_input


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--frames",
        required=True,
        help="comma-separated physical game frames",
    )
    parser.add_argument("--horizons", default="8,12,16")
    parser.add_argument("--budget-ms", type=float, default=1000.0)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--trace-csv",
        type=Path,
        help="optional online trace used to align the published action",
    )
    return parser.parse_args()


def names(values) -> list[str]:
    return [value.action.name for value in values]


def preferred(scores) -> list[str]:
    best = max(scores.values(), default=0)
    return [
        action.name for action, score in scores.items()
        if score == best and best > 0
    ]


def best_score(scores) -> int:
    return max(scores.values(), default=0)


def main() -> int:
    args = parse_args()
    requested_frames = tuple(int(value) for value in args.frames.split(","))
    horizons = tuple(int(value) for value in args.horizons.split(","))
    if (
        not requested_frames
        or not horizons
        or tuple(sorted(set(horizons))) != horizons
        or horizons[0] < 4
        or args.budget_ms <= 0.0
    ):
        raise ValueError("invalid physical frontier dimensions")
    by_frame = {
        snapshot.frame: snapshot
        for snapshot in load_failure_history(args.artifact)
        if snapshot.frame in requested_frames
    }
    missing = set(requested_frames) - set(by_frame)
    if missing:
        raise ValueError(f"frames missing from artifact: {sorted(missing)}")
    online_by_frame = {}
    if args.trace_csv is not None:
        with args.trace_csv.open(newline="", encoding="utf-8") as source:
            online_by_frame = {
                int(row["frame"]): row for row in csv.DictReader(source)
                if int(row["frame"]) in requested_frames
            }

    output = []
    for frame in requested_frames:
        snapshot = by_frame[frame]
        kernel = NativeSafetyKernel()
        started = time.perf_counter()
        hard = kernel.certify_selected(
            snapshot,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )
        hard_actions = tuple(value.action for value in hard)
        values = {
            "frame": frame,
            "player": [snapshot.x, snapshot.y],
            "bullets": len(snapshot.bullets),
            "held": action_from_input(snapshot.input_mask).name,
            "hard": len(hard) if args.compact else names(hard),
            "constant": {},
            "segment": {},
            "boolean": {},
        }
        online = online_by_frame.get(frame)
        if online is not None:
            values["online"] = {
                "action": online["action"],
                "effort_horizon": int(online["effort_horizon"] or 0),
                "effort_safe": int(online["effort_safe"] or 0),
                "decision_age": (
                    int(online["decision_age"])
                    if online["decision_age"] else None
                ),
                "attack_x": (
                    float(online["attack_x"])
                    if online["attack_x"] else None
                ),
                "clearance": float(online["clearance"]),
                "solve_ms": float(online["solve_ms"]),
                "reason": online["reason"],
            }
        if not args.compact:
            values["hard_detail"] = {
                value.action.name: {
                    "clearance": value.clearance,
                    "final": [value.final_x, value.final_y],
                }
                for value in hard
            }
        if not hard:
            values["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
            output.append(values)
            continue
        for horizon in horizons:
            constant = kernel.certify_selected(
                snapshot,
                horizon,
                hard_actions,
                collision_margin=0.35,
            )
            segment = kernel.terminal_counts(
                snapshot,
                hard,
                4,
                horizon,
                collision_margin=0.35,
            )
            try:
                boolean = kernel.boolean_reachability_progressive(
                    snapshot,
                    hard,
                    4,
                    min(8, horizon),
                    horizon,
                    collision_margin=0.35,
                    budget_ms=args.budget_ms,
                )
            except RuntimeError as error:
                raise RuntimeError(
                    f"frame {frame} horizon {horizon}: {error}"
                ) from error
            values["constant"][str(horizon)] = names(constant)
            values["segment"][str(horizon)] = {
                "preferred": preferred(segment),
                "best": best_score(segment),
                **(
                    {}
                    if args.compact
                    else {
                        "scores": {
                            action.name: score
                            for action, score in segment.items()
                        }
                    }
                ),
            }
            if boolean is None:
                values["boolean"][str(horizon)] = None
            elif args.compact:
                winning = frozenset(
                    action for action, score in boolean[1].items()
                    if score > 0
                )
                values["boolean"][str(horizon)] = {
                    "completed": boolean[0],
                    "excluded": [
                        action.name for action in hard_actions
                        if action not in winning
                    ],
                }
            else:
                values["boolean"][str(horizon)] = {
                    "completed": boolean[0],
                    "reached": boolean[2],
                    "winning": [
                        action.name for action, score in boolean[1].items()
                        if score > 0
                    ],
                }
        if kernel._prepared_horizon >= horizons[-1]:
            bullet_offsets, _bullets, laser_offsets, _lasers = (
                kernel._prepared_hazards
            )
            values["prepared"] = {
                "aabbs": int(bullet_offsets[horizons[-1]]),
                "lasers": int(laser_offsets[horizons[-1]]),
            }
        values["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        output.append(values)
    if args.compact:
        for values in output:
            print(json.dumps(values, separators=(",", ":")))
    else:
        print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
