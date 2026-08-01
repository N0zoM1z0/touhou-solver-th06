"""Compose adaptive horizon, hard authority, and proposal ranking."""

from __future__ import annotations

import os

from .hazards.lasers import future_hazards as future_laser_hazards
from .kernels.safety import NativeSafetyKernel
from .laser_effort import (
    LASER_EFFORT_HORIZON,
    isolate_lasers,
    retained_current_corridor,
)
from .model import Action, Decision, PLAYER_ALIVE, PLAYER_INVULNERABLE, Snapshot
from .ranking import ProposalRanker
from .safety import DELIVERY_DELAYS, certify_actions, nearest_current_clearance
from .viability import replanning_scores


# Physical runs normally bound a hazardous-state decision interval to two
# native frames and input pickup to two more.  Longer 8/12/16-frame rollouts
# allocate ranking effort; they must not turn constant-action rollout into a
# hard eligibility requirement.
HARD_SAFETY_HORIZON = 4


def adaptive_horizon(snapshot: Snapshot) -> int:
    # Long proposal rollouts are useful only if their result can arrive in
    # time.  A physical Stage 3 CE measured a 38.5 ms 16-frame solve at 284
    # bullets, while the same hard authority plus 8-frame effort stayed below
    # one native frame in the saved-snapshot benchmark.  This changes ranking
    # effort only; HARD_SAFETY_HORIZON and its allowed actions are unchanged.
    # Stage 4 f2663 spent 34.6 ms on effort-8 with 461 bullets and four
    # enemies; the resulting four-frame-old proposal was correctly discarded.
    # Hard-4 alone was timely, but a later 623-bullet branch needed h6 to reject
    # a rightward dead end two frames earlier. Keep this bounded compromise;
    # the hard authority itself remains four frames.
    if len(snapshot.bullets) >= 400:
        return 6
    if len(snapshot.bullets) >= 220:
        return 8
    if len(snapshot.bullets) >= 100:
        # Stage 4 f6425 spent 49.5 ms on a 16-frame repair with 119
        # bullets and six lasers, although four constant actions survived 12
        # frames. Keep mixed scenes inside one delivery interval here.
        return 12
    if snapshot.lasers or snapshot.enemies:
        return 16
    nearest = nearest_current_clearance(snapshot)
    if nearest < 48.0:
        return 16
    if nearest < 120.0:
        return 12
    return 8


