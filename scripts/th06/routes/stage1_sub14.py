"""Hard/Reimu-A Stage 1 main-boss sub14 basin policies."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ..model import ACTIONS, Action, action_from_input
from ..safety import (
    MOVEMENT_BOTTOM,
    MOVEMENT_LEFT,
    MOVEMENT_RIGHT,
    MOVEMENT_TOP,
)
from .base import ProposalRequest, RouteIntent, RouteProposal
from .feedback_tube import compiled_feedback_proposal, feedback_distance_sq
from .phase import ecl_source_instruction_id
from .stage1_sub14_data import (
    ECL_SHA256,
    HELD_MISMATCH_PENALTY,
    POLICY_SCHEMA,
    POSITION_SCALE,
    SAMPLES,
)


@dataclass(frozen=True)
class SourceEvent:
    local_time: int
    relative_offset: int
    opcode: int
    role: str


@dataclass(frozen=True)
class Sub14Contract:
    subroutine: int
    entry_time: int
    exit_time: int
    ecl_sha256: str
    instruction_offsets: frozenset[int]
    events: tuple[SourceEvent, ...]


# Verified by ``load_stage_ecl_program`` against installed ecldata1.ecl. On
# Hard, sub14 has exactly two hostile transitions before its t200 random call
# dispatch.  Other difficulty variants remain in the instruction-offset set
# because the live VM may publish only after skipping them.
CONTRACT = Sub14Contract(
    subroutine=14,
    entry_time=0,
    exit_time=200,
    ecl_sha256=ECL_SHA256,
    instruction_offsets=frozenset((
        0x0, 0x14, 0x24, 0x34, 0x60, 0x8C, 0xB8, 0xE4,
        0xF4, 0x120, 0x14C, 0x178, 0x18C, 0x1AC, 0x1CC,
    )),
    events=(
        SourceEvent(80, 0x8C, 67, "Hard aimed 5x16 fan"),
        SourceEvent(110, 0x120, 69, "Hard aimed 24x2 circle"),
        SourceEvent(200, 0x18C, 39, "conditional call sub13"),
        SourceEvent(200, 0x1AC, 39, "conditional call sub12"),
        SourceEvent(200, 0x1CC, 35, "fallback call sub15"),
    ),
)


_SAMPLES_BY_TIME = dict(SAMPLES)

# The original compiled route's disjoint delivery holdout reached distance
# 612 at most.  Use the next power of two as an inspectable entry guard.  The
# f5630 physical root that rejected that route is far outside it (228861).
COMPILED_ENTRY_HOLDOUT_MAX_DISTANCE_SQ = 612
COMPILED_ENTRY_MAX_DISTANCE_SQ = 1024
DURABLE_HORIZON = 12
REPAIR_SPLIT = 4
REPAIR_HORIZON = 8
REPAIR_COMMITMENT_FRAMES = 4
USEFUL_POSITION = (192.0, 380.0)
USEFUL_POSITION_WEIGHT = 0.08


@dataclass
class Sub14PolicyState:
    """Latch one measured entry basin and a short local repair command."""

    context: str | None = None
    basin: str | None = None
    entry_distance_sq: int | None = None
    repair_action: Action | None = None
    repair_until_frame: int | None = None
    last_frame: int | None = None
    last_local_time: int | None = None

    def reset(self) -> None:
        self.context = None
        self.basin = None
        self.entry_distance_sq = None
        self.repair_action = None
        self.repair_until_frame = None
        self.last_frame = None
        self.last_local_time = None

    def enter(
        self,
        intent: RouteIntent,
        request: ProposalRequest,
        boss,
        entry_distance_sq: int | None,
    ) -> str:
        if (
            self.context != intent.phase_id
            or (
                self.last_frame is not None
                and request.snapshot.frame <= self.last_frame
            )
            or (
                self.last_local_time is not None
                and boss.ecl_time <= self.last_local_time
            )
        ):
            self.reset()
        if self.basin is None:
            self.context = intent.phase_id
            self.entry_distance_sq = entry_distance_sq
            self.basin = (
                "compiled"
                if (
                    entry_distance_sq is not None
                    and entry_distance_sq <= COMPILED_ENTRY_MAX_DISTANCE_SQ
                )
                else "durable"
            )
        self.last_frame = request.snapshot.frame
        self.last_local_time = boss.ecl_time
        return self.basin


def compiled_sub14_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
    boss,
) -> RouteProposal:
    """Rank current Hard actions by the nearest robust demonstration tube.

    Every sample is keyed by source-local time and continuous player state,
    not a physical frame or RNG identity.  Multiple delivery demonstrations
    at the same clock form the tube width.  The live held input participates
    in the distance because transition-prefix state changes the correct next
    command.  Common Hard remains the final and only eligibility authority.
    """
    return compiled_feedback_proposal(
        intent,
        request,
        boss,
        schema=POLICY_SCHEMA,
        subroutine=CONTRACT.subroutine,
        start_time=CONTRACT.entry_time + 1,
        stop_time=CONTRACT.exit_time,
        instruction_offsets=CONTRACT.instruction_offsets,
        samples_by_time=_SAMPLES_BY_TIME,
        position_scale=POSITION_SCALE,
        held_mismatch_penalty=HELD_MISMATCH_PENALTY,
        success_source="compiled-sub14-feedback-tube-v1",
        hold_source="compiled-sub14-tube-hold",
        schema_mismatch_source="compiled-sub14-schema-mismatch",
        source_mismatch_source="compiled-sub14-source-mismatch",
    )


def _boundary_room(x: float, y: float) -> float:
    return min(
        x - MOVEMENT_LEFT,
        MOVEMENT_RIGHT - x,
        y - MOVEMENT_TOP,
        MOVEMENT_BOTTOM - y,
    )


def _unavailable(
    intent: RouteIntent,
    source: str,
    *,
    effort_horizon: int = 4,
) -> RouteProposal:
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=(),
        commitment_frames=1,
        effort_horizon=effort_horizon,
        proposal_source=source,
        provenance=intent.provenance,
        available=False,
    )


def _timeout_hold(
    intent: RouteIntent,
    request: ProposalRequest,
    source: str,
) -> RouteProposal:
    """Discard incomplete soft work and retain only a fresh-Hard hold."""
    current = action_from_input(request.snapshot.input_mask)
    hard_actions = frozenset(candidate.action for candidate in request.hard)
    action_tiers = ((current,),) if current in hard_actions else ()
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=action_tiers,
        commitment_frames=1,
        effort_horizon=4,
        proposal_source=source,
        provenance=intent.provenance,
    )


def durable_sub14_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
    state: Sub14PolicyState,
) -> RouteProposal:
    """Rank focused Hard actions by one bounded durable/repair primitive."""
    focused_hard = tuple(
        candidate for candidate in request.hard if candidate.action in ACTIONS
    )
    if not focused_hard:
        return _unavailable(intent, "sub14-durable-no-focused-hard")

    durable = request.services.certify_selected_budgeted(
        request.snapshot,
        DURABLE_HORIZON,
        tuple(candidate.action for candidate in focused_hard),
    )
    if durable is None:
        return _timeout_hold(
            intent,
            request,
            "sub14-durable-timeout-hold",
        )
    durable_actions = frozenset(candidate.action for candidate in durable)
    repairable_actions: frozenset[Action] = frozenset()
    if not durable_actions:
        scores = request.services.replanning_scores(
            request.snapshot,
            focused_hard,
            REPAIR_SPLIT,
            REPAIR_HORIZON,
        )
        if scores is None:
            return _timeout_hold(
                intent,
                request,
                "sub14-repair-timeout-hold",
            )
        best = max(scores.values(), default=0)
        if best <= 0:
            return _unavailable(
                intent,
                "sub14-no-repairable-action",
                effort_horizon=DURABLE_HORIZON,
            )
        repairable_actions = frozenset(
            action for action, score in scores.items() if score == best
        )

    snapshot = request.snapshot
    current = action_from_input(snapshot.input_mask)
    candidate_actions = frozenset(
        candidate.action for candidate in focused_hard
    )
    continued_repair = (
        state.repair_action
        if (
            state.repair_action in candidate_actions
            and state.repair_until_frame is not None
            and snapshot.frame < state.repair_until_frame
        )
        else None
    )
    current_room = _boundary_room(snapshot.x, snapshot.y)

    def score(candidate) -> tuple:
        useful_position = -USEFUL_POSITION_WEIGHT * math.hypot(
            candidate.final_x - USEFUL_POSITION[0],
            candidate.final_y - USEFUL_POSITION[1],
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

    ranked = tuple(sorted(focused_hard, key=score, reverse=True))
    chosen = ranked[0]
    selective_repair = (
        repairable_actions
        and len(repairable_actions) < len(candidate_actions)
        and chosen.action in repairable_actions
    )
    if selective_repair and continued_repair != chosen.action:
        state.repair_action = chosen.action
        state.repair_until_frame = snapshot.frame + REPAIR_COMMITMENT_FRAMES
    elif continued_repair is not None and chosen.action != continued_repair:
        state.repair_action = None
        state.repair_until_frame = None

    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=tuple((candidate.action,) for candidate in ranked),
        commitment_frames=1,
        effort_horizon=DURABLE_HORIZON,
        proposal_source=(
            "sub14-durable-h12"
            if durable_actions
            else "sub14-selective-repair-h8"
        ),
        provenance=intent.provenance,
    )


def sub14_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
    boss,
    state: Sub14PolicyState,
) -> RouteProposal:
    """Select one controller from entry feedback, then keep it for the phase."""
    source_id = ecl_source_instruction_id(boss)
    if (
        source_id is None
        or source_id[0] != CONTRACT.subroutine
        or source_id[1] not in CONTRACT.instruction_offsets
        or not CONTRACT.entry_time < boss.ecl_time < CONTRACT.exit_time
    ):
        state.reset()
        return _unavailable(intent, "sub14-source-mismatch")
    distance = feedback_distance_sq(
        request,
        boss,
        _SAMPLES_BY_TIME,
        schema=POLICY_SCHEMA,
        position_scale=POSITION_SCALE,
        held_mismatch_penalty=HELD_MISMATCH_PENALTY,
    )
    basin = state.enter(intent, request, boss, distance)
    if basin == "compiled":
        return compiled_sub14_proposal(intent, request, boss)
    return durable_sub14_proposal(intent, request, state)
