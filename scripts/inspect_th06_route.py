#!/usr/bin/env python3
"""Print installed timeline and source-relative ECL route evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from th06.barrage_lab.assets import load_stage_ecl_program, load_stage_timeline


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
    parser.add_argument(
        "--subroutine",
        type=int,
        action="append",
        default=[],
        help="include this full source-relative ECL subroutine (repeatable)",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        choices=range(5),
        default=2,
        help="mark instructions executable on this source difficulty",
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
    program = load_stage_ecl_program(args.archive, args.stage)
    if any(
        not 0 <= subroutine < len(program.subroutine_offsets)
        for subroutine in args.subroutine
    ):
        raise ValueError("requested ECL subroutine is outside the installed table")
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
    selected_subroutines = []
    for subroutine in dict.fromkeys(args.subroutine):
        instructions = program.subroutine(subroutine)
        edges_by_source = {}
        for edge in program.edges:
            if edge.source_subroutine != subroutine:
                continue
            edges_by_source.setdefault(edge.source_relative_offset, []).append({
                "kind": edge.kind,
                "target_subroutine": edge.target_subroutine,
                "target_relative_offset": edge.target_relative_offset,
            })
        selected_subroutines.append({
            "subroutine": subroutine,
            "source_offset": program.subroutine_offsets[subroutine],
            "instructions": [
                {
                    "source_id": instruction.source_id,
                    "relative_offset": instruction.relative_offset,
                    "time": instruction.time,
                    "opcode": instruction.opcode,
                    "size": instruction.size,
                    "difficulty_mask": instruction.difficulty_mask,
                    "executes_on_selected_difficulty": instruction.executes_on(
                        args.difficulty
                    ),
                    "edges": edges_by_source.get(
                        instruction.relative_offset, []
                    ),
                }
                for instruction in instructions
            ],
        })
    print(json.dumps({
        "stage": args.stage,
        "source": f"ecldata{args.stage}.ecl",
        "timeline_instruction_count": len(timeline),
        "sections": sections,
        "control_events": controls,
        "ecl": {
            "sha256": program.sha256,
            "subroutine_count": len(program.subroutine_offsets),
            "instruction_count": len(program.instructions),
            "edge_count": len(program.edges),
            "selected_difficulty": args.difficulty,
            "selected_subroutines": selected_subroutines,
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
