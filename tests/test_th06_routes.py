import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from th06.barrage_lab.assets import load_stage_timeline
from th06.model import BUTTON_FOCUS, ItemState, PlayerAttackState, Snapshot
from th06.routes.phase import boss_phase_id, ecl_subroutine_index
from th06.routes.registry import default_routes, snapshot_route_key
from th06.routes.stage1_hard_reimu_a import (
    AIMED_STREAM,
    FIRST_BODY_STREAM,
    HardReimuAStage1,
    MIDBOSS_INSERTION,
    POST_MIDBOSS_AIMED_STREAM,
    RANDOM_BODY_STREAM,
    SECOND_BODY_STREAM,
)
from th06.routes.stage4_hard_reimu_a import (
    HardReimuAStage4,
    TIMELINE_PHASES,
    timeline_phase,
)
from th06.routes.state_machine import PolicyState, TimelineStateMachine
from th06.solver import Solver


def player_attack(shot_type=0):
    return PlayerAttackState(
        shots=(),
        last_enemy_hit_x=0.0,
        last_enemy_hit_y=0.0,
        orb_state=0,
        is_focus=True,
        focus_timer_previous=0,
        focus_timer=0,
        focus_timer_float=0.0,
        fire_timer_previous=0,
        fire_timer=0,
        fire_timer_float=0.0,
        orb_positions=((0.0, 0.0), (0.0, 0.0)),
        shot_type=shot_type,
        bomb_active=False,
        spell_active=False,
    )


def snapshot(**changes):
    values = dict(
        frame=100,
        stage=4,
        player_state=0,
        x=192.0,
        y=380.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.828427,
        focus_diagonal_speed=1.414214,
        frame_multiplier=1.0,
        input_mask=BUTTON_FOCUS,
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
        difficulty=2,
        character=0,
        player_attack=player_attack(),
        timeline_complete=True,
    )
    values.update(changes)
    return Snapshot(**values)


