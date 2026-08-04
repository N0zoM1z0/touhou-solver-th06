import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from th06.barrage_lab.assets import load_stage_timeline
from th06.model import BUTTON_FOCUS, PlayerAttackState, Snapshot
from th06.routes.phase import boss_phase_id, ecl_subroutine_index
from th06.routes.registry import default_routes, snapshot_route_key
from th06.routes.stage4_hard_reimu_a import (
    HardReimuAStage4,
    TIMELINE_PHASES,
    timeline_phase,
)
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
    def test_stage4_manifest_boundaries_exist_in_installed_ecl(self):
        timeline = load_stage_timeline(
            "reference/th06_dat/th06_ST.DAT", 4
        )
        source_times = {instruction.time for instruction in timeline}
        self.assertTrue(
            {phase.start for phase in TIMELINE_PHASES if phase.start}
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
        self.assertEqual(timeline_phase(2388).horizon, 16)

    def test_t1004_phase_uses_the_physically_publishable_local_rung(self):
        phase = timeline_phase(1004)
        self.assertEqual(phase.phase_id, "timeline:t1004:subs2-3")
        self.assertEqual(phase.horizon, 8)

    def test_t1514_phase_uses_its_measured_publishable_rung(self):
        phase = timeline_phase(1514)
        self.assertEqual(phase.phase_id, "timeline:t1514:sub10")
        self.assertEqual(phase.horizon, 8)

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
        self.assertEqual(decision.effort_horizon, 8)

    def test_missing_route_is_fail_visible_even_when_hard_exists(self):
        decision = Solver().decide(snapshot(stage=3))

        self.assertTrue(decision.safe_actions)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "route-unavailable")


if __name__ == "__main__":
    unittest.main()
