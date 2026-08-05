"""Hard/Reimu-A Stage 1 second-nonspell source-cycle policy.

This module owns only soft route ranking.  Every candidate originates in the
fresh common Hard set and the runtime intersects the proposal with that same
set again immediately before publication.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Action, Snapshot, action_from_input
from .base import ProposalRequest, RouteIntent, RouteProposal
from .phase import boss_phase_id, ecl_source_instruction_id


ECL_SHA256 = "9d9a40e9f7e3ab9346d3874438134659cacf9d34f4aff57b96b4be4ea85b99d7"
BOTTOM_CENTER = (192.0, 380.0)


@dataclass(frozen=True)
class SourceSegment:
    subroutine: int
    name: str
    start_time: int
    stop_time: int

    def contains(self, local_time: int) -> bool:
        return self.start_time <= local_time <= self.stop_time


# Boundaries come directly from installed ecldata1.ecl.  A residual begins
# after that subroutine's final hostile birth/mutation; dispatch is the exact
# source clock at which the three RNG-conditioned tail calls execute.
SOURCE_SEGMENTS = (
    SourceSegment(18, "entry-positioning", 0, 11),
    SourceSegment(18, "aimed-fan", 12, 19),
    SourceSegment(18, "laser-births", 20, 60),
    SourceSegment(18, "laser-hold", 61, 123),
    SourceSegment(18, "laser-turn", 124, 164),
    SourceSegment(18, "residual", 165, 223),
    SourceSegment(18, "dispatch", 224, 224),
    SourceSegment(19, "entry-movement", 0, 59),
    SourceSegment(19, "circle-volley", 60, 120),
    SourceSegment(19, "residual", 121, 239),
    SourceSegment(19, "dispatch", 240, 240),
    SourceSegment(20, "entry-movement", 0, 59),
    SourceSegment(20, "aimed-fans", 60, 100),
    SourceSegment(20, "residual", 101, 219),
    SourceSegment(20, "dispatch", 220, 220),
    SourceSegment(21, "active", 0, 4),
    SourceSegment(21, "residual", 5, 123),
    SourceSegment(21, "dispatch", 124, 124),
)


INSTRUCTION_OFFSETS = {
    18: frozenset((
        0x0, 0x14, 0x24, 0x34, 0x60, 0x8C, 0xB8, 0xE4, 0xF4,
        0x134, 0x144, 0x184, 0x194, 0x1D4, 0x1E4, 0x224, 0x234,
        0x274, 0x284, 0x2C4, 0x2D4, 0x2E4, 0x2F4, 0x304, 0x314,
        0x324, 0x334, 0x348, 0x368, 0x388,
    )),
    19: frozenset((
        0x0, 0x14, 0x24, 0x34, 0x44, 0x70, 0x9C, 0xC8, 0xF4,
        0x104, 0x130, 0x15C, 0x188, 0x1B4, 0x1C4, 0x1F0, 0x21C,
        0x248, 0x274, 0x284, 0x298, 0x2B8, 0x2D8,
    )),
    20: frozenset((
        0x0, 0x14, 0x24, 0x34, 0x60, 0x8C, 0xB8, 0xE4, 0xF4,
        0x104, 0x130, 0x15C, 0x188, 0x1B4, 0x1C4, 0x1F0, 0x21C,
        0x248, 0x274, 0x284, 0x298, 0x2B8, 0x2D8,
    )),
    21: frozenset((
        0x0, 0x14, 0x24, 0x34, 0x48, 0x5C, 0x70, 0x84, 0x98,
        0xAC, 0xD8, 0x104, 0x130, 0x15C, 0x16C, 0x184, 0x19C,
        0x1B4, 0x1C8, 0x1DC, 0x208, 0x234, 0x260, 0x28C, 0x29C,
        0x2B4, 0x2CC, 0x2E4, 0x2F8, 0x318, 0x338,
    )),
}


def source_segment(subroutine: int, local_time: int) -> SourceSegment | None:
    return next(
        (
            segment for segment in SOURCE_SEGMENTS
            if segment.subroutine == subroutine and segment.contains(local_time)
        ),
        None,
    )


def caller_subroutine(boss) -> int | None:
    """Map the saved CALL return address to a stable source subroutine."""
    if not boss.ecl_stack or not boss.ecl_subroutines:
        return None
    address = boss.ecl_stack[-1].instruction_address
    return next(
        (
            index
            for index, base in reversed(tuple(enumerate(boss.ecl_subroutines)))
            if address >= base
        ),
        None,
    )


def _uncovered(phase_id: str, provenance: str) -> RouteIntent:
    return RouteIntent(
        phase_id,
        "uncovered",
        "uncovered",
        4,
        None,
        1,
        provenance=provenance,
    )


def second_nonspell_intent(snapshot: Snapshot, boss) -> RouteIntent:
    spell_active = bool(
        snapshot.player_attack and snapshot.player_attack.spell_active
    )
    phase_id = boss_phase_id(boss, spell_active)
    source_id = ecl_source_instruction_id(boss)
    if spell_active or source_id is None or source_id[0] not in INSTRUCTION_OFFSETS:
        return _uncovered(
            phase_id,
            "Stage 1 second-nonspell policy requires nonspell sub18-sub21",
        )
    subroutine, relative_offset = source_id
    segment = source_segment(subroutine, boss.ecl_time)
    if segment is None or relative_offset not in INSTRUCTION_OFFSETS[subroutine]:
        return _uncovered(
            phase_id,
            "installed Stage 1 second-nonspell source identity is incoherent",
        )

    state = f"second-nonspell-sub{subroutine}-{segment.name}"
    provenance = (
        f"installed ecldata1.ecl sha256 {ECL_SHA256[:12]}...; "
        f"source sub{subroutine} local t{segment.start_time}-"
        f"{segment.stop_time} {segment.name}; candidate-conditioned battle "
        "search from physical f8233 uses no frame or RNG identity"
    )
    if (
        subroutine == 18
        and segment.name == "entry-positioning"
        and caller_subroutine(boss) == 16
    ):
        return RouteIntent(
            phase_id,
            state + "-initial-call",
            "target-only",
            4,
            BOTTOM_CENTER,
            4,
            provenance=provenance + "; initial source CALL18 from sub16",
        )
    if subroutine == 18 and segment.name in (
        "entry-positioning",
        "aimed-fan",
        "laser-births",
        "laser-hold",
    ):
        return RouteIntent(
            phase_id,
            state + "-delivery-tube",
            "compiled-policy",
            12,
            None,
            1,
            provenance=provenance + "; sticky pickup-robust h12 command tube",
        )
    if subroutine == 18 and segment.name == "laser-turn":
        return RouteIntent(
            phase_id,
            state + "-turn-tube",
            "compiled-policy",
            10,
            None,
            1,
            provenance=provenance + "; sticky constant h10 reserve",
        )
    if segment.name == "residual":
        return RouteIntent(
            phase_id,
            state,
            "policy-volume",
            6,
            None,
            4,
            provenance=(
                provenance
                + "; final hostile source event has passed; target-free h6 "
                "preserves the candidate-conditioned residual field"
            ),
        )
    if segment.name == "dispatch":
        return RouteIntent(
            phase_id,
            state,
            "policy-volume",
            4,
            None,
            1,
            provenance=provenance + "; exact RNG-conditioned call boundary",
        )
    return RouteIntent(
        phase_id,
        state,
        "policy-volume",
        8,
        None,
        4,
        provenance=provenance,
    )


def _proposal(
    intent: RouteIntent,
    actions: tuple[Action, ...],
    source: str,
    effort_horizon: int,
    *,
    available: bool = True,
) -> RouteProposal:
    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=((actions,) if actions else ()),
        commitment_frames=1,
        effort_horizon=effort_horizon,
        proposal_source=source,
        provenance=intent.provenance,
        available=available,
    )


def _timeout_hold(intent: RouteIntent, request: ProposalRequest, source: str):
    current = action_from_input(request.snapshot.input_mask)
    if current in {candidate.action for candidate in request.hard}:
        return _proposal(intent, (current,), source, 4)
    return _proposal(intent, (), source, 4, available=False)


def second_nonspell_proposal(
    intent: RouteIntent,
    request: ProposalRequest,
) -> RouteProposal:
    """Evaluate the two sticky sub18 policies inside fresh common Hard."""
    hard_order = tuple(candidate.action for candidate in request.hard)
    current = action_from_input(request.snapshot.input_mask)
    reserve = request.services.certify_selected_budgeted(
        request.snapshot,
        intent.horizon,
        hard_order,
    )
    if reserve is None:
        return _timeout_hold(
            intent, request, "second-nonspell-reserve-timeout-hold"
        )
    reserve_actions = tuple(candidate.action for candidate in reserve)
    if current in reserve_actions:
        return _proposal(
            intent,
            (current,),
            "second-nonspell-sticky-current",
            intent.horizon,
        )

    preferred = reserve_actions
    if intent.horizon == 12:
        robust = request.services.delivery_segment_viability(
            request.snapshot,
            request.hard,
            4,
            8,
            12,
        )
        if robust is None:
            return _timeout_hold(
                intent, request, "second-nonspell-delivery-timeout-hold"
            )
        completed_horizon, membership, complete = robust
        if complete and completed_horizon == 12:
            viable = tuple(
                action for action in hard_order if membership.get(action, 0) > 0
            )
            if viable:
                viable_set = frozenset(viable)
                viable_hard = tuple(
                    candidate for candidate in request.hard
                    if candidate.action in viable_set
                )
                guidance = request.services.terminal_guidance(
                    request.snapshot, viable_hard, 12
                )
                if guidance is not None:
                    best = max(
                        (value.terminal_count for value in guidance.values()),
                        default=0,
                    )
                    preferred = tuple(
                        action for action in viable
                        if best <= 0 or guidance[action].terminal_count == best
                    )
                else:
                    preferred = viable
    else:
        guidance = request.services.terminal_guidance(
            request.snapshot, reserve, intent.horizon
        )
        if guidance is not None:
            best = max(
                (value.terminal_count for value in guidance.values()),
                default=0,
            )
            if best > 0:
                preferred = tuple(
                    action for action in reserve_actions
                    if guidance[action].terminal_count == best
                )

    if not preferred:
        best_clearance = max(
            (candidate.clearance for candidate in request.hard), default=None
        )
        preferred = tuple(
            candidate.action for candidate in request.hard
            if best_clearance is not None and candidate.clearance == best_clearance
        )
    return _proposal(
        intent,
        preferred,
        (
            "second-nonspell-sticky-delivery-h12"
            if intent.horizon == 12
            else "second-nonspell-sticky-reserve-count-h10"
        ),
        intent.horizon,
        available=bool(preferred),
    )
