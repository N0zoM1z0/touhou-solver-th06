#!/usr/bin/env python3
"""Print source timeline sections for route-pack authoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from th06.barrage_lab.assets import load_stage_timeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="installed th06_ST.DAT")
    parser.add_argument("--stage", type=int, choices=range(1, 8), required=True)
    parser.add_argument(
        "--section-gap",
        type=int,
        default=150,
        help="start a new spawn section after this many source timeline ticks",
    )
    return parser.parse_args()


def spawn_record(instruction):
    if not 0 <= instruction.opcode <= 7:
        return None
    if instruction.size < 28:
        raise ValueError("source spawn record is shorter than EclTimelineInstr")
    x, y, z, item, score, life = struct.unpack_from(
        "<fffHHi", instruction.raw, 8
    )
    return {
        "time": instruction.time,
        "opcode": instruction.opcode,
        "sub": instruction.arg0,
        "x": x,
        "y": y,
        "z": z,
        "item": item,
        "score": score,
        "life": life,
    }


def main() -> int:
    args = parse_args()
    if args.section_gap <= 0:
        raise ValueError("section gap must be positive")
    timeline = load_stage_timeline(args.archive, args.stage)
    spawns = tuple(
        record
        for instruction in timeline
        if (record := spawn_record(instruction)) is not None
    )
    sections = []
    for spawn in spawns:
        if (
            not sections
            or spawn["time"] - sections[-1]["last_time"] >= args.section_gap
        ):
            sections.append({
                "start": spawn["time"],
                "last_time": spawn["time"],
                "subroutines": [],
                "spawns": [],
            })
        section = sections[-1]
        section["last_time"] = spawn["time"]
        if spawn["sub"] not in section["subroutines"]:
            section["subroutines"].append(spawn["sub"])
        section["spawns"].append(spawn)
    controls = [
        {
            "time": instruction.time,
            "opcode": instruction.opcode,
            "arg0": instruction.arg0,
        }
        for instruction in timeline
        if instruction.opcode >= 8
    ]
    print(json.dumps({
        "stage": args.stage,
        "source": f"ecldata{args.stage}.ecl",
        "instruction_count": len(timeline),
        "sections": sections,
        "control_events": controls,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