class RoutePhaseTests(unittest.TestCase):
    @unittest.skipUnless(
        Path("reference/th06_dat/th06_ST.DAT").exists(),
        "installed source stage archive is ignored",
    )
    def test_stage1_first_phase_boundaries_exist_in_installed_ecl(self):
        timeline = load_stage_timeline(
            "reference/th06_dat/th06_ST.DAT", 1
        )
        source_times = {instruction.time for instruction in timeline}

        self.assertEqual(len(timeline), 231)
        self.assertTrue(
            {128, 432, 576, 640, 1220, 1400, 1600, 1808, 2008}
            <= source_times
        )

    @unittest.skipUnless(
        Path("reference/th06_dat/th06_ST.DAT").exists(),
        "installed source stage archive is ignored",
    )
    def test_stage4_manifest_boundaries_exist_in_installed_ecl(self):
        timeline = load_stage_timeline(
            "reference/th06_dat/th06_ST.DAT", 4
        )
        source_times = {instruction.time for instruction in timeline}
        self.assertTrue(
            {
                machine.start_time
                for machine in TIMELINE_PHASES
                if machine.start_time
            }
            <= source_times
        )
        self.assertEqual(len(timeline), 404)

    def test_route_key_includes_difficulty_character_shot_and_stage(self):
        state = snapshot()
        self.assertEqual(
            snapshot_route_key(state),
            HardReimuAStage4.key,
        )
        self.assertIsNotNone(default_routes().resolve(state))
        self.assertIsNone(default_routes().resolve(replace(
            state, player_attack=player_attack(shot_type=1)
        )))

    def test_stage1_authored_phases_bridge_only_into_t2008_midboss(self):
        pack = HardReimuAStage1()

        setup = pack.intent(snapshot(stage=1, timeline_time=127))
        first = pack.intent(snapshot(stage=1, timeline_time=128))
        mirrored = pack.intent(snapshot(stage=1, timeline_time=432))
        tail = pack.intent(snapshot(stage=1, timeline_time=639))
        aimed = pack.intent(snapshot(stage=1, timeline_time=640))
        dense_tail = pack.intent(snapshot(stage=1, timeline_time=1080))
        random_stream = pack.intent(snapshot(stage=1, timeline_time=1220))
        random_tail = pack.intent(snapshot(stage=1, timeline_time=1401))
        second_stream = pack.intent(snapshot(stage=1, timeline_time=1600))
        second_tail = pack.intent(snapshot(stage=1, timeline_time=1809))
        insertion = pack.intent(snapshot(stage=1, timeline_time=2008))
        next_phase = pack.intent(snapshot(stage=1, timeline_time=2009))

        self.assertEqual(setup.phase_id, "timeline:t0:setup")
        self.assertEqual(first.phase_id, FIRST_BODY_STREAM.phase_id)
        self.assertEqual(first.policy_state, "sub0-left-stream")
        self.assertEqual(first.algorithm, "target-only")
        self.assertEqual(mirrored.policy_state, "sub1-mirrored-stream")
        self.assertEqual(tail.policy_state, "tail")
        self.assertEqual(aimed.phase_id, AIMED_STREAM.phase_id)
        self.assertEqual(aimed.policy_state, "aimed-stream-entry")
        self.assertEqual(aimed.algorithm, "policy-volume")
        self.assertEqual(aimed.horizon, 8)
        self.assertIsNone(aimed.target)
        self.assertEqual(dense_tail.policy_state, "compressed-sub2-tail")
        self.assertEqual(random_stream.phase_id, RANDOM_BODY_STREAM.phase_id)
        self.assertEqual(random_stream.policy_state, "random-insertion")
        self.assertEqual(random_stream.algorithm, "policy-volume")
        self.assertEqual(random_stream.horizon, 6)
        self.assertIsNone(random_stream.target)
        self.assertEqual(random_tail.policy_state, "tail")
        self.assertEqual(second_stream.phase_id, SECOND_BODY_STREAM.phase_id)
        self.assertEqual(second_stream.policy_state, "mirrored-formations")
        self.assertEqual(second_stream.algorithm, "target-only")
        self.assertEqual(second_stream.horizon, 4)
        self.assertIsNotNone(second_stream.target)
        self.assertEqual(second_tail.policy_state, "tail")
        self.assertEqual(insertion.phase_id, MIDBOSS_INSERTION.phase_id)
        self.assertEqual(insertion.policy_state, "timeline-insertion")
        self.assertEqual(insertion.algorithm, "target-only")
        self.assertEqual(insertion.commitment_frames, 1)
        self.assertEqual(next_phase.algorithm, "uncovered")
        self.assertEqual(
            next_phase.phase_id,
            "timeline:t2009:sub8-midboss-missing",
        )

        post_midboss = pack.intent(snapshot(stage=1, timeline_time=3827))
        residual_tail = pack.intent(snapshot(stage=1, timeline_time=4497))
        next_resource = pack.intent(snapshot(stage=1, timeline_time=4498))
        self.assertEqual(post_midboss.phase_id, POST_MIDBOSS_AIMED_STREAM.phase_id)
        self.assertEqual(
            post_midboss.policy_state,
            "aimed-stream-and-residual-tail",
        )
        self.assertEqual(post_midboss.algorithm, "policy-volume")
        self.assertEqual(post_midboss.horizon, 8)
        self.assertIsNone(post_midboss.target)
        self.assertEqual(residual_tail.phase_id, post_midboss.phase_id)
        self.assertEqual(next_resource.algorithm, "uncovered")
        self.assertEqual(
            next_resource.phase_id,
            "timeline:t4498:sub0-resource-formations",
        )

    def test_common_solver_stops_if_stage1_midboss_is_missing_after_insertion(self):
        decision = Solver(decision_budget_ms=100.0).decide(
            snapshot(stage=1, timeline_time=2009)
        )

        self.assertTrue(decision.safe_actions)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "phase-unavailable")
        self.assertEqual(decision.route_id, "hard-reimu-a-stage1")
        self.assertEqual(
            decision.phase_id,
            "timeline:t2009:sub8-midboss-missing",
        )

    def test_stage1_midboss_uses_stable_sub8_identity_after_insertion(self):
        subroutines = tuple(0x1000 + index * 0x100 for index in range(10))
        boss = SimpleNamespace(
            is_boss=True,
            boss_id=0,
            slot=0,
            next_instruction=SimpleNamespace(address=subroutines[8] + 0x10),
            ecl_subroutines=subroutines,
            life_callback_sub=9,
            timer_callback_sub=7,
            ecl_time=2,
            x=320.0,
            movement_mode=0,
            move_start_x=0.0,
            move_interp_x=0.0,
        )

        intent = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2009,
            spawners=(boss,),
        ))

        self.assertEqual(intent.algorithm, "target-only")
        self.assertEqual(intent.policy_state, "entry-movement")
        self.assertEqual(intent.horizon, 4)
        self.assertIsNotNone(intent.target)
        self.assertEqual(
            intent.phase_id,
            "boss:0:sub8:life_cb9:timer_cb7:nonspell",
        )

        boss.ecl_time = 160
        first_attack = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2167,
            spawners=(boss,),
        ))
        self.assertEqual(first_attack.algorithm, "policy-volume")
        self.assertEqual(first_attack.policy_state, "first-circle-movement")
        self.assertEqual(first_attack.horizon, 8)
        self.assertEqual(first_attack.target, (320.0, 380.0))
        self.assertEqual(first_attack.phase_id, intent.phase_id)

        boss.movement_mode = 2
        boss.move_start_x = 320.0
        boss.move_interp_x = -128.0
        moving_attack = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2209,
            spawners=(boss,),
        ))
        self.assertEqual(moving_attack.target, (192.0, 380.0))

        boss.ecl_time = 414
        second_attack = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2421,
            spawners=(boss,),
        ))
        self.assertEqual(second_attack.algorithm, "policy-volume")
        self.assertEqual(second_attack.policy_state, "paired-circles-movement")
        self.assertEqual(second_attack.horizon, 8)
        self.assertEqual(second_attack.target, (192.0, 380.0))
        self.assertEqual(second_attack.phase_id, intent.phase_id)

        boss.ecl_time = 738
        third_attack = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2745,
            spawners=(boss,),
        ))
        self.assertEqual(third_attack.algorithm, "policy-volume")
        self.assertEqual(third_attack.policy_state, "late-circles-loop")
        self.assertEqual(third_attack.horizon, 8)
        self.assertEqual(third_attack.target, (192.0, 380.0))
        self.assertEqual(third_attack.phase_id, intent.phase_id)

        boss.ecl_time = 840
        loop = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2847,
            spawners=(boss,),
        ))
        self.assertEqual(loop.policy_state, "late-circles-loop")

        boss.ecl_time = 193
        repeated_cycle = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=2848,
            spawners=(boss,),
        ))
        self.assertEqual(repeated_cycle.policy_state, "first-circle-movement")

        boss.ecl_time = 1
        boss.next_instruction = SimpleNamespace(address=subroutines[9] + 0x10)
        life_callback = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3044,
            spawners=(boss,),
        ))
        self.assertEqual(life_callback.algorithm, "uncovered")
        self.assertEqual(life_callback.policy_state, "uncovered")
        self.assertEqual(
            life_callback.phase_id,
            "boss:0:sub9:life_cb9:timer_cb7:nonspell",
        )

        boss.timer_callback_sub = 6
        spell_entry = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3044,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(spell_entry.algorithm, "target-only")
        self.assertEqual(spell_entry.policy_state, "spell-entry")
        self.assertEqual(spell_entry.horizon, 4)
        self.assertIsNotNone(spell_entry.target)
        self.assertEqual(
            spell_entry.phase_id,
            "boss:0:sub9:life_cb9:timer_cb6:spell",
        )

        boss.ecl_time = 120
        spell_attack = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3162,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(spell_attack.algorithm, "target-only")
        self.assertEqual(spell_attack.policy_state, "laser-pattern-start")
        self.assertEqual(spell_attack.horizon, 4)
        self.assertIsNotNone(spell_attack.target)

        boss.ecl_time = 150
        laser_rotation = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3192,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(laser_rotation.algorithm, "policy-volume")
        self.assertEqual(laser_rotation.policy_state, "rotating-laser-loop")
        self.assertEqual(laser_rotation.horizon, 6)
        self.assertIsNone(laser_rotation.target)

        boss.ecl_time = 151
        repeated_rotation = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3250,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(repeated_rotation.policy_state, "rotating-laser-loop")

        boss.ecl_time = 152
        laser_tail = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3313,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(laser_tail.algorithm, "policy-volume")
        self.assertEqual(laser_tail.policy_state, "laser-retirement-tail")
        self.assertEqual(laser_tail.horizon, 6)
        self.assertIsNone(laser_tail.target)

        boss.ecl_time = 211
        spell_movement = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3372,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(spell_movement.algorithm, "policy-volume")
        self.assertEqual(spell_movement.policy_state, "random-movement")
        self.assertEqual(spell_movement.horizon, 6)
        self.assertIsNone(spell_movement.target)

        boss.ecl_time = 330
        movement_tail = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3491,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(movement_tail.policy_state, "random-movement")

        boss.ecl_time = 331
        cycle_rewind = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3492,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(cycle_rewind.algorithm, "policy-volume")
        self.assertEqual(cycle_rewind.policy_state, "cycle-rewind")
        self.assertEqual(cycle_rewind.horizon, 4)
        self.assertEqual(cycle_rewind.commitment_frames, 1)
        self.assertIsNone(cycle_rewind.target)

        boss.ecl_time = 332
        impossible_tail = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3493,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(impossible_tail.algorithm, "uncovered")
        self.assertEqual(impossible_tail.policy_state, "uncovered")

        boss.next_instruction = SimpleNamespace(
            address=subroutines[6] + 0x10
        )
        boss.ecl_time = 0
        spell_end = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3499,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=True),
        ))
        self.assertEqual(spell_end.algorithm, "target-only")
        self.assertEqual(spell_end.policy_state, "spell-end-conversion")
        self.assertEqual(spell_end.horizon, 4)
        self.assertEqual(spell_end.commitment_frames, 1)
        self.assertEqual(spell_end.target, (192.0, 380.0))
        self.assertEqual(
            spell_end.phase_id,
            "boss:0:sub6:life_cb9:timer_cb6:spell",
        )

        boss.ecl_time = 1
        items = (
            ItemState(223, -2.5, 110.5, 0.0, -2.17, 0.0, 0.0, 0, 1, 1.0, 2, 0),
            ItemState(224, 20.0, 183.0, 0.0, -2.17, 0.0, 0.0, 0, 1, 1.0, 0, 0),
        )
        spell_end_tail = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3500,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=False),
            item_states=items,
        ))
        self.assertEqual(spell_end_tail.algorithm, "target-only")
        self.assertEqual(spell_end_tail.policy_state, "power-collection-tail")
        self.assertEqual(spell_end_tail.horizon, 4)
        self.assertEqual(spell_end_tail.target, (8.0, 110.5))

        boss.ecl_time = 2
        nearest_small = HardReimuAStage1().intent(snapshot(
            stage=1,
            x=90.0,
            y=200.0,
            timeline_time=3501,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=False),
            item_states=(
                replace(items[1], slot=224, x=20.0, y=180.0),
                replace(items[1], slot=225, x=92.0, y=212.0),
            ),
        ))
        self.assertEqual(nearest_small.target, (92.0, 212.0))

        boss.ecl_time = 160
        despawn_boundary = HardReimuAStage1().intent(snapshot(
            stage=1,
            timeline_time=3659,
            spawners=(boss,),
            player_attack=replace(player_attack(), spell_active=False),
        ))
        self.assertEqual(despawn_boundary.algorithm, "uncovered")
        self.assertEqual(despawn_boundary.policy_state, "uncovered")

    def test_stage4_timeline_boundaries_are_source_timeline_times(self):
        self.assertEqual(timeline_phase(2387).phase_id, "timeline:t1878:subs3-2")
        self.assertEqual(
            timeline_phase(2388).phase_id,
            "timeline:t2388:subs11-13",
        )
        self.assertEqual(
            timeline_phase(2712).phase_id,
            "timeline:t2712:subs5-4-3",
        )
        self.assertEqual(
            timeline_phase(2388).state(2388).state_id,
            "formation",
        )

    def test_t1004_phase_uses_the_physically_publishable_local_rung(self):
        phase = timeline_phase(1004)
        self.assertEqual(phase.phase_id, "timeline:t1004:subs2-3")
        self.assertEqual(phase.state(1004).horizon, 8)

    def test_t1514_phase_uses_its_measured_publishable_rung(self):
        phase = timeline_phase(1514)
        self.assertEqual(phase.phase_id, "timeline:t1514:sub10")
        self.assertEqual(phase.state(1514).state_id, "parent-entry")
        self.assertEqual(phase.state(1584).state_id, "child-circle")
        self.assertEqual(phase.state(1615).horizon, 8)
        self.assertIsNotNone(phase.state(1648).target)
        self.assertEqual(phase.state(1649).state_id, "tail")
        self.assertEqual(phase.state(1649).horizon, 7)
        self.assertIsNotNone(phase.state(1649).target)

    def test_historical_dense_rules_are_owned_by_their_source_states(self):
        horizontal = timeline_phase(2388)
        following = timeline_phase(2712)

        self.assertEqual(horizontal.state(2457).state_id, "formation")
        self.assertEqual(horizontal.state(2457).horizon, 8)
        self.assertEqual(horizontal.state(2458).state_id, "horizontal-band")
        self.assertEqual(horizontal.state(2458).horizon, 6)
        self.assertEqual(horizontal.state(2458).algorithm, "constant-frontier")
        self.assertIsNone(horizontal.state(2458).target)
        self.assertEqual(following.state(2712).state_id, "sub5-aimed-stream")
        self.assertEqual(following.state(2712).horizon, 6)
        self.assertEqual(following.state(2712).algorithm, "policy-volume")
        self.assertIsNone(following.state(2712).target)
        self.assertEqual(following.state(2942).state_id, "sub4-aimed-stream")
        self.assertEqual(following.state(3172).state_id, "sub3-aimed-stream")
        self.assertIsNotNone(following.state(2942).target)

    def test_t1878_sub3_causal_boundary_does_not_leak_into_sub2(self):
        stream = timeline_phase(1878)

        self.assertEqual(stream.state(1878).state_id, "sub3-aimed-stream")
        self.assertEqual(stream.state(2107).horizon, 6)
        self.assertEqual(stream.state(2108).state_id, "sub2-aimed-stream")
        self.assertEqual(stream.state(2108).horizon, 8)

    def test_phase_state_machine_can_seek_without_cross_phase_history(self):
        machine = TimelineStateMachine(
            "test-phase",
            (
                PolicyState(10, "entry", "target-only", 4, (10.0, 20.0)),
                PolicyState(20, "active", "policy-volume", 8, (30.0, 40.0)),
            ),
        )

        active = machine.intent(snapshot(timeline_time=25))
        entry = machine.intent(snapshot(timeline_time=15))

        self.assertEqual(active.policy_state, "active")
        self.assertEqual(active.horizon, 8)
        self.assertEqual(entry.policy_state, "entry")
        self.assertEqual(entry.horizon, 4)

    def test_ecl_phase_identity_survives_pointer_relocation(self):
        first = SimpleNamespace(
            next_instruction=SimpleNamespace(address=0x1108),
            ecl_subroutines=(0x1000, 0x1100, 0x1300),
            boss_id=0,
            life_callback_sub=22,
            timer_callback_sub=23,
        )
        relocated = SimpleNamespace(
            next_instruction=SimpleNamespace(address=0x71108),
            ecl_subroutines=(0x70000, 0x71100, 0x71300),
            boss_id=0,
            life_callback_sub=22,
            timer_callback_sub=23,
        )
        self.assertEqual(ecl_subroutine_index(first), 1)
        self.assertEqual(ecl_subroutine_index(relocated), 1)
        self.assertEqual(
            boss_phase_id(first, False),
            boss_phase_id(relocated, False),
        )

    def test_stage4_pack_exposes_boss_phase_as_uncovered(self):
        boss = SimpleNamespace(
            is_boss=True,
            boss_id=0,
            slot=3,
            next_instruction=SimpleNamespace(address=0x1108),
            ecl_subroutines=(0x1000, 0x1100, 0x1300),
            life_callback_sub=22,
            timer_callback_sub=23,
        )
        intent = HardReimuAStage4().intent(snapshot(spawners=(boss,)))
        self.assertIsNotNone(intent)
        self.assertEqual(intent.algorithm, "uncovered")
        self.assertEqual(intent.policy_state, "uncovered")
        self.assertEqual(
            intent.phase_id,
            "boss:0:sub1:life_cb22:timer_cb23:nonspell",
        )

    def test_common_solver_executes_stage4_intent_only_inside_hard(self):
        decision = Solver(decision_budget_ms=100.0).decide(snapshot())
        hard_actions = {candidate.action for candidate in decision.safe_actions}

        self.assertEqual(decision.reason, "ok")
        self.assertIn(decision.action, hard_actions)
        self.assertEqual(decision.route_id, "hard-reimu-a-stage4")
        self.assertEqual(decision.phase_id, "timeline:t0:setup")
        self.assertEqual(decision.policy_state, "staging")
        self.assertEqual(decision.effort_horizon, 8)

    def test_common_solver_runs_only_the_selected_dense_phase_state(self):
        decision = Solver(decision_budget_ms=100.0).decide(
            snapshot(timeline_time=2458)
        )

        self.assertEqual(decision.reason, "ok")
        self.assertEqual(decision.phase_id, "timeline:t2388:subs11-13")
        self.assertEqual(decision.policy_state, "horizontal-band")
        self.assertEqual(decision.effort_horizon, 6)
        self.assertEqual(decision.proposal_source, "constant-frontier")

    def test_missing_route_is_fail_visible_even_when_hard_exists(self):
        decision = Solver().decide(snapshot(stage=3))

        self.assertTrue(decision.safe_actions)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "route-unavailable")


if __name__ == "__main__":
    unittest.main()
