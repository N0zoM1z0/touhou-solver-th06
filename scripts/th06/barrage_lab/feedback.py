"""Small offline feedback-tube compiler primitives shared by route phases."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
import math

from ..model import ACTIONS, CONTROL_ACTIONS, Action, Snapshot, action_from_input
from ..ranking import ProposalRanker
from ..safety import (
    MOVEMENT_BOTTOM,
    MOVEMENT_LEFT,
    MOVEMENT_RIGHT,
    MOVEMENT_TOP,
    certify_actions,
)
from ..viability import replanning_scores


POSITION_SCALE = 4
HELD_MISMATCH_PENALTY = 16 * POSITION_SCALE * POSITION_SCALE
SourceClock = Callable[[Snapshot], int]


def _boundary_room(x: float, y: float) -> float:
    return min(
        x - MOVEMENT_LEFT,
        MOVEMENT_RIGHT - x,
        y - MOVEMENT_TOP,
        MOVEMENT_BOTTOM - y,
    )


@dataclass(frozen=True)
class FeedbackSample:
    local_time: int
    x_quarter: int
    y_quarter: int
    held_action: int
    proposed_action: int


def samples_by_time(
    samples: tuple[FeedbackSample, ...],
) -> dict[int, tuple[FeedbackSample, ...]]:
    grouped: dict[int, list[FeedbackSample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.local_time].append(sample)
    return {
        local_time: tuple(values)
        for local_time, values in sorted(grouped.items())
    }


def parse_seed_range(value: str) -> tuple[int, ...]:
    if ":" in value:
        start, stop = (int(part) for part in value.split(":", 1))
        return tuple(range(start, stop))
    return tuple(int(part) for part in value.split(",") if part)


class HistoricalClearDemonstrator:
    """The b5 route heuristic, evaluated only offline under current Hard."""

    def __init__(
        self,
        samples: list[FeedbackSample],
        source_clock: SourceClock,
    ) -> None:
        self.samples = samples
        self.source_clock = source_clock
        self.repair_action: Action | None = None
        self.repair_until_frame: int | None = None

    def __call__(self, snapshot: Snapshot) -> Action | None:
        hard = certify_actions(snapshot, 4, actions=ACTIONS)
        if not hard:
            return None
        durable = certify_actions(
            snapshot,
            16,
            actions=tuple(candidate.action for candidate in hard),
        )
        durable_actions = frozenset(candidate.action for candidate in durable)
        repairable_actions: frozenset[Action] = frozenset()
        if not durable_actions:
            scores = replanning_scores(snapshot, hard, 4, 8)
            best = max(scores.values(), default=0)
            if best:
                repairable_actions = frozenset(
                    action for action, score in scores.items() if score == best
                )

        current = action_from_input(snapshot.input_mask)
        candidate_actions = frozenset(candidate.action for candidate in hard)
        continued_repair = (
            self.repair_action
            if self.repair_action in candidate_actions
            and self.repair_until_frame is not None
            and snapshot.frame < self.repair_until_frame
            else None
        )
        current_room = _boundary_room(snapshot.x, snapshot.y)

        def score(candidate) -> tuple:
            useful_position = -0.04 * math.hypot(
                candidate.final_x - 192.0,
                candidate.final_y - 380.0,
            )
            continuity = 0.15 if candidate.action == current else 0.0
            return (
                candidate.action in durable_actions,
                candidate.action == continued_repair,
                candidate.action in repairable_actions,
                _boundary_room(candidate.final_x, candidate.final_y)
                > current_room + 0.25,
                min(80.0, candidate.clearance) + useful_position + continuity,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(hard, key=score)
        selective_repair = (
            repairable_actions
            and len(repairable_actions) < len(candidate_actions)
            and chosen.action in repairable_actions
        )
        if selective_repair and continued_repair != chosen.action:
            self.repair_action = chosen.action
            self.repair_until_frame = snapshot.frame + 4
        elif continued_repair is not None and chosen.action != continued_repair:
            self.repair_action = None
            self.repair_until_frame = None

        self.samples.append(FeedbackSample(
            self.source_clock(snapshot),
            round(snapshot.x * POSITION_SCALE),
            round(snapshot.y * POSITION_SCALE),
            CONTROL_ACTIONS.index(current),
            ACTIONS.index(chosen.action),
        ))
        return chosen.action


class CompiledFeedbackPolicy:
    """Offline reference implementation of the constant-time route lookup."""

    def __init__(
        self,
        samples: tuple[FeedbackSample, ...],
        source_clock: SourceClock,
    ) -> None:
        self.samples = samples_by_time(samples)
        self.source_clock = source_clock
        self.ranker = ProposalRanker()

    def __call__(self, snapshot: Snapshot) -> Action | None:
        hard = certify_actions(snapshot, 4, actions=CONTROL_ACTIONS)
        if not hard:
            return None
        current = action_from_input(snapshot.input_mask)
        x_quarter = round(snapshot.x * POSITION_SCALE)
        y_quarter = round(snapshot.y * POSITION_SCALE)
        allowed = frozenset(candidate.action for candidate in hard)
        nearest_by_action: dict[Action, int] = {}
        for sample in self.samples.get(self.source_clock(snapshot), ()):
            proposed = ACTIONS[sample.proposed_action]
            if proposed not in allowed:
                continue
            distance = (
                (sample.x_quarter - x_quarter) ** 2
                + (sample.y_quarter - y_quarter) ** 2
                + (
                    0
                    if CONTROL_ACTIONS[sample.held_action] == current
                    else HELD_MISMATCH_PENALTY
                )
            )
            nearest_by_action[proposed] = min(
                distance,
                nearest_by_action.get(proposed, distance),
            )
        selected = (
            min(nearest_by_action, key=lambda action: (
                nearest_by_action[action], action.name
            ))
            if nearest_by_action
            else None
        )
        preferred = frozenset((selected,)) if selected is not None else frozenset()
        return self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=1,
        ).action
