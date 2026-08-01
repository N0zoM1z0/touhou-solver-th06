"""Cheap long-horizon laser proposal; never an action authority."""

from __future__ import annotations

from dataclasses import replace

from .model import Action, Snapshot, action_from_input


LASER_EFFORT_HORIZON = 24


def isolate_lasers(snapshot: Snapshot) -> Snapshot:
    """Keep native timing/player state while removing non-laser work."""
    return replace(
        snapshot,
        bullets=(),
        enemies=(),
        despawning_bullets=(),
    )


def retained_current_corridor(
    snapshot: Snapshot,
    hard_actions: frozenset[Action],
    laser_survivors: frozenset[Action],
) -> Action | None:
    """Retain, but never enter, a long-lived laser corridor."""
    current = action_from_input(snapshot.input_mask)
    if current in hard_actions and current in laser_survivors:
        return current
    return None
