"""Proposal/ranking layer. It has no authority to add actions."""

from __future__ import annotations

import math

from .model import ACTIONS, Action, SafeAction, Snapshot, action_from_input


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
    ) -> SafeAction:
        current = action_from_input(snapshot.input_mask)

        def score(candidate: SafeAction) -> tuple[bool, float, float, float, str]:
            useful_position = -0.04 * math.hypot(candidate.final_x - 192.0, candidate.final_y - 380.0)
            continuity = 0.15 if candidate.action == current else 0.0
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
                total,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(candidates, key=score)
        self.previous_action = chosen.action
        return chosen
