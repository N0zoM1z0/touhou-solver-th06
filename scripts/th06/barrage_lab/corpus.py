"""Decode runtime snapshots for offline barrage-lab replay."""

from __future__ import annotations

import json
from pathlib import Path

from ..model import (
    Bullet,
    BulletPattern,
    EnemyBody,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
    Laser,
    Snapshot,
    StageTimelineInstruction,
)


def decode_snapshot(raw: dict) -> Snapshot:
    """Restore the immutable runtime model written by ``agent.py``."""
    values = dict(raw)
    values["bullets"] = tuple(Bullet(**item) for item in values["bullets"])
    values["despawning_bullets"] = tuple(
        Bullet(**item) for item in values["despawning_bullets"]
    )
    values["lasers"] = tuple(Laser(**item) for item in values["lasers"])
    values["enemies"] = tuple(
        EnemyBody(**item) for item in values["enemies"]
    )
    values["spawners"] = tuple(
        EnemySpawner(
            **{
                **item,
                "ecl_compare": item.get("ecl_compare", 0),
                "ecl_stack": tuple(
                    EnemyEclContext(**context)
                    for context in item.get("ecl_stack", ())
                ),
                "pattern": (
                    BulletPattern(**item["pattern"])
                    if item.get("pattern") is not None
                    else None
                ),
                "next_instruction": (
                    EclInstruction(**item["next_instruction"])
                    if item.get("next_instruction") is not None
                    else None
                ),
                "ecl_program": tuple(
                    EclInstruction(**instruction)
                    for instruction in item.get("ecl_program", ())
                ),
            }
        )
        for item in values.get("spawners", ())
    )
    values["timeline_instructions"] = tuple(
        StageTimelineInstruction(**item)
        for item in values.get("timeline_instructions", ())
    )
    return Snapshot(**values)


def load_failure_history(path: Path) -> tuple[Snapshot, ...]:
    """Load the ordered physical snapshots retained in one failure artifact."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    raw_history = artifact.get("snapshot_history") or (artifact["snapshot"],)
    history = tuple(decode_snapshot(raw) for raw in raw_history)
    if any(right.frame <= left.frame for left, right in zip(history, history[1:])):
        raise ValueError("runtime snapshot history must have increasing frames")
    return history
