"""Common Hard authority and route-pack dispatch.

The previous universal anytime solver is preserved at annotated tag
``pre-phase-route-pivot-20260804``.  This module intentionally contains no
stage strategy: route packs receive fresh Hard authority, rank only inside it,
and return an inspectable proposal.  This runtime re-intersects that proposal
with the same Hard set and publishes one action.
"""

from __future__ import annotations

import os
import time

from .hazards.lasers import unknown_motion_may_reach_player
from .guidance import terminal_guidance_scores
from .kernels.safety import NativeSafetyKernel
from .model import (
    CONTROL_ACTIONS,
    Action,
    Decision,
    PLAYER_ALIVE,
    PLAYER_INVULNERABLE,
    Snapshot,
    action_from_input,
)
from .ranking import ProposalRanker
from .routes import ProposalRequest, RouteRegistry, default_routes
from .safety import COLLISION_MARGIN, DELIVERY_DELAYS, certify_actions
from .viability import nominal_policy_scores, replanning_scores


HARD_SAFETY_HORIZON = 4
HARD_CURRENT_HOLD_HORIZON = HARD_SAFETY_HORIZON + 1
DEFAULT_DECISION_BUDGET_MS = 1000.0 / 60.0 * 0.75
PUBLICATION_GUARD_MS = 1.0


class _ProposalServices:
    """Deadline-aware source evaluators; no method can publish an action."""

    def __init__(self, solver: "Solver", started: float) -> None:
        self.solver = solver
        self.started = started

    def remaining_budget_ms(self) -> float:
        elapsed_ms = (self.solver.clock() - self.started) * 1000.0
        return (
            self.solver.decision_budget_ms
            - elapsed_ms
            - PUBLICATION_GUARD_MS
        )

    def certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ):
        return self.solver._certify_selected(snapshot, horizon, actions)

    def certify_selected_budgeted(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ):
        native = (
            getattr(type(self.solver.kernel), "certify_selected_budgeted", None)
            if self.solver.kernel is not None
            else None
        )
        if native is not None:
            budget_ms = self.remaining_budget_ms()
            if budget_ms <= 0.0:
                return None
            return native(
                self.solver.kernel,
                snapshot,
                horizon,
                actions,
                collision_margin=COLLISION_MARGIN,
                budget_ms=budget_ms,
            )
        return certify_actions(snapshot, horizon, actions=actions)

    def replanning_scores(
        self,
        snapshot: Snapshot,
        candidates,
        split: int,
        horizon: int,
    ):
        native = (
            getattr(type(self.solver.kernel), "replanning_scores_budgeted", None)
            if self.solver.kernel is not None
            else None
        )
        if native is not None:
            budget_ms = self.remaining_budget_ms()
            if budget_ms <= 0.0:
                return None
            return native(
                self.solver.kernel,
                snapshot,
                candidates,
                split,
                horizon,
                collision_margin=COLLISION_MARGIN,
                budget_ms=budget_ms,
            )
        return replanning_scores(
            snapshot,
            candidates,
            split,
            horizon,
            continuation_actions=CONTROL_ACTIONS,
        )

    def nominal_policy_counts(
        self,
        snapshot: Snapshot,
        hard,
        horizon: int,
    ) -> dict[Action, int] | None:
        if horizon <= HARD_SAFETY_HORIZON:
            return {candidate.action: 1 for candidate in hard}
        native = (
            getattr(
                type(self.solver.kernel),
                "nominal_policy_counts_budgeted",
                None,
            )
            if self.solver.kernel is not None
            else None
        )
        if native is not None:
            budget_ms = self.remaining_budget_ms()
            if budget_ms <= 0.0:
                return None
            return native(
                self.solver.kernel,
                snapshot,
                hard,
                HARD_SAFETY_HORIZON,
                horizon,
                collision_margin=COLLISION_MARGIN,
                budget_ms=budget_ms,
            )
        return nominal_policy_scores(
            snapshot,
            hard,
            HARD_SAFETY_HORIZON,
            horizon,
            continuation_actions=CONTROL_ACTIONS,
        )

    def terminal_guidance(
        self,
        snapshot: Snapshot,
        hard,
        horizon: int,
    ):
        native = (
            getattr(
                type(self.solver.kernel),
                "terminal_guidance_budgeted",
                None,
            )
            if self.solver.kernel is not None
            else None
        )
        if native is not None:
            budget_ms = self.remaining_budget_ms()
            if budget_ms <= 0.0:
                return None
            return native(
                self.solver.kernel,
                snapshot,
                hard,
                HARD_SAFETY_HORIZON,
                horizon,
                collision_margin=COLLISION_MARGIN,
                budget_ms=budget_ms,
            )
        return terminal_guidance_scores(
            snapshot,
            hard,
            HARD_SAFETY_HORIZON,
            horizon,
            continuation_actions=CONTROL_ACTIONS,
        )


