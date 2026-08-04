"""Hard/Reimu-A Stage 1, authored one source phase at a time."""

from __future__ import annotations

from ..model import Snapshot
from .base import RouteIntent, RouteKey
from .phase import boss_phase_id, ecl_subroutine_index
from .state_machine import PolicyState, TimelineStateMachine


BOTTOM_CENTER = (192.0, 380.0)
MOVEMENT_LEFT = 8.0
MOVEMENT_RIGHT = 376.0


def source_destination_alignment(snapshot: Snapshot, boss) -> tuple[float, float]:
    """Aim inside an h8 tie at the boss's captured source destination."""
    target_x = boss.x
    if boss.movement_mode == 2:
        target_x = boss.move_start_x + boss.move_interp_x
    return (
        min(max(target_x, MOVEMENT_LEFT), MOVEMENT_RIGHT),
        snapshot.y,
    )


def power_item_alignment(snapshot: Snapshot) -> tuple[float, float]:
    """Prefer live Power value during the source-defined nonlethal tail."""
    big_power = tuple(
        item for item in snapshot.item_states if item.item_type in (2, 4)
    )
    if big_power:
        item = min(big_power, key=lambda candidate: candidate.slot)
    else:
        small_power = tuple(
            item for item in snapshot.item_states if item.item_type == 0
        )
        if not small_power:
            return BOTTOM_CENTER
        item = min(
            small_power,
            key=lambda candidate: (
                (candidate.x - snapshot.x) ** 2
                + (candidate.y - snapshot.y) ** 2,
                candidate.slot,
            ),
        )
    return (
        min(max(item.x, MOVEMENT_LEFT), MOVEMENT_RIGHT),
        min(max(item.y, 16.0), 432.0),
    )


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
            "policy-volume",
            6,
            None,
            provenance=(
                "physical f1330 target-loop counterexample; installed "
                "random-x sub0/sub1 parents through t1400, with target-free "
                "h6 surviving all paired stateful delivery worlds"
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


POST_MIDBOSS_AIMED_STREAM = TimelineStateMachine(
    "timeline:t2408:subs2-3-post-midboss-aimed-stream",
    (
        PolicyState(
            2408,
            "aimed-stream-and-residual-tail",
            "policy-volume",
            8,
            None,
            provenance=(
                "physical f3827 post-midboss root; installed t2408-t4298 "
                "alternating sub2/sub3 aimed parents plus their residual "
                "children; complete 671-frame delivery sweeps and derived "
                "stateful battle worlds select target-free h8"
            ),
        ),
    ),
)


POST_MIDBOSS_RESOURCE_PHASE_ID = (
    "timeline:t4498:sub0-random-item-resource-formations"
)


PREBOSS_DIALOGUE = TimelineStateMachine(
    "timeline:t5278:preboss-dialogue",
    (
        PolicyState(
            5278,
            "message-zero-wait",
            "target-only",
            4,
            BOTTOM_CENTER,
            provenance=(
                "source t5278 MSGREAD(0) and t5279 MSGWAIT; installed message "
                "bytecode proves six earliest wait updates before ECLRESUME "
                "allows the same-update sub10 boss insertion; Ctrl/Z dialogue "
                "control remains independent of this movement proposal"
            ),
        ),
    ),
)


def post_midboss_resource_intent(snapshot: Snapshot) -> RouteIntent:
    return RouteIntent(
        phase_id=POST_MIDBOSS_RESOURCE_PHASE_ID,
        policy_state="power-item-collection",
        algorithm="policy-volume",
        horizon=8,
        target=power_item_alignment(snapshot),
        commitment_frames=4,
        provenance=(
            "physical f4637 resource root; installed t4498-t4978 life-3 "
            "sub0 parents drop random items and emit no Hard bullets; "
            "the f5060 body-collision counterexample requires fresh h8 "
            "continuation before item-distance tie-breaking; common Hard-4 "
            "remains unchanged"
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


def mainboss_intent(snapshot: Snapshot, boss) -> RouteIntent:
    spell_active = bool(
        snapshot.player_attack and snapshot.player_attack.spell_active
    )
    phase_id = boss_phase_id(boss, spell_active)
    subroutine = ecl_subroutine_index(boss)
    if subroutine == 10 and not spell_active:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="dialogue-gated-entry",
            algorithm="target-only",
            horizon=4,
            target=BOTTOM_CENTER,
            commitment_frames=4,
            provenance=(
                "physical f5286 sub10 root; source time-zero disables boss "
                "collision and damage, starts the 60-tick decelerating "
                "entry movement, and contains no hostile birth opcode; "
                "message 0 still proves 48 priority-9 waits before the "
                "timeline interrupt enters unaudited sub11"
            ),
        )
    if subroutine == 11 and not spell_active and boss.ecl_time <= 100:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="first-nonspell-entry",
            algorithm="count-clearance",
            horizon=8,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical f5350 sub11 root and f5629 promotion run; source "
                "installs life/timer callbacks 22, enables collision and "
                "damage, then calls sub12 at local t100; stateful delivery "
                "sweeps select terminal-count then clearance at h8"
            ),
        )
    if subroutine == 12 and not spell_active and boss.ecl_time < 180:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="first-nonspell-aimed-fans",
            algorithm="count-clearance",
            horizon=8,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical f5629 run crossed all seven sub12 local t12-t60 "
                "Hard aimed fans (130 births); exact candidate-conditioned "
                "sweeps and adjacent parity cover player attack, boss "
                "damage, ECL movement, RNG, and delivery through t179"
            ),
        )
    if subroutine == 14 and not spell_active and boss.ecl_time < 200:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="first-nonspell-hard-fan-circle",
            algorithm="constant-frontier",
            horizon=10,
            target=None,
            commitment_frames=4,
            provenance=(
                "physical f5629 sub14 root; source moves at time zero, "
                "emits the Hard t80 aimed 5x16 fan and t110 aimed 24x2 "
                "circle, then branches at t200; exact and warmup-derived "
                "battle worlds select a target-free constant h10 reserve"
            ),
        )
    return uncovered(
        phase_id,
        "Stage 1 main-boss source state after the dialogue-gated sub10 "
        "entry has not been authored",
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
            target=source_destination_alignment(snapshot, boss),
            commitment_frames=4,
            provenance=(
                "physical local-t160 root; complete candidate-conditioned "
                "battle sweeps cover the Hard 16x5 aimed circle and the "
                "following source movement through local t413; equal h8 "
                "continuations align to the captured destination"
            ),
        )
    if is_sub8_nonspell and boss.ecl_time < 738:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="paired-circles-movement",
            algorithm="policy-volume",
            horizon=8,
            target=source_destination_alignment(snapshot, boss),
            commitment_frames=4,
            provenance=(
                "physical local-t414 root; complete candidate-conditioned "
                "battle sweeps cover the local-t414/t444 Hard aimed "
                "circles and the t526 movement through local t737; equal "
                "h8 continuations align to the captured destination"
            ),
        )
    if is_sub8_nonspell and boss.ecl_time <= 840:
        return RouteIntent(
            phase_id=phase_id,
            policy_state="late-circles-loop",
            algorithm="policy-volume",
            horizon=8,
            target=source_destination_alignment(snapshot, boss),
            commitment_frames=4,
            provenance=(
                "physical local-t738 root; candidate-conditioned sweeps "
                "cover the t738/t768 Hard circles and the source t840 "
                "jump back to local t193 while equal h8 continuations "
                "align to the captured destination"
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
        if boss.ecl_time == 331:
            return RouteIntent(
                phase_id=phase_id,
                policy_state="cycle-rewind",
                algorithm="policy-volume",
                horizon=4,
                target=None,
                commitment_frames=1,
                provenance=(
                    "physical local-t331 root; source opcode 2 rewinds to "
                    "t120 and recreates the audited pattern/laser cycle"
                ),
            )
        return uncovered(
            phase_id,
            "Stage 1 sub9 spell reached an ECL clock beyond the source "
            "t331 cycle rewind",
        )
    if (
        ecl_subroutine_index(boss) == 6
        and spell_active
        and boss.ecl_time == 0
    ):
        return RouteIntent(
            phase_id=phase_id,
            policy_state="spell-end-conversion",
            algorithm="target-only",
            horizon=4,
            target=BOTTOM_CENTER,
            commitment_frames=1,
            provenance=(
                "physical f3499 post-death-callback root; source opcode 94 "
                "converts every occupied bullet and both active lasers "
                "before their same-update manager pass"
            ),
        )
    if (
        ecl_subroutine_index(boss) == 6
        and not spell_active
        and 1 <= boss.ecl_time < 160
    ):
        return RouteIntent(
            phase_id=phase_id,
            policy_state="power-collection-tail",
            algorithm="target-only",
            horizon=4,
            target=power_item_alignment(snapshot),
            commitment_frames=4,
            provenance=(
                "physical f3980 SpellEnd root; source sub6 has no hostile "
                "births before the t40 exit movement; exact delivery "
                "branches collect the live Big Power and at least one "
                "Small Power before source out-of-bounds despawn, while "
                "common Hard-4 remains unchanged"
            ),
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
            if snapshot.timeline_time >= 5280:
                return mainboss_intent(snapshot, boss)
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
        if snapshot.timeline_time < 2408:
            return uncovered(
                "timeline:t2009:sub8-midboss-missing",
                "sub8 should have published stable boss ECL state after its "
                "t2008 timeline insertion",
            )
        if snapshot.timeline_time < 4498:
            return POST_MIDBOSS_AIMED_STREAM.intent(snapshot)
        if snapshot.timeline_time < 5278:
            return post_midboss_resource_intent(snapshot)
        if snapshot.timeline_time < 5280:
            return PREBOSS_DIALOGUE.intent(snapshot)
        return uncovered(
            "timeline:t5280:sub10-main-boss-missing",
            "sub10 should have published stable boss ECL state after the "
            "t5279 dialogue-gated timeline insertion",
        )