class Solver:
    def __init__(self, ranker: ProposalRanker | None = None) -> None:
        self.ranker = ranker or ProposalRanker()
        self.kernel = NativeSafetyKernel() if os.name == "nt" else None
        self.backend = "native-c++" if self.kernel is not None else "python-reference"

    def _certify(self, snapshot: Snapshot, horizon: int):
        if self.kernel is not None:
            return self.kernel.certify(snapshot, horizon, collision_margin=0.35)
        return certify_actions(snapshot, horizon)

    def _last_viable_frontier(
        self,
        snapshot: Snapshot,
        minimum_horizon: int,
        maximum_horizon: int,
    ):
        if self.kernel is not None and hasattr(self.kernel, "last_viable_frontier"):
            return self.kernel.last_viable_frontier(
                snapshot,
                minimum_horizon,
                maximum_horizon,
                collision_margin=0.35,
            )
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            certified = self._certify(snapshot, horizon)
            if certified:
                return certified
        return ()

    def observe(self, survived: bool) -> None:
        self.ranker.observe(survived)

    def decide(self, snapshot: Snapshot, required_action: Action | None = None) -> Decision:
        if snapshot.in_menu:
            return Decision(None, (), 0.0, 0, "menu")
        if snapshot.replay_or_demo:
            return Decision(None, (), 0.0, 0, "replay-or-demo")
        if snapshot.time_stopped:
            return Decision(None, (), 0.0, 0, "time-stopped")
        if snapshot.player_state not in (PLAYER_ALIVE, PLAYER_INVULNERABLE):
            return Decision(None, (), 0.0, 0, "player-not-active")
        if not 0.99 <= snapshot.frame_multiplier <= 1.01:
            return Decision(None, (), 0.0, 0, "unsupported-frame-multiplier")
        if snapshot.laser_count != len(snapshot.lasers):
            return Decision(None, (), 0.0, 0, "unsupported-laser-decode")
        if any(
            not laser.motion_known
            and any(future_laser_hazards(laser, HARD_SAFETY_HORIZON))
            for laser in snapshot.lasers
        ):
            return Decision(None, (), 0.0, 0, "unsupported-laser-motion")
        if required_action is not None:
            # The full certificate was issued with the physical command.  On
            # the sole pending frame, recheck both possible next inputs
            # (current or leased) against newly observed hazards without
            # extending a constant-action requirement past acknowledgement.
            certified = self._certify(snapshot, 1)
            leased = next(
                (candidate for candidate in certified if candidate.action == required_action),
                None,
            )
            if leased is None:
                return Decision(
                    None,
                    certified,
                    0.0,
                    1,
                    "input-lease-unsafe",
                    1,
                )
            return Decision(
                leased.action,
                certified,
                leased.clearance,
                1,
                "ok",
                1,
            )
        effort_horizon = adaptive_horizon(snapshot)
        age_zero_certified = ()
        if (
            self.kernel is not None
            and hasattr(self.kernel, "certify_pair_with_age_zero")
            and effort_horizon > HARD_SAFETY_HORIZON
        ):
            certified, effort_certified, age_zero_certified = (
                self.kernel.certify_pair_with_age_zero(
                    snapshot,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                    collision_margin=0.35,
                )
            )
        elif (
            self.kernel is not None
            and hasattr(self.kernel, "certify_delivery_sets")
            and effort_horizon == HARD_SAFETY_HORIZON
        ):
            certified, age_zero_certified = self.kernel.certify_delivery_sets(
                snapshot,
                HARD_SAFETY_HORIZON,
                collision_margin=0.35,
            )
            effort_certified = certified
        elif self.kernel is not None and effort_horizon > HARD_SAFETY_HORIZON:
            certified, effort_certified = self.kernel.certify_pair(
                snapshot, HARD_SAFETY_HORIZON, effort_horizon, collision_margin=0.35
            )
        else:
            certified = self._certify(snapshot, HARD_SAFETY_HORIZON)
            effort_certified = (
                self._certify(snapshot, effort_horizon)
                if certified and effort_horizon > HARD_SAFETY_HORIZON
                else certified
            )
        if not certified:
            if self.kernel is None:
                age_zero_certified = certify_actions(
                    snapshot,
                    HARD_SAFETY_HORIZON,
                    DELIVERY_DELAYS[:-1],
                )
            if age_zero_certified:
                chosen = self.ranker.choose(snapshot, age_zero_certified)
                return Decision(
                    chosen.action,
                    age_zero_certified,
                    chosen.clearance,
                    HARD_SAFETY_HORIZON,
                    "same-frame-delivery-only",
                    HARD_SAFETY_HORIZON,
                )
            return Decision(
                None,
                (),
                0.0,
                HARD_SAFETY_HORIZON,
                "hard-safe-set-empty",
                effort_horizon,
            )
        durable = frozenset(
            candidate.action
            for candidate in effort_certified
        )
        laser_survivors = frozenset()
        if durable and snapshot.lasers and effort_horizon < LASER_EFFORT_HORIZON:
            laser_survivors = frozenset(
                candidate.action
                for candidate in self._certify(
                    isolate_lasers(snapshot),
                    LASER_EFFORT_HORIZON,
                )
            )
            refined_durable = durable & laser_survivors
            if refined_durable:
                durable = refined_durable
        repairable = frozenset()
        if not durable and effort_horizon >= 8:
            # Stage 4 entered a corner because the adaptive layer allocated 16
            # frames but the fallback repair proposal discarded everything
            # after frame 8.  Spend the existing soft budget; hard eligibility
            # remains the fixed four-frame set above.
            repair_horizon = effort_horizon
            scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    repair_horizon,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    repair_horizon,
                )
            )
            best_score = max(scores.values(), default=0)
            if best_score:
                repairable = frozenset(
                    action for action, score in scores.items() if score == best_score
                )
        if (
            not durable
            and not repairable
            and effort_horizon > HARD_SAFETY_HORIZON + 1
        ):
            # Physical Stage 4 branches exhausted the full constant-action
            # and two-segment proposals while one complete mixed-hazard action
            # still survived substantially longer than the boundary heuristic's
            # choice. Preserve the longest nonempty frontier for soft ranking.
            durable = frozenset(
                candidate.action
                for candidate in self._last_viable_frontier(
                    snapshot,
                    HARD_SAFETY_HORIZON + 1,
                    effort_horizon - 1,
                )
            )
        if (
            not durable
            and not repairable
            and snapshot.lasers
            and effort_horizon < LASER_EFFORT_HORIZON
        ):
            laser_survivors = frozenset(
                candidate.action
                for candidate in self._certify(
                    isolate_lasers(snapshot),
                    LASER_EFFORT_HORIZON,
                )
            )
            retained = retained_current_corridor(
                snapshot,
                frozenset(candidate.action for candidate in certified),
                laser_survivors,
            )
            if retained is not None:
                # Continuity only: do not steer into a new laser-only route
                # after the mixed proposal and its repair have both failed.
                durable = frozenset((retained,))
        chosen = self.ranker.choose(
            snapshot,
            certified,
            durable,
            repairable,
            repair_span=HARD_SAFETY_HORIZON,
        )
        return Decision(
            chosen.action,
            certified,
            chosen.clearance,
            HARD_SAFETY_HORIZON,
            "ok",
            effort_horizon,
            len(durable),
            len(repairable),
        )
