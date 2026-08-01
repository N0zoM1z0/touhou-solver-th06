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


def near_single_wall(snapshot: Snapshot) -> bool:
    """Whether one boundary axis, but not a corner, is in soft lookahead."""
    lookahead = snapshot.focus_speed * 16.0
    horizontal_near = min(
        snapshot.x - MOVEMENT_LEFT,
        MOVEMENT_RIGHT - snapshot.x,
    ) <= lookahead
    vertical_near = min(
        snapshot.y - MOVEMENT_TOP,
        MOVEMENT_BOTTOM - snapshot.y,
    ) <= lookahead
    return horizontal_near != vertical_near


def heads_toward_single_wall(snapshot: Snapshot, action: Action) -> bool:
    """Identify proposals that spend room along the sole nearby wall axis."""
    if not near_single_wall(snapshot):
        return False
    lookahead = snapshot.focus_speed * 16.0
    left_room = snapshot.x - MOVEMENT_LEFT
    right_room = MOVEMENT_RIGHT - snapshot.x
    if min(left_room, right_room) <= lookahead:
        return action.dx < 0 if left_room <= right_room else action.dx > 0
    top_room = snapshot.y - MOVEMENT_TOP
    bottom_room = MOVEMENT_BOTTOM - snapshot.y
    return action.dy < 0 if top_room <= bottom_room else action.dy > 0


class ProposalRanker:
    def __init__(self) -> None:
        self.preference = {action: 0.0 for action in ACTIONS}
        self.previous_action: Action | None = None
        self.repair_action: Action | None = None
        self.repair_stage: int | None = None
        self.repair_until_frame: int | None = None

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
        repair_span: int = 4,
    ) -> SafeAction:
        current = action_from_input(snapshot.input_mask)
        continued_repair: Action | None = self.repair_action
        candidate_actions = frozenset(candidate.action for candidate in candidates)
        if (
            continued_repair not in candidate_actions
            or self.repair_stage != snapshot.stage
            or self.repair_until_frame is None
            or snapshot.frame >= self.repair_until_frame
        ):
            continued_repair = None
            self.repair_action = None
            self.repair_stage = None
            self.repair_until_frame = None

        current_boundary_room = _boundary_room(snapshot.x, snapshot.y)
        horizontal_room = min(
            snapshot.x - MOVEMENT_LEFT,
            MOVEMENT_RIGHT - snapshot.x,
        )
        vertical_room = min(
            snapshot.y - MOVEMENT_TOP,
            MOVEMENT_BOTTOM - snapshot.y,
        )
        near_corner = (
            horizontal_room <= snapshot.focus_speed + 0.25
            and vertical_room <= snapshot.focus_speed + 0.25
        )

        boundary_lookahead = snapshot.focus_speed * 16.0

        def score(candidate: SafeAction) -> tuple[bool, bool, bool, bool, bool, int, bool, float, float, float, str]:
            useful_position = -0.04 * math.hypot(candidate.final_x - 192.0, candidate.final_y - 380.0)
            continuity = 0.15 if candidate.action == current else 0.0
            boundary_egress = (
                _boundary_room(candidate.final_x, candidate.final_y)
                > current_boundary_room + 0.25
            )
            urgent_egress = near_corner and boundary_egress
            boundary_relief = 0
            if snapshot.x - MOVEMENT_LEFT <= boundary_lookahead:
                boundary_relief += candidate.action.dx
            if MOVEMENT_RIGHT - snapshot.x <= boundary_lookahead:
                boundary_relief -= candidate.action.dx
            if snapshot.y - MOVEMENT_TOP <= boundary_lookahead:
                boundary_relief += candidate.action.dy
            if MOVEMENT_BOTTOM - snapshot.y <= boundary_lookahead:
                boundary_relief -= candidate.action.dy
            total = (
                min(80.0, candidate.clearance)
                + useful_position
                + continuity
                + self.preference[candidate.action]
            )
            # A longer source-grounded survival rollout is the primary soft
            # proposal signal, but it never adds to or removes from candidates.
            return (
                urgent_egress,
                candidate.action in durable_actions,
                candidate.action == continued_repair,
                candidate.action in repairable_actions,
                (
                    near_single_wall(snapshot)
                    and len(candidate_actions) <= 2
                    and candidate.action == current
                ),
                boundary_relief,
                boundary_egress,
                total,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(candidates, key=score)
        # A Stage 1 physical CE selected the correct first repair segment, then
        # discarded it after one frame.  Preserve a selective repair proposal
        # for one hard horizon, while the freshly certified candidates retain
        # absolute authority on every decision.
        selective_repair = (
            bool(repairable_actions)
            and len(repairable_actions) < len(candidate_actions)
            and chosen.action in repairable_actions
        )
        if selective_repair and continued_repair != chosen.action:
            self.repair_action = chosen.action
            self.repair_stage = snapshot.stage
            self.repair_until_frame = snapshot.frame + max(1, repair_span)
        elif continued_repair is not None and chosen.action != continued_repair:
            self.repair_action = None
            self.repair_stage = None
            self.repair_until_frame = None
        self.previous_action = chosen.action
        return chosen
