"""Small route-side runtime for compiled spatial feedback tubes."""

from __future__ import annotations

from collections.abc import Mapping

from ..model import ACTIONS, CONTROL_ACTIONS, Action, action_from_input
from .base import ProposalRequest, RouteIntent, RouteProposal
from .phase import ecl_source_instruction_id


EncodedSampleV1 = tuple[int, int, int, int]
EncodedSampleV2 = tuple[int, int, int, int, int]
EncodedSample = EncodedSampleV1 | EncodedSampleV2
SamplesByTime = Mapping[int, tuple[EncodedSample, ...]]


def _hard_mask(request: ProposalRequest) -> int:
    allowed = frozenset(candidate.action for candidate in request.hard)
    return sum(
        1 << index
        for index, action in enumerate(CONTROL_ACTIONS)
        if action in allowed
    )


def _decode_sample(
    sample: EncodedSample,
    schema: int,
) -> tuple[int, int, int, int, int]:
    if schema == 1 and len(sample) == 4:
        sample_x, sample_y, held_index, proposal_index = sample
        return sample_x, sample_y, held_index, proposal_index, 0
    if schema == 2 and len(sample) == 5:
        return sample
    raise ValueError("compiled feedback sample does not match its schema")


def feedback_distance_sq(
    request: ProposalRequest,
    boss,
    samples_by_time: SamplesByTime,
    *,
    schema: int,
    position_scale: int,
    held_mismatch_penalty: int,
    hard_mask_mismatch_penalty: int = 0,
) -> int | None:
    """Return distance to the demonstrated semantic tube at this clock."""
    samples = samples_by_time.get(boss.ecl_time, ())
    if not samples:
        return None
    snapshot = request.snapshot
    current = action_from_input(snapshot.input_mask)
    x_scaled = round(snapshot.x * position_scale)
    y_scaled = round(snapshot.y * position_scale)
    current_hard_mask = _hard_mask(request)
    return min(
        (decoded[0] - x_scaled) ** 2
        + (decoded[1] - y_scaled) ** 2
        + (0 if CONTROL_ACTIONS[decoded[2]] == current else held_mismatch_penalty)
        + (
            (decoded[4] ^ current_hard_mask).bit_count()
            * hard_mask_mismatch_penalty
        )
        for decoded in (_decode_sample(sample, schema) for sample in samples)
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
    hard_mask_mismatch_penalty: int = 0,
    success_source: str,
    hold_source: str,
    schema_mismatch_source: str,
    source_mismatch_source: str,
) -> RouteProposal:
    """Rank only fresh-Hard actions by nearest demonstrated feedback state."""
    if schema not in (1, 2):
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
    current_hard_mask = _hard_mask(request)
    nearest_by_action: dict[Action, int] = {}
    for encoded in samples_by_time.get(boss.ecl_time, ()):
        sample_x, sample_y, held_index, proposal_index, sample_hard_mask = (
            _decode_sample(encoded, schema)
        )
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
            + (
                (sample_hard_mask ^ current_hard_mask).bit_count()
                * hard_mask_mismatch_penalty
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
