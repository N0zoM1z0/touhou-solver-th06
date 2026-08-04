"""Hard/Reimu-A Stage 4 route pilot.

The route is a table of isolated source-phase state machines.  Their state
boundaries come from installed timeline spawns and the ECL-local delay before
the relevant child/shoot instruction.  The table deliberately contains no
global bullet-count or wall-position classifier: only the selected source
phase runs, and each state names the local primitive it owns.
"""

from __future__ import annotations

from ..model import Snapshot
from .base import RouteIntent, RouteKey
from .phase import boss_phase_id
from .state_machine import PolicyState, TimelineStateMachine


BOTTOM_CENTER = (192.0, 380.0)


def state(
    start_time: int,
    state_id: str,
    horizon: int,
    provenance: str,
) -> PolicyState:
    return PolicyState(
        start_time=start_time,
        state_id=state_id,
        algorithm="policy-volume",
        horizon=horizon,
        target=BOTTOM_CENTER,
        provenance=provenance,
    )


def phase(phase_id: str, *states: PolicyState) -> TimelineStateMachine:
    return TimelineStateMachine(phase_id, tuple(states))


# Source event groups from installed ecldata4.ecl.  Sub-state boundaries are
# source events, not captured failure frames.  Historical frames only select
# the local primitive/horizon after the source phase has already been fixed.
TIMELINE_PHASES = (
    phase(
        "timeline:t0:setup",
        state(0, "staging", 8, "quiet route entry"),
    ),
    phase(
        "timeline:t440:sub0",
        state(440, "parent-entry", 8, "timeline sub0 parents"),
        # sub0 reaches ENEMYCREATE sub1 at local ECL t70.
        state(510, "child-circle", 8, "sub0 child sub1 at local t70"),
        state(575, "tail", 8, "last t504 parent child emitted by t574"),
    ),
    phase(
        "timeline:t1004:subs2-3",
        # Subs 2/3 set and shoot their aimed fans at ECL t0.
        state(
            1004,
            "aimed-stream",
            8,
            "physical t1004 h8 crossed the old f1329 publication boundary",
        ),
        state(1365, "tail", 8, "last immediate fan spawned at t1364"),
    ),
    phase(
        "timeline:t1514:sub10",
        state(1514, "parent-entry", 8, "timeline sub10 parents"),
        # sub10 creates sub1 at local ECL t70; the current f1615 boundary is
        # therefore inside this state rather than an anonymous multi-enemy
        # scene.  The historical clear solver also recorded multi-enemy cost
        # trouble near f1565.
        state(
            1584,
            "child-circle",
            8,
            "sub10 child sub1 at local t70; physical f1615 h12 timed out",
        ),
        state(1649, "tail", 8, "last t1578 parent child emitted by t1648"),
    ),
    phase(
        "timeline:t1878:subs3-2",
        state(1878, "aimed-stream", 12, "subs3/2 immediate aimed fans"),
        state(2239, "tail", 8, "last immediate fan spawned at t2238"),
    ),
    phase(
        "timeline:t2388:subs11-13",
        state(2388, "formation", 8, "subs11/13 shoot at local ECL t70"),
        # Old physical CEs f2625/f2652/f2663/f2665/f2668/f2709 all belong to
        # this exact pre-midboss source phase.  The Stage 4 clear used the
        # bounded h6 primitive here once the horizontal bands matured; making
        # that phase ownership explicit removes the old >=400-bullet branch.
        state(
            2458,
            "horizontal-band",
            6,
            "historical Stage 4 horizontal-band h6 publication/escape CEs",
        ),
    ),
    phase(
        "timeline:t2712:subs5-4-3",
        # Historical f2760/f2912 are in this immediate aimed-fan group and
        # likewise needed the bounded dense h6 rung without paying for it in
        # unrelated phases.
        state(
            2712,
            "dense-aimed-stream",
            6,
            "historical Stage 4 f2760/f2912 bounded dense rung",
        ),
        state(3263, "tail", 8, "last immediate fan spawned at t3262"),
    ),
    phase(
        "timeline:t3452:sub14",
        state(3452, "formation", 8, "sub14 shoots at local ECL t30"),
        # f4091 measured an unnecessary h8 pass at 392 bullets, but also
        # showed this source group needs a bounded continuation rather than a
        # target-only rule.  h8 is retained and isolated to the group.
        state(
            3482,
            "dense-radial",
            8,
            "historical Stage 4 f4091 dense publication evidence",
        ),
        state(3723, "tail", 8, "last t3692 spawn fires by t3722"),
    ),
    phase(
        "timeline:t4132:sub21",
        state(4132, "midboss-entry", 12, "source midboss spawn/interrupt"),
    ),
    phase(
        "timeline:t4932:sub6-a",
        state(4932, "formation-a", 12, "installed t4932 sub6 group"),
    ),
    phase(
        "timeline:t5212:sub6-b",
        state(5212, "formation-b", 12, "installed t5212 sub6 group"),
    ),
    phase(
        "timeline:t5492:sub7",
        state(5492, "formation", 12, "installed t5492 sub7 group"),
    ),
    phase(
        "timeline:t5772:subs3-16-18",
        state(5772, "mixed-entry", 16, "installed subs3/16/18 group"),
    ),
    phase(
        "timeline:t6586:subs16-18-7",
        state(6586, "mixed-entry", 16, "installed subs16/18/7 group"),
    ),
    phase(
        "timeline:t7494:subs11-17",
        state(7494, "delayed-circle", 12, "subs11/17 delayed source shots"),
    ),
    phase(
        "timeline:t7644:subs3-11-17",
        state(7644, "mixed-stream", 16, "installed subs3/11/17 group"),
    ),
    phase(
        "timeline:t8044:sub3",
        state(8044, "aimed-stream", 12, "sub3 immediate aimed fans"),
    ),
    phase(
        "timeline:t8414:subs8-9",
        state(8414, "dense-aimed-stream", 16, "96 installed subs8/9 spawns"),
    ),
    phase(
        "timeline:t9844:subs11-9",
        state(9844, "mixed-stream", 16, "53 installed subs11/9 spawns"),
    ),
    phase(
        "timeline:t10694:boss-entry",
        state(10694, "dialogue-entry", 8, "source message/boss entry"),
    ),
)


def timeline_phase(timeline_time: int) -> TimelineStateMachine:
    return max(
        (machine for machine in TIMELINE_PHASES if machine.start_time <= timeline_time),
        key=lambda machine: machine.start_time,
    )


class HardReimuAStage4:
    key = RouteKey(difficulty=2, character=0, shot_type=0, stage=4)
    route_id = "hard-reimu-a-stage4"

    def intent(self, snapshot: Snapshot) -> RouteIntent | None:
        bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
        if bosses:
            boss = min(bosses, key=lambda spawner: (spawner.boss_id, spawner.slot))
            phase_id = boss_phase_id(
                boss,
                bool(snapshot.player_attack and snapshot.player_attack.spell_active),
            )
            return RouteIntent(
                phase_id=phase_id,
                policy_state="uncovered",
                algorithm="uncovered",
                horizon=4,
                target=None,
                commitment_frames=1,
                provenance="boss ECL phase has not been authored",
            )

        return timeline_phase(snapshot.timeline_time).intent(snapshot)
