#!/usr/bin/env python3
"""Run the source-derived barrage correctness gate."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from th06.barrage_lab.assets import load_ecl_bullet_catalogue
from th06.barrage_lab.generator import (
    eligible_opcodes,
    runtime_barrage_template,
)
from th06.barrage_lab.runner import (
    native_action_names,
    native_progressive_terminal_guidance,
    native_progressive_terminal_counts,
    native_terminal_counts,
    python_terminal_guidance,
    run_planner_sweep,
    run_sweep,
    source_terminal_guidance,
)
from th06.barrage_lab.temporal import run_proposal_temporal_sweep


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="path to the installed TH06 ST.DAT")
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument(
        "--corpus", type=Path,
        help="condition generated cases on an online failure artifact",
    )
    parser.add_argument(
        "--corpus-density-scale", type=float, default=1.0,
        help="multiply each sampled runtime frame's observed bullet count",
    )
    parser.add_argument(
        "--temporal-seeds", type=int, default=0,
        help="also fuzz proposal publication/expiry sequences",
    )
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument(
        "--planner", action="store_true",
        help="differentially fuzz terminal-state planning instead of Hard certification",
    )
    parser.add_argument("--segment-length", type=int, default=4)
    parser.add_argument(
        "--guidance", action="store_true",
        help="with --planner, fuzz exact free-endpoint guidance reuse",
    )
    parser.add_argument(
        "--placement",
        choices=("interior", "edge", "corner", "mixed"),
        default="interior",
        help="source movement-area player placement distribution",
    )
    parser.add_argument(
        "--native", action="store_true",
        help="also compare build/th06_safety.dll (Windows Python only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seeds <= 0 or not 1 <= args.horizon <= 64:
        raise ValueError("seeds must be positive and horizon must be in 1..64")
    if args.planner and not 0 < args.segment_length <= args.horizon:
        raise ValueError("planner segment length must be inside the horizon")
    if args.guidance and not args.planner:
        raise ValueError("--guidance requires --planner")
    if args.corpus_density_scale <= 0.0 or args.temporal_seeds < 0:
        raise ValueError(
            "corpus scale must be positive and temporal seeds nonnegative"
        )
    runtime_templates = ()
    if args.corpus is not None:
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        history = corpus.get("snapshot_history") or (corpus["snapshot"],)
        runtime_templates = tuple(
            runtime_barrage_template(raw, args.corpus_density_scale)
            for raw in history
        )
    catalogue = load_ecl_bullet_catalogue(args.archive)
    kernel = None
    if args.native:
        if os.name != "nt":
            raise RuntimeError("--native requires Windows Python")
        from th06.kernels.safety import NativeSafetyKernel
        kernel = NativeSafetyKernel()
    if args.planner:
        if args.guidance:
            base_planners = (
                ("python-guidance", python_terminal_guidance),
            )
            extras = (
                ((
                    "native-progressive-guidance",
                    native_progressive_terminal_guidance(kernel),
                ),)
                if kernel is not None else ()
            )
            oracle_planner = source_terminal_guidance
        else:
            base_planners = None
            extras = (
                (
                    ("native-fixed", native_terminal_counts(kernel)),
                    (
                        "native-progressive",
                        native_progressive_terminal_counts(kernel),
                    ),
                )
                if kernel is not None else ()
            )
            oracle_planner = None
        summary, mismatch = run_planner_sweep(
            catalogue,
            seeds=args.seeds,
            segment_length=args.segment_length,
            horizon=args.horizon,
            placement=args.placement,
            oracle_planner=oracle_planner,
            **(
                {"base_planners": base_planners}
                if base_planners is not None else {}
            ),
            extra_planners=extras,
            one_candidate=args.guidance,
            runtime_templates=runtime_templates,
        )
    else:
        extras = (
            (("native", native_action_names(kernel)),)
            if kernel is not None else ()
        )
        summary, mismatch = run_sweep(
            catalogue, seeds=args.seeds, horizon=args.horizon,
            placement=args.placement,
            extra_certifiers=extras,
            runtime_templates=runtime_templates,
        )
    temporal_summary = None
    temporal_mismatch = None
    if args.temporal_seeds:
        temporal_summary, temporal_mismatch = run_proposal_temporal_sweep(
            args.temporal_seeds
        )
    output = {
        "archive": str(args.archive),
        "mode": (
            "planner-guidance"
            if args.guidance else
            "planner" if args.planner else
            "hard-certification"
        ),
        "placement": args.placement,
        "catalogue_opcodes": len(catalogue),
        "exact_hard_opcodes": len(eligible_opcodes(catalogue)),
        "runtime_templates": len(runtime_templates),
        "summary": asdict(summary),
        "temporal_summary": (
            asdict(temporal_summary) if temporal_summary is not None else None
        ),
        "temporal_mismatch": (
            asdict(temporal_mismatch) if temporal_mismatch is not None else None
        ),
        "mismatch": None,
    }
    if mismatch is not None:
        mismatch_output = {
            "seed": mismatch.seed,
            "implementation": mismatch.implementation,
            "reduced_horizon": mismatch.horizon,
            "differing_actions": mismatch.differing_actions,
            "expected": mismatch.expected,
            "actual": mismatch.actual,
            "reduced_bullets": len(mismatch.snapshot.bullets),
            "player": {
                "x": mismatch.snapshot.x,
                "y": mismatch.snapshot.y,
                "half_width": mismatch.snapshot.half_width,
                "half_height": mismatch.snapshot.half_height,
                "input_mask": mismatch.snapshot.input_mask,
            },
            "bullets": [
                asdict(bullet) for bullet in mismatch.snapshot.bullets
            ],
            "ecl_sources": mismatch.sources,
        }
        if args.planner:
            mismatch_output["segment_length"] = mismatch.segment_length
            mismatch_output["candidate_actions"] = mismatch.candidate_names
        output["mismatch"] = mismatch_output
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return int(mismatch is not None or temporal_mismatch is not None)


if __name__ == "__main__":
    raise SystemExit(main())
