"""Compose adaptive horizon, hard authority, and proposal ranking."""

from __future__ import annotations

import os

from .kernels.safety import NativeSafetyKernel
from .model import Action, Decision, PLAYER_ALIVE, PLAYER_INVULNERABLE, Snapshot
from .ranking import ProposalRanker
from .safety import certify_actions, nearest_current_clearance


# Physical runs currently bound a hazardous-state decision interval to three
# native frames and input pickup to two more.  Longer 8/12/16-frame rollouts
# allocate ranking effort; they must not turn constant-action rollout into a
# hard eligibility requirement.
HARD_SAFETY_HORIZON = 5


def adaptive_horizon(snapshot: Snapshot) -> int:
    if snapshot.lasers or snapshot.enemies:
        return 16
    nearest = nearest_current_clearance(snapshot)
    if nearest < 48.0 or len(snapshot.bullets) >= 220:
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
        certified = self._certify(snapshot, HARD_SAFETY_HORIZON)
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
            for candidate in self._certify(snapshot, effort_horizon)
        ) if effort_horizon > HARD_SAFETY_HORIZON else frozenset(
            candidate.action for candidate in certified
        )
        chosen = self.ranker.choose(snapshot, certified, durable)
        return Decision(
            chosen.action,
            certified,
            chosen.clearance,
            HARD_SAFETY_HORIZON,
            "ok",
            effort_horizon,
            len(durable),
        )