class Solver:
    def __init__(
        self,
        ranker: ProposalRanker | None = None,
        decision_budget_ms: float = DEFAULT_DECISION_BUDGET_MS,
        clock=time.perf_counter,
        routes: RouteRegistry | None = None,
    ) -> None:
        if decision_budget_ms <= 0.0:
            raise ValueError("decision budget must be positive")
        self.ranker = ranker or ProposalRanker()
        self.kernel = NativeSafetyKernel() if os.name == "nt" else None
        self.backend = "native-c++" if self.kernel is not None else "python-reference"
        self.decision_budget_ms = decision_budget_ms
        self.clock = clock
        self.routes = routes or default_routes()
        self._proposal_context: tuple[str, str, str] | None = None

    def reset_plan(self) -> None:
        self.ranker.reset_plan()
        self._proposal_context = None

    def _enter_proposal_context(
        self,
        route_id: str,
        phase_id: str,
        policy_state: str,
    ) -> None:
        """Keep a soft commitment inside the state that authored it."""
        context = (route_id, phase_id, policy_state)
        if context == self._proposal_context:
            return
        self.ranker.reset_plan()
        self._proposal_context = context

    def observe(self, survived: bool) -> None:
        self.ranker.observe(survived)

    def observe_publication(self, _stale: bool) -> None:
        """Publication adaptation retired with the universal effort ladder."""

    def _certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ):
        if self.kernel is not None:
            return self.kernel.certify_selected(
                snapshot,
                horizon,
                actions,
                collision_margin=COLLISION_MARGIN,
            )
        return certify_actions(snapshot, horizon, actions=actions)

    def _hard_authority(self, snapshot: Snapshot):
        held = action_from_input(snapshot.input_mask)
        combined = (
            getattr(type(self.kernel), "certify_delivery_sets_with_selected", None)
            if self.kernel is not None
            else None
        )
        if combined is not None:
            return combined(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                HARD_CURRENT_HOLD_HORIZON,
                (held,),
                collision_margin=COLLISION_MARGIN,
            )
        hard = certify_actions(
            snapshot,
            HARD_SAFETY_HORIZON,
            actions=CONTROL_ACTIONS,
        )
        age_zero = (
            certify_actions(
                snapshot,
                HARD_SAFETY_HORIZON,
                delivery_delays=DELIVERY_DELAYS[:-1],
                actions=CONTROL_ACTIONS,
            )
            if not hard
            else ()
        )
        held_safe = (
            certify_actions(
                snapshot,
                HARD_CURRENT_HOLD_HORIZON,
                actions=(held,),
            )
            if any(candidate.action == held for candidate in hard)
            else ()
        )
        return hard, age_zero, held_safe

    def selected_delivery_safe(
        self,
        snapshot: Snapshot,
        action: Action,
        maximum_delay: int,
    ) -> bool:
        if maximum_delay <= DELIVERY_DELAYS[-1]:
            return bool(self._certify_selected(
                snapshot, HARD_SAFETY_HORIZON, (action,)
            ))
        if maximum_delay != DELIVERY_DELAYS[-1] + 1:
            return False
        extended = (
            getattr(type(self.kernel), "certify_selected_extended_delivery", None)
            if self.kernel is not None
            else None
        )
        if extended is not None:
            return bool(extended(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                (action,),
                collision_margin=COLLISION_MARGIN,
            ))
        return bool(certify_actions(
            snapshot,
            HARD_SAFETY_HORIZON,
            delivery_delays=DELIVERY_DELAYS + (maximum_delay,),
            actions=(action,),
        ))

    @staticmethod
    def _passive_reason(snapshot: Snapshot) -> str | None:
        if snapshot.in_menu:
            return "menu"
        if snapshot.replay_or_demo:
            return "replay-or-demo"
        if snapshot.time_stopped:
            return "time-stopped"
        if snapshot.player_state not in (PLAYER_ALIVE, PLAYER_INVULNERABLE):
            return "player-not-active"
        if not 0.99 <= snapshot.frame_multiplier <= 1.01:
            return "unsupported-frame-multiplier"
        if snapshot.laser_count != len(snapshot.lasers):
            return "unsupported-laser-decode"
        if any(
            not laser.motion_known
            and unknown_motion_may_reach_player(
                snapshot, laser, HARD_SAFETY_HORIZON
            )
            for laser in snapshot.lasers
        ):
            return "unsupported-laser-motion"
        return None

    def decide(
        self,
        snapshot: Snapshot,
        required_action: Action | None = None,
        required_delivery_delays: tuple[int, ...] = DELIVERY_DELAYS,
    ) -> Decision:
        passive = self._passive_reason(snapshot)
        if passive is not None:
            return Decision(None, (), 0.0, 0, passive)

        if required_action is not None:
            # This is an already-issued SendInput batch, not a new command.
            # Its lease reports only the delivery branches that can remain
            # after the newly observed native input.  The one-action,
            # one-frame reference proof is deliberately cheap and keeps the
            # exact delivery set explicit; the native all-action hot path has
            # no arbitrary-delay entry point.
            certified = certify_actions(
                snapshot,
                1,
                delivery_delays=required_delivery_delays,
                actions=(required_action,),
            )
            leased = next(
                (
                    candidate for candidate in certified
                    if candidate.action == required_action
                ),
                None,
            )
            if leased is None:
                return Decision(None, certified, 0.0, 1, "input-lease-unsafe", 1)
            return Decision(
                leased.action,
                certified,
                leased.clearance,
                1,
                "ok",
                1,
                route_id="input-lease",
                proposal_source="certified in-flight command",
            )

        started = self.clock()
        hard, age_zero, held_safe = self._hard_authority(snapshot)
        if not hard:
            return Decision(
                None,
                (),
                0.0,
                HARD_SAFETY_HORIZON,
                "hard-safe-set-empty",
                HARD_SAFETY_HORIZON,
                repairable_count=len(age_zero),
            )

        pack = self.routes.resolve(snapshot)
        if pack is None:
            return Decision(
                None,
                hard,
                0.0,
                HARD_SAFETY_HORIZON,
                "route-unavailable",
                HARD_SAFETY_HORIZON,
                held_horizon=(
                    HARD_CURRENT_HOLD_HORIZON if held_safe
                    else HARD_SAFETY_HORIZON
                ),
            )
        proposal = pack.propose(ProposalRequest(
            snapshot,
            hard,
            _ProposalServices(self, started),
        ))
        if proposal is None:
            return Decision(
                None,
                hard,
                0.0,
                HARD_SAFETY_HORIZON,
                "phase-unavailable",
                HARD_SAFETY_HORIZON,
                held_horizon=(
                    HARD_CURRENT_HOLD_HORIZON if held_safe
                    else HARD_SAFETY_HORIZON
                ),
                route_id=pack.route_id,
            )
        self._enter_proposal_context(
            pack.route_id,
            proposal.phase_id,
            proposal.policy_state,
        )
        if not proposal.available:
            return Decision(
                None,
                hard,
                0.0,
                HARD_SAFETY_HORIZON,
                "phase-unavailable",
                HARD_SAFETY_HORIZON,
                held_horizon=(
                    HARD_CURRENT_HOLD_HORIZON if held_safe
                    else HARD_SAFETY_HORIZON
                ),
                route_id=pack.route_id,
                phase_id=proposal.phase_id,
                policy_state=proposal.policy_state,
                proposal_source=proposal.proposal_source,
            )

        hard_actions = frozenset(candidate.action for candidate in hard)
        preferred = frozenset(proposal.first_hard_tier(hard_actions))

        chosen = self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=proposal.commitment_frames,
        )
        return Decision(
            chosen.action,
            hard,
            chosen.clearance,
            HARD_SAFETY_HORIZON,
            "ok",
            proposal.effort_horizon,
            len(preferred),
            0,
            (
                HARD_CURRENT_HOLD_HORIZON if held_safe
                else HARD_SAFETY_HORIZON
            ),
            route_id=pack.route_id,
            phase_id=proposal.phase_id,
            policy_state=proposal.policy_state,
            proposal_source=proposal.proposal_source,
        )
