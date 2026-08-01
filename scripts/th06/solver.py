"""Compose adaptive horizon, hard authority, and proposal ranking."""

from __future__ import annotations

from .model import Decision, PLAYER_ALIVE, PLAYER_INVULNERABLE, Snapshot
from .ranking import ProposalRanker
from .safety import certify_actions, nearest_current_clearance


def adaptive_horizon(snapshot: Snapshot) -> int:
    nearest = nearest_current_clearance(snapshot)
    if nearest < 48.0 or len(snapshot.bullets) >= 220:
        return 16
    if nearest < 120.0 or len(snapshot.bullets) >= 100:
        return 12
    return 8


class Solver:
    def __init__(self, ranker: ProposalRanker | None = None) -> None:
        self.ranker = ranker or ProposalRanker()

    def observe(self, survived: bool) -> None:
        self.ranker.observe(survived)

    def decide(self, snapshot: Snapshot) -> Decision:
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
        if snapshot.laser_count:
            return Decision(None, (), 0.0, 0, "unsupported-active-laser")
        horizon = adaptive_horizon(snapshot)
        certified = certify_actions(snapshot, horizon)
        if not certified:
            return Decision(None, (), 0.0, horizon, "hard-safe-set-empty")
        chosen = self.ranker.choose(snapshot, certified)
        return Decision(chosen.action, certified, chosen.clearance, horizon, "ok")
