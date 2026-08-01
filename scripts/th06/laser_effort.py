"""Cheap long-horizon laser proposal; never an action authority."""

from __future__ import annotations

from dataclasses import replace

from .model import Snapshot


LASER_EFFORT_HORIZON = 24


def isolate_lasers(snapshot: Snapshot) -> Snapshot:
    """Keep native timing/player state while removing non-laser work."""
    return replace(
        snapshot,
        bullets=(),
        enemies=(),
        despawning_bullets=(),
    )
