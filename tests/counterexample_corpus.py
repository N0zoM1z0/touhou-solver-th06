"""Load compact, physically observed solver counterexamples."""

from __future__ import annotations

import json
from pathlib import Path

from th06.model import (
    CONTROL_ACTIONS,
    Bullet,
    BulletPattern,
    EnemyBody,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
    Laser,
    Snapshot,
)
CORPUS_DIR = Path(__file__).with_name("corpus") / "counterexamples"
ACTION_BY_NAME = {action.name: action for action in CONTROL_ACTIONS}


def load_cases() -> tuple[dict, ...]:
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CORPUS_DIR.glob("*.json"))
    )


def decode_snapshot(raw: dict) -> Snapshot:
    values = dict(raw)
    values["bullets"] = tuple(Bullet(**item) for item in values["bullets"])
    values["despawning_bullets"] = tuple(
        Bullet(**item) for item in values["despawning_bullets"]
    )
    values["lasers"] = tuple(Laser(**item) for item in values["lasers"])
    values["enemies"] = tuple(EnemyBody(**item) for item in values["enemies"])
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
    return Snapshot(**values)
