"""Proposal/ranking layer. It has no authority to add actions."""

from __future__ import annotations

import math

from .model import (
    ACTIONS,
    CONTROL_ACTIONS,
    Action,
    SafeAction,
    Snapshot,
    action_from_input,
)
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


def near_two_walls(snapshot: Snapshot, lookahead_frames: int = 20) -> bool:
    """Whether both boundary axes are inside one soft lookahead window."""
    lookahead = snapshot.focus_speed * lookahead_frames
    return (
        min(snapshot.x - MOVEMENT_LEFT, MOVEMENT_RIGHT - snapshot.x) <= lookahead
        and min(snapshot.y - MOVEMENT_TOP, MOVEMENT_BOTTOM - snapshot.y) <= lookahead
    )


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


def boundary_relief(
    snapshot: Snapshot,
    action: Action,
    lookahead_frames: int = 16,
) -> int:
    """Positive movement room across every boundary in soft lookahead."""
    lookahead = snapshot.focus_speed * lookahead_frames
    relief = 0
    if snapshot.x - MOVEMENT_LEFT <= lookahead:
        relief += action.dx
    if MOVEMENT_RIGHT - snapshot.x <= lookahead:
        relief -= action.dx
    if snapshot.y - MOVEMENT_TOP <= lookahead:
        relief += action.dy
    if MOVEMENT_BOTTOM - snapshot.y <= lookahead:
        relief -= action.dy
    return relief


class ProposalRanker:
    def __init__(self) -> None:
        self.preference = {action: 0.0 for action in CONTROL_ACTIONS}
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
        discouraged_actions: frozenset[Action] = frozenset(),
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
        best_clearance = max(candidate.clearance for candidate in candidates)
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
        open_boundary_contact = (
            current_boundary_room <= 0.01
            and candidate_actions == durable_actions
            and len(candidate_actions) == len(ACTIONS)
        )

        def score(candidate: SafeAction) -> tuple[
            bool, bool, bool, bool, bool, bool, bool,
            int, bool, float, float, float, float, str,
        ]:
            useful_position = -0.04 * math.hypot(candidate.final_x - 192.0, candidate.final_y - 380.0)
            continuity = 0.15 if candidate.action == current else 0.0
            candidate_boundary_room = _boundary_room(
                candidate.final_x, candidate.final_y
            )
            boundary_egress = candidate_boundary_room > current_boundary_room + 0.25
            preserved_boundary_room = (
                candidate_boundary_room
                if current_boundary_room <= snapshot.focus_speed * 20.0
                else current_boundary_room
            )
            # Stage 5 f6016 reached the exact bottom edge with every Hard-4
            # and longer-rollout action still available. Dense clearance then
            # preferred a tangent path and later stay/down paths until the
            # upward corridor disappeared. Leave only that uniformly open
            # case: f2565 was still 0.235 px off the edge, while f2570 had just
            # one h7 survivor. Applying this override there caused an earlier
            # empty set at f2573. This only ranks hard-admitted candidates.
            urgent_egress = (
                near_corner or open_boundary_contact
            ) and boundary_egress
            # Use the same one-Hard-segment-early boundary window as the
            # solver's soft wall search. Stage 4 f4544 was 38.8 px from the
            # bottom: the 20-frame detector had already entered its warning
            # band, while this 16-frame tie-break still treated down and left
            # alike and selected the descending route that emptied at f4561.
            relief = boundary_relief(snapshot, candidate.action, 20)
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
                candidate.action not in discouraged_actions,
                candidate.action in durable_actions,
                candidate.action == continued_repair,
                candidate.action in repairable_actions,
                (
                    len(snapshot.bullets) < 400
                    or
                    len(candidate_actions) < len(ACTIONS)
                    or candidate.clearance >= best_clearance - 1.0
                ),
                (
                    near_single_wall(snapshot)
                    and len(candidate_actions) <= 2
                    and candidate.action == current
                ),
                relief,
                boundary_egress,
                preserved_boundary_room,
                total,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(candidates, key=score)
        started_boundary_egress = score(chosen)[0]
        # A Stage 1 physical CE selected the correct first repair segment, then
        # discarded it after one frame.  Preserve a selective repair proposal
        # for one hard horizon, while the freshly certified candidates retain
        # absolute authority on every decision.
        selective_repair = (
            bool(repairable_actions)
            and len(repairable_actions) < len(candidate_actions)
            and chosen.action in repairable_actions
        )
        if started_boundary_egress and continued_repair != chosen.action:
            # Stage 5 f2892 and f2930 correctly began leaving the exact bottom
            # edge, then clearance reversed them after one decision and the
            # same linear wave closed at f2946. Keep that egress proposal for
            # one Hard-4 segment. Every following frame must still admit it,
            # and a narrowed durable set ranks ahead of this continuation.
            self.repair_action = chosen.action
            self.repair_stage = snapshot.stage
            self.repair_until_frame = snapshot.frame + max(1, repair_span)
        elif selective_repair and continued_repair != chosen.action:
            self.repair_action = chosen.action
            self.repair_stage = snapshot.stage
            self.repair_until_frame = snapshot.frame + max(1, repair_span)
        elif continued_repair is not None and chosen.action != continued_repair:
            self.repair_action = None
            self.repair_stage = None
            self.repair_until_frame = None
        self.previous_action = chosen.action
        return chosen
