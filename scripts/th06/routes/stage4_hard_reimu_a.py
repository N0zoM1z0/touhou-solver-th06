"""Hard/Reimu-A Stage 4 route pilot.

The timeline section starts below were audited from the installed
``ecldata4.ecl``.  They are source timeline times at natural spawn gaps, not
game-frame counterexamples.  This first policy intentionally keeps the route
data small: each section chooses a bounded local primitive and a soft staging
point.  Physical iteration will replace individual entries with compiled
state-conditioned policies as each phase is reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Snapshot
from .base import RouteIntent, RouteKey
from .phase import boss_phase_id


@dataclass(frozen=True)
class TimelinePhase:
    start: int
    phase_id: str
    horizon: int
    target: tuple[float, float]


# Source event groups from the installed Stage 4 timeline.  The names retain
# the source time and spawned sub IDs so an entry can be re-audited without a
# spell-name database.  The t2388 and t2712 groups bracket the dense crossing
# waves seen in the current physical Stage 4 workload.
TIMELINE_PHASES = (
    TimelinePhase(0, "timeline:t0:setup", 8, (192.0, 380.0)),
    TimelinePhase(440, "timeline:t440:sub0", 8, (192.0, 380.0)),
    # The first post-pivot physical run measured h12 at 16.76 ms median and
    # 27.72 ms maximum in this section, with 17 stale publications before its
    # f1329 stop.  Stateful replay on the retained f1290--f1327 battle roots
    # kept h8 alive while publishing the missed downward f1320 correction.
    TimelinePhase(1004, "timeline:t1004:subs2-3", 8, (192.0, 380.0)),
    # The next physical run crossed t1004 with zero stale results, then
    # measured this h12 section at 19.79 ms median with 10 stale publications
    # and 18 timeouts before f1615.  Retained battle roots keep h8 alive for
    # 32 frames with 2.64 mean commands versus h12's 4.50.
    TimelinePhase(1514, "timeline:t1514:sub10", 8, (192.0, 380.0)),
    TimelinePhase(1878, "timeline:t1878:subs3-2", 12, (192.0, 380.0)),
    TimelinePhase(2388, "timeline:t2388:subs11-13", 16, (192.0, 380.0)),
    TimelinePhase(2712, "timeline:t2712:subs5-4-3", 12, (192.0, 380.0)),
    TimelinePhase(3452, "timeline:t3452:sub14", 12, (192.0, 380.0)),
    TimelinePhase(4132, "timeline:t4132:sub21", 16, (192.0, 380.0)),
    TimelinePhase(4932, "timeline:t4932:sub6-a", 12, (192.0, 380.0)),
    TimelinePhase(5212, "timeline:t5212:sub6-b", 12, (192.0, 380.0)),
    TimelinePhase(5492, "timeline:t5492:sub7", 12, (192.0, 380.0)),
    TimelinePhase(5772, "timeline:t5772:subs3-16-18", 16, (192.0, 380.0)),
    TimelinePhase(6586, "timeline:t6586:subs16-18-7", 16, (192.0, 380.0)),
    TimelinePhase(7494, "timeline:t7494:subs11-17", 12, (192.0, 380.0)),
    TimelinePhase(7644, "timeline:t7644:subs3-11-17", 16, (192.0, 380.0)),
    TimelinePhase(8044, "timeline:t8044:sub3", 12, (192.0, 380.0)),
    TimelinePhase(8414, "timeline:t8414:subs8-9", 16, (192.0, 380.0)),
    TimelinePhase(9844, "timeline:t9844:subs11-9", 16, (192.0, 380.0)),
    TimelinePhase(10694, "timeline:t10694:boss-entry", 8, (192.0, 380.0)),
)


def timeline_phase(timeline_time: int) -> TimelinePhase:
    return max(
        (phase for phase in TIMELINE_PHASES if phase.start <= timeline_time),
        key=lambda phase: phase.start,
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
            # Boss policy is deliberately exposed as uncovered until its ECL
            # phases are audited and authored.  Falling back to an anonymous
            # universal planner here would hide route work that remains.
            return RouteIntent(
                phase_id=phase_id,
                algorithm="uncovered",
                horizon=4,
                target=None,
                commitment_frames=1,
                provenance="boss ECL phase has not been authored",
            )

        phase = timeline_phase(snapshot.timeline_time)
        return RouteIntent(
            phase_id=phase.phase_id,
            algorithm="policy-volume",
            horizon=phase.horizon,
            target=phase.target,
            commitment_frames=4,
            provenance="installed ecldata4.ecl timeline event groups",
        )
