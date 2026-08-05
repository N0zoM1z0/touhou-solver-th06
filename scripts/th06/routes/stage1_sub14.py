"""Compiled Hard/Reimu-A Stage 1 main-boss sub14 feedback policy."""

from __future__ import annotations

from dataclasses import dataclass

from .base import ProposalRequest, RouteIntent, RouteProposal
from .feedback_tube import compiled_feedback_proposal
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
