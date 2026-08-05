"""Stage 1/sub12 residual policies and their installed-source contract."""

from __future__ import annotations

from dataclasses import dataclass

from .base import ProposalRequest, RouteIntent, RouteProposal
from .feedback_tube import compiled_feedback_proposal, feedback_distance_sq
from .policy import proposal_from_intent
from .stage1_sub12_residual_data import (
    ECL_SHA256,
    HELD_MISMATCH_PENALTY,
    MAX_FEEDBACK_DISTANCE_SQ,
    POLICY_SCHEMA,
    POSITION_SCALE,
    SAMPLES,
)


RIGHT_STREAM_TARGET = (376.0, 320.0)


@dataclass(frozen=True)
class SourceEvent:
    local_time: int
    relative_offset: int
    opcode: int
    role: str


@dataclass(frozen=True)
class Sub12ResidualContract:
    subroutine: int
    start_time: int
    stop_time: int
    ecl_sha256: str
    instruction_offsets: frozenset[int]
    events: tuple[SourceEvent, ...]


CONTRACT = Sub12ResidualContract(
    subroutine=12,
    start_time=61,
    stop_time=180,
    ecl_sha256=ECL_SHA256,
    # After the final Hard t60 fan, this t180 instruction is the unique next
    # source identity until the random branch dispatch executes.
    instruction_offsets=frozenset((0x574,)),
    events=(
        SourceEvent(60, 0x50C, 67, "final Hard aimed fan"),
        SourceEvent(180, 0x588, 39, "conditional call sub13"),
        SourceEvent(180, 0x5A8, 39, "conditional call sub14"),
        SourceEvent(180, 0x5C8, 35, "fallback call sub15"),
    ),
)


_SAMPLES_BY_TIME = dict(SAMPLES)


def compiled_sub12_residual_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
    boss,
) -> RouteProposal:
    """Use the new central tube only inside its measured semantic basin."""
    compiled = compiled_feedback_proposal(
        intent,
        request,
        boss,
        schema=POLICY_SCHEMA,
        subroutine=CONTRACT.subroutine,
        start_time=CONTRACT.start_time,
        stop_time=CONTRACT.stop_time,
        instruction_offsets=CONTRACT.instruction_offsets,
        samples_by_time=_SAMPLES_BY_TIME,
        position_scale=POSITION_SCALE,
        held_mismatch_penalty=HELD_MISMATCH_PENALTY,
        success_source="compiled-sub12-residual-feedback-tube-v1",
        hold_source="compiled-sub12-residual-tube-hold",
        schema_mismatch_source="compiled-sub12-residual-schema-mismatch",
        source_mismatch_source="compiled-sub12-residual-source-mismatch",
    )
    if not compiled.available:
        return compiled

    distance = feedback_distance_sq(
        request,
        boss,
        _SAMPLES_BY_TIME,
        position_scale=POSITION_SCALE,
        held_mismatch_penalty=HELD_MISMATCH_PENALTY,
    )
    if distance is not None and distance <= MAX_FEEDBACK_DISTANCE_SQ:
        return compiled

    # Preserve the already physically promoted right-lane policy outside the
    # f6070 tube instead of extrapolating a nearest sample across the screen.
    fallback = RouteIntent(
        phase_id=intent.phase_id,
        policy_state="first-nonspell-residual-right-stream",
        algorithm="constant-frontier",
        horizon=8,
        target=RIGHT_STREAM_TARGET,
        commitment_frames=4,
        provenance=(
            "outside the compiled central tube; retain the physically "
            "promoted source-t61..t179 h8 right-stream policy"
        ),
    )
    return proposal_from_intent(fallback, request)
