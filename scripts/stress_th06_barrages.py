#!/usr/bin/env python3
"""Run the source-derived barrage correctness gate."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from th06.barrage_lab.assets import load_ecl_bullet_catalogue
from th06.barrage_lab.generator import eligible_opcodes
from th06.barrage_lab.runner import native_action_names, run_sweep


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="path to the installed TH06 ST.DAT")
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument(
        "--native", action="store_true",
        help="also compare build/th06_safety.dll (Windows Python only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seeds <= 0 or not 1 <= args.horizon <= 64:
        raise ValueError("seeds must be positive and horizon must be in 1..64")
    catalogue = load_ecl_bullet_catalogue(args.archive)
    extras = ()
    if args.native:
        if os.name != "nt":
            raise RuntimeError("--native requires Windows Python")
        from th06.kernels.safety import NativeSafetyKernel
        extras = (("native", native_action_names(NativeSafetyKernel())),)
    summary, mismatch = run_sweep(
        catalogue, seeds=args.seeds, horizon=args.horizon,
        extra_certifiers=extras,
    )
    output = {
        "archive": str(args.archive),
        "catalogue_opcodes": len(catalogue),
        "exact_hard_opcodes": len(eligible_opcodes(catalogue)),
        "summary": asdict(summary),
        "mismatch": None,
    }
    if mismatch is not None:
        output["mismatch"] = {
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
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return int(mismatch is not None)


if __name__ == "__main__":
    raise SystemExit(main())
