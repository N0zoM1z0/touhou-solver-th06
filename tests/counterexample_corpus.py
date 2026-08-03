"""Load compact, physically observed solver counterexamples."""

from __future__ import annotations

import json
from pathlib import Path

from th06.barrage_lab.corpus import decode_snapshot
from th06.model import CONTROL_ACTIONS
CORPUS_DIR = Path(__file__).with_name("corpus") / "counterexamples"
ACTION_BY_NAME = {action.name: action for action in CONTROL_ACTIONS}


def load_cases() -> tuple[dict, ...]:
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CORPUS_DIR.glob("*.json"))
    )
