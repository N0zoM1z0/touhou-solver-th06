"""Proposal/ranking layer. It has no authority to add actions."""

from __future__ import annotations

import math

from .model import ACTIONS, Action, SafeAction, Snapshot, action_from_input
from .safety import MOVEMENT_BOTTOM, MOVEMENT_LEFT, MOVEMENT_RIGHT, MOVEMENT_TOP


def _boundary_room(x: float, y: float) -> float:
    return min(
        x - MOVEMENT_LEFT,
        MOVEMENT_RIGHT - x,
        y - MOVEMENT_TOP,
        MOVEMENT_BOTTOM - y,
    )


class ProposalRanker:
    def __init__(self) -> None:
        self.preference = {action: 0.0 for action in ACTIONS}
        self.previous_action: Action | None = None

    def observe(self, survived: bool) -> None:
        if self.previous_action is None:
            return
        old = self.preference[self.previous_action]
        # Mere survival is not evidence that an action is good: the first
        # physical run showed that rewarding it locks motion into a boundary.
        # Keep only a small death penalty until richer context exists.
        updated = old * 0.997 if survived else old - 1.0
        self.preference[self.previous_action] = max(-2.0, min(0.0, updated))

    def choose(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        durable_actions: frozenset[Action] = frozenset(),
        repairable_actions: frozenset[Action] = frozenset(),
    ) -> SafeAction:
        current = action_from_input(snapshot.input_mask)

        current_boundary_room = _boundary_room(snapshot.x, snapshot.y)

        def score(candidate: SafeAction) -> tuple[bool, bool, bool, float, float, float, str]:
            useful_position = -0.04 * math.hypot(candidate.final_x - 192.0, candidate.final_y - 380.0)
            continuity = 0.15 if candidate.action == current else 0.0
            boundary_egress = (
                _boundary_room(candidate.final_x, candidate.final_y)
                > current_boundary_room + 0.25
            )
            total = (
                min(80.0, candidate.clearance)
                + useful_position
                + continuity
                + self.preference[candidate.action]
            )
            # A longer source-grounded survival rollout is the primary soft
            # proposal signal, but it never adds to or removes from candidates.
            return (
                candidate.action in durable_actions,
                candidate.action in repairable_actions,
                boundary_egress,
                total,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(candidates, key=score)
        self.previous_action = chosen.action
        return chosen
