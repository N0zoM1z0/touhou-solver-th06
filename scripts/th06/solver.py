"""Compose adaptive horizon, hard authority, and proposal ranking."""

from __future__ import annotations

import os

from .kernels.safety import NativeSafetyKernel
from .model import Action, Decision, PLAYER_ALIVE, PLAYER_INVULNERABLE, Snapshot
from .ranking import ProposalRanker
from .safety import certify_actions, nearest_current_clearance
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
    if len(snapshot.bullets) >= 220:
        return 8
    if snapshot.lasers or snapshot.enemies:
        return 16
    nearest = nearest_current_clearance(snapshot)
    if nearest < 48.0:
        return 16
    if nearest < 120.0 or len(snapshot.bullets) >= 100:
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
        if self.kernel is not None and effort_horizon > HARD_SAFETY_HORIZON:
            certified, effort_certified = self.kernel.certify_pair(
                snapshot,
                HARD_SAFETY_HORIZON,
                effort_horizon,
                collision_margin=0.35,
            )
        else:
            certified = self._certify(snapshot, HARD_SAFETY_HORIZON)
            effort_certified = (
                self._certify(snapshot, effort_horizon)
                if certified and effort_horizon > HARD_SAFETY_HORIZON
                else certified
            )
        if not certified:
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
        repairable = frozenset()
        if not durable and effort_horizon >= 8:
            repair_horizon = 8
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
