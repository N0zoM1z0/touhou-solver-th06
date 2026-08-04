"""Hard/Reimu-A Stage 1, authored one source phase at a time.

The quiet setup and source phases through the t1600 body/resource stream are
covered. At t2008 only the one-frame source insertion bridge is authored; the
newborn sub8 boss phase remains deliberately fail-visible.
"""

from __future__ import annotations

from ..model import Snapshot
from .base import RouteIntent, RouteKey
from .phase import boss_phase_id, ecl_subroutine_index
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


AIMED_STREAM = TimelineStateMachine(
    "timeline:t640:subs2-3-aimed-stream",
    (
        PolicyState(
            640,
            "aimed-stream-entry",
            "policy-volume",
            8,
            None,
            provenance=(
                "physical f641 entry; sub2 fires the Hard 9x2 aimed fan "
                "at local ECL t70"
            ),
        ),
        PolicyState(
            1080,
            "compressed-sub2-tail",
            "policy-volume",
            8,
            None,
            provenance=(
                "installed t1080/t1100/t1110 sub2 tail fires at "
                "t1150/t1170/t1180"
            ),
        ),
    ),
)


RANDOM_BODY_STREAM = TimelineStateMachine(
    "timeline:t1220:random-subs0-1-body-stream",
    (
        PolicyState(
            1220,
            "random-insertion",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance=(
                "physical f1220 entry; installed random-x sub0/sub1 "
                "parents through t1400"
            ),
        ),
        PolicyState(
            1401,
            "tail",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="last random-coordinate parent spawned at source t1400",
        ),
    ),
)


SECOND_BODY_STREAM = TimelineStateMachine(
    "timeline:t1600:sub0-body-resource-stream",
    (
        PolicyState(
            1600,
            "mirrored-formations",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance=(
                "physical f1600 entry; installed mirrored sub0 parents "
                "through t1808 carry item 3 and emit no Hard bullets"
            ),
        ),
        PolicyState(
            1809,
            "tail",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance="last mirrored sub0 parent spawned at source t1808",
        ),
    ),
)


MIDBOSS_INSERTION = TimelineStateMachine(
    "timeline:t2008:sub8-midboss-entry",
    (
        PolicyState(
            2008,
            "timeline-insertion",
            "target-only",
            4,
            BOTTOM_CENTER,
            commitment_frames=1,
            provenance=(
                "physical f2008 boundary before RunEclTimeline creates "
                "sub8; common source future already contains the boss body"
            ),
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


def midboss_intent(snapshot: Snapshot, boss) -> RouteIntent:
    spell_active = bool(
        snapshot.player_attack and snapshot.player_attack.spell_active
    )
    phase_id = boss_phase_id(
        boss,
        spell_active,
    )
    is_sub8_nonspell = (
        ecl_subroutine_index(boss) == 8
        and not spell_active
    )
    if is_sub8_nonspell and boss.ecl_time < 160:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="entry-movement",
            algorithm="target-only",
            horizon=4,
            target=BOTTOM_CENTER,
            commitment_frames=4,
            provenance=(
                "physical f2009 sub8 root; local t60 enables interaction "
                "and the first Hard aimed circle is local t160"
            ),
        )
    if is_sub8_nonspell and boss.ecl_time < 414:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="first-circle-movement",
            algorithm="policy-volume",
            horizon=8,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical local-t160 root; complete candidate-conditioned "
                "battle sweeps cover the Hard 16x5 aimed circle and the "
                "following source movement through local t413"
            ),
        )
    if is_sub8_nonspell and boss.ecl_time < 738:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="paired-circles-movement",
            algorithm="policy-volume",
            horizon=8,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical local-t414 root; complete candidate-conditioned "
                "battle sweeps cover the local-t414/t444 Hard aimed "
                "circles and the t526 movement through local t737"
            ),
        )
    if is_sub8_nonspell and boss.ecl_time <= 840:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="late-circles-loop",
            algorithm="policy-volume",
            horizon=8,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical local-t738 root; candidate-conditioned sweeps "
                "cover the t738/t768 Hard circles and the source t840 "
                "jump back to local t193"
            ),
        )
    if ecl_subroutine_index(boss) == 9 and spell_active:
        if boss.ecl_time < 120:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="spell-entry",
                algorithm="target-only",
                horizon=4,
                target=BOTTOM_CENTER,
                commitment_frames=4,
                provenance=(
                    "physical f3044 sub9 spell root; source entry cancels "
                    "old bullets, disables damage, and moves for 120 ticks "
                    "before creating its Hard pattern and two lasers"
                ),
            )
        if boss.ecl_time < 150:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="laser-pattern-start",
                algorithm="target-only",
                horizon=4,
                target=BOTTOM_CENTER,
                commitment_frames=4,
                provenance=(
                    "physical local-t120 root; exact source stepping covers "
                    "the Hard delayed 42-way birth and laser slots 0/1 "
                    "through local t149"
                ),
            )
        if boss.ecl_time < 152:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="rotating-laser-loop",
                algorithm="policy-volume",
                horizon=6,
                target=None,
                commitment_frames=4,
                provenance=(
                    "physical local-t150 root; source int4 counts the "
                    "opposed opcode-88 laser rotations from 120 to zero"
                ),
            )
        if boss.ecl_time < 211:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="laser-retirement-tail",
                algorithm="policy-volume",
                horizon=6,
                target=None,
                commitment_frames=4,
                provenance=(
                    "same exact local-t150 battle sweep; both source lasers "
                    "retire after the t151 loop and ECL advances to t210"
                ),
            )
        if boss.ecl_time < 331:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="random-movement",
                algorithm="policy-volume",
                horizon=6,
                target=None,
                commitment_frames=4,
                provenance=(
                    "physical local-t211 root; source random-in-bounds "
                    "heading and 120-tick movement lead to the t331 rewind"
                ),
            )
        return uncovered(
            phase_id,
            "Stage 1 sub9 spell at or after the local-t331 cycle rewind "
            "transition has not been authored",
        )
    return uncovered(
        phase_id,
        "Stage 1 midboss source state outside the audited sub8 control "
        "cycle has not been authored",
    )


class HardReimuAStage1:
    key = RouteKey(difficulty=2, character=0, shot_type=0, stage=1)
    route_id = "hard-reimu-a-stage1"

    def intent(self, snapshot: Snapshot) -> RouteIntent | None:
        bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
        if bosses:
            boss = min(bosses, key=lambda spawner: (spawner.boss_id, spawner.slot))
            return midboss_intent(snapshot, boss)

        if snapshot.timeline_time < 128:
            return SETUP.intent(snapshot)
        if snapshot.timeline_time < 640:
            return FIRST_BODY_STREAM.intent(snapshot)
        if snapshot.timeline_time < 1220:
            return AIMED_STREAM.intent(snapshot)
        if snapshot.timeline_time < 1600:
            return RANDOM_BODY_STREAM.intent(snapshot)
        if snapshot.timeline_time < 2008:
            return SECOND_BODY_STREAM.intent(snapshot)
        if snapshot.timeline_time < 2009:
            return MIDBOSS_INSERTION.intent(snapshot)
        return uncovered(
            "timeline:t2009:sub8-midboss-missing",
            "sub8 should have published stable boss ECL state after its "
            "t2008 timeline insertion",
        )
