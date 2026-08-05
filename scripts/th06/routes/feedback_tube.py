"""Small route-side runtime for compiled spatial feedback tubes."""

from __future__ import annotations

from collections.abc import Mapping

from ..model import ACTIONS, CONTROL_ACTIONS, Action, action_from_input
from .base import ProposalRequest, RouteIntent, RouteProposal
from .phase import ecl_source_instruction_id


EncodedSample = tuple[int, int, int, int]
SamplesByTime = Mapping[int, tuple[EncodedSample, ...]]


def feedback_distance_sq(
    request: ProposalRequest,
    boss,
    samples_by_time: SamplesByTime,
    *,
    position_scale: int,
    held_mismatch_penalty: int,
) -> int | None:
    """Return distance to the demonstrated semantic tube at this clock."""
    samples = samples_by_time.get(boss.ecl_time, ())
    if not samples:
        return None
    snapshot = request.snapshot
    current = action_from_input(snapshot.input_mask)
    x_scaled = round(snapshot.x * position_scale)
    y_scaled = round(snapshot.y * position_scale)
    return min(
        (sample_x - x_scaled) ** 2
        + (sample_y - y_scaled) ** 2
        + (
            0
            if CONTROL_ACTIONS[held_index] == current
            else held_mismatch_penalty
        )
        for sample_x, sample_y, held_index, _proposal_index in samples
    )


def _unavailable(
    intent: RouteIntent,
    proposal_source: str,
) -> RouteProposal:
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=(),
        commitment_frames=1,
        effort_horizon=4,
        proposal_source=proposal_source,
        provenance=intent.provenance,
        available=False,
    )


def compiled_feedback_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
    boss,
    *,
    schema: int,
    subroutine: int,
    start_time: int,
    stop_time: int,
    instruction_offsets: frozenset[int],
    samples_by_time: SamplesByTime,
    position_scale: int,
    held_mismatch_penalty: int,
    success_source: str,
    hold_source: str,
    schema_mismatch_source: str,
    source_mismatch_source: str,
) -> RouteProposal:
    """Rank only fresh-Hard actions by nearest demonstrated feedback state."""
    if schema != 1:
        return _unavailable(intent, schema_mismatch_source)
    source_id = ecl_source_instruction_id(boss)
    if (
        source_id is None
        or source_id[0] != subroutine
        or source_id[1] not in instruction_offsets
        or not start_time <= boss.ecl_time < stop_time
    ):
        return _unavailable(intent, source_mismatch_source)

    snapshot = request.snapshot
    current = action_from_input(snapshot.input_mask)
    x_scaled = round(snapshot.x * position_scale)
    y_scaled = round(snapshot.y * position_scale)
    hard_actions = frozenset(candidate.action for candidate in request.hard)
    nearest_by_action: dict[Action, int] = {}
    for sample_x, sample_y, held_index, proposal_index in samples_by_time.get(
        boss.ecl_time, ()
    ):
        action = ACTIONS[proposal_index]
        if action not in hard_actions:
            continue
        distance = (
            (sample_x - x_scaled) ** 2
            + (sample_y - y_scaled) ** 2
            + (
                0
                if CONTROL_ACTIONS[held_index] == current
                else held_mismatch_penalty
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
        proposal_source=success_source if ranked else hold_source,
        provenance=intent.provenance,
    )
