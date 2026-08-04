"""Hard/Reimu-A Stage 1, authored one source phase at a time.

Only the quiet setup and the installed t128 sub0/sub1 body stream are covered.
The t640 sub2/sub3 aimed-wave transition is deliberately fail-visible until
its own policy has physical entry evidence.
"""

from __future__ import annotations

from ..model import Snapshot
from .base import RouteIntent, RouteKey
from .phase import boss_phase_id
from .state_machine import PolicyState, TimelineStateMachine


BOTTOM_CENTER = (192.0, 380.0)


SETUP = TimelineStateMachine(
    "timeline:t0:setup",
    (
        PolicyState(
            0,
            "staging",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="quiet source entry before the first t128 spawn",
        ),
    ),
)


FIRST_BODY_STREAM = TimelineStateMachine(
    "timeline:t128:subs0-1-body-stream",
    (
        PolicyState(
            128,
            "sub0-left-stream",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="installed t128-t368 sub0 body/resource stream",
        ),
        PolicyState(
            432,
            "sub1-mirrored-stream",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="installed t432-t576 mirrored sub1 body/resource stream",
        ),
        PolicyState(
            577,
            "tail",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="last sub1 parent spawned at source t576",
        ),
    ),
)


def uncovered(phase_id: str, provenance: str) -> RouteIntent:
    return RouteIntent(
        phase_id=phase_id,
        policy_state="uncovered",
        algorithm="uncovered",
        horizon=4,
        target=None,
        commitment_frames=1,
        provenance=provenance,
    )


class HardReimuAStage1:
    key = RouteKey(difficulty=2, character=0, shot_type=0, stage=1)
    route_id = "hard-reimu-a-stage1"

    def intent(self, snapshot: Snapshot) -> RouteIntent | None:
        bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
        if bosses:
            boss = min(bosses, key=lambda spawner: (spawner.boss_id, spawner.slot))
            return uncovered(
                boss_phase_id(
                    boss,
                    bool(
                        snapshot.player_attack
                        and snapshot.player_attack.spell_active
                    ),
                ),
                "Stage 1 boss ECL phase has not been authored",
            )

        if snapshot.timeline_time < 128:
            return SETUP.intent(snapshot)
        if snapshot.timeline_time < 640:
            return FIRST_BODY_STREAM.intent(snapshot)
        return uncovered(
            "timeline:t640:subs2-3-aimed-stream",
            "next installed source phase begins with sub2 at t640; "
            "its Hard 9x2 aimed fan fires at local ECL t70",
        )
