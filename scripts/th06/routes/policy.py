"""Shared soft primitives used explicitly by route-owned phase policies.

This module is deliberately on the route side of the authority boundary.  It
adapts the existing compact ``RouteIntent`` tables while individual phases are
migrated to compiled policies.  Adding a new spell solver no longer requires a
branch in the common online solver.
"""

from __future__ import annotations

from ..model import Action
from ..ranking import preferred_target_actions
from .base import ProposalRequest, RouteIntent, RouteProposal


def _ordered_tie(
    actions,
    order: tuple[Action, ...],
) -> tuple[tuple[Action, ...], ...]:
    selected = frozenset(actions)
    tier = tuple(action for action in order if action in selected)
    return (tier,) if tier else ()


def proposal_from_intent(
    intent: RouteIntent,
    request: ProposalRequest,
) -> RouteProposal:
    """Evaluate one legacy table intent entirely inside its owning route.

    This is a migration adapter, not the target architecture for authored
    attacks.  Compiled phase policies bypass it and return ``RouteProposal``
    directly.
    """
    if intent.algorithm == "uncovered":
        return RouteProposal(
            phase_id=intent.phase_id,
            policy_state=intent.policy_state,
            action_tiers=(),
            commitment_frames=intent.commitment_frames,
            effort_horizon=4,
            proposal_source=intent.provenance,
            provenance=intent.provenance,
            available=False,
        )
    if intent.algorithm == "compiled-policy":
        raise ValueError(
            "compiled phase intent must be evaluated by its owning route"
        )

    snapshot = request.snapshot
    hard = request.hard
    hard_order = tuple(candidate.action for candidate in hard)
    hard_actions = frozenset(hard_order)
    preferred = tuple(
        action for action in intent.preferred_actions if action in hard_actions
    )
    completed_horizon = 4
    source = "compiled-actions" if preferred else intent.algorithm

    if intent.algorithm == "policy-volume":
        scores = request.services.nominal_policy_counts(
            snapshot, hard, intent.horizon
        )
        if scores is None:
            source = "policy-timeout-hold"
            preferred = ()
        else:
            completed_horizon = intent.horizon
            best = max(scores.values(), default=0)
            preferred = tuple(
                action for action in hard_order
                if best > 0 and scores.get(action, 0) == best
            )
    elif intent.algorithm in ("count-clearance", "constant-frontier-count"):
        working = hard
        if intent.algorithm == "constant-frontier-count":
            working = request.services.certify_selected(
                snapshot, intent.horizon, hard_order
            )
            if not working:
                preferred = ()
                completed_horizon = intent.horizon
            else:
                guidance = request.services.terminal_guidance(
                    snapshot, working, intent.horizon
                )
                if guidance is None:
                    source = "constant-frontier-count-timeout-hold"
                    preferred = ()
                else:
                    completed_horizon = intent.horizon
                    best = max(
                        (value.terminal_count for value in guidance.values()),
                        default=0,
                    )
                    preferred = tuple(
                        action for action in hard_order
                        if action in {candidate.action for candidate in working}
                        and best > 0
                        and guidance[action].terminal_count == best
                    )
        else:
            guidance = request.services.terminal_guidance(
                snapshot, working, intent.horizon
            )
            if guidance is None:
                source = "count-clearance-timeout-hold"
                preferred = ()
            else:
                completed_horizon = intent.horizon
                scores = {
                    action: (value.terminal_count, value.free_clearance)
                    for action, value in guidance.items()
                }
                best = max(scores.values(), default=None)
                preferred = tuple(
                    action for action in hard_order
                    if best is not None and best[0] > 0 and scores[action] == best
                )
    elif intent.algorithm in ("constant-frontier", "constant-clearance"):
        reserve = request.services.certify_selected(
            snapshot, intent.horizon, hard_order
        )
        completed_horizon = intent.horizon
        if intent.algorithm == "constant-frontier":
            preferred = tuple(candidate.action for candidate in reserve)
        else:
            best = max((candidate.clearance for candidate in reserve), default=None)
            preferred = tuple(
                candidate.action for candidate in reserve
                if best is not None and candidate.clearance == best
            )
    elif intent.algorithm == "target-only":
        preferred = hard_order

    if preferred and intent.target is not None:
        targeted = preferred_target_actions(
            hard, frozenset(preferred), intent.target
        )
        if targeted:
            preferred = tuple(action for action in hard_order if action in targeted)

    return RouteProposal(
        phase_id=intent.phase_id,
        policy_state=intent.policy_state,
        action_tiers=_ordered_tie(preferred, hard_order),
        commitment_frames=intent.commitment_frames,
        effort_horizon=completed_horizon,
        proposal_source=source,
        provenance=intent.provenance,
    )
