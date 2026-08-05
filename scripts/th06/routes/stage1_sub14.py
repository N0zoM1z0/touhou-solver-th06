"""Compiled Hard/Reimu-A Stage 1 main-boss sub14 feedback policy."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import ACTIONS, CONTROL_ACTIONS, Action, action_from_input
from .base import ProposalRequest, RouteIntent, RouteProposal
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


def _unavailable(intent: RouteIntent, source: str) -> RouteProposal:
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=(),
        commitment_frames=1,
        effort_horizon=4,
        proposal_source=source,
        provenance=intent.provenance,
        available=False,
    )


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
    if POLICY_SCHEMA != 1:
        return _unavailable(intent, "compiled-sub14-schema-mismatch")
    source_id = ecl_source_instruction_id(boss)
    if (
        source_id is None
        or source_id[0] != CONTRACT.subroutine
        or source_id[1] not in CONTRACT.instruction_offsets
        or not CONTRACT.entry_time < boss.ecl_time < CONTRACT.exit_time
    ):
        return _unavailable(intent, "compiled-sub14-source-mismatch")

    snapshot = request.snapshot
    current = action_from_input(snapshot.input_mask)
    x_quarter = round(snapshot.x * POSITION_SCALE)
    y_quarter = round(snapshot.y * POSITION_SCALE)
    hard_actions = frozenset(candidate.action for candidate in request.hard)
    nearest_by_action: dict[Action, int] = {}
    for sample_x, sample_y, held_index, proposal_index in _SAMPLES_BY_TIME.get(
        boss.ecl_time, ()
    ):
        action = ACTIONS[proposal_index]
        if action not in hard_actions:
            continue
        distance = (
            (sample_x - x_quarter) ** 2
            + (sample_y - y_quarter) ** 2
            + (
                0
                if CONTROL_ACTIONS[held_index] == current
                else HELD_MISMATCH_PENALTY
            )
        )
        nearest_by_action[action] = min(
            distance,
            nearest_by_action.get(action, distance),
        )

    ranked = tuple(sorted(
        nearest_by_action,
        key=lambda action: (nearest_by_action[action], action.name),
    ))
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=tuple((action,) for action in ranked),
        commitment_frames=1,
        effort_horizon=4,
        proposal_source=(
            "compiled-sub14-feedback-tube-v1"
            if ranked
            else "compiled-sub14-tube-hold"
        ),
        provenance=intent.provenance,
    )
