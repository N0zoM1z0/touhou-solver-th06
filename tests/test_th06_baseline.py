import unittest

from th06.model import (
    ACTION_BY_VECTOR,
    ACTIONS,
    BUTTON_BOMB,
    BUTTON_FOCUS,
    BUTTON_LEFT,
    Bullet,
    Snapshot,
    action_from_input,
)
from th06.ranking import ProposalRanker
from th06.safety import certify_actions
from th06.solver import Solver, adaptive_horizon
from th06.actuator import Keyboard
from th06.agent import authority_unavailable
from th06.menu import _select_unlocked_practice_stage
from th06 import menu
from th06.native import PROCESS_ACCESS
from th06.model import Decision


def snapshot(*bullets, x=192.0, y=380.0, input_mask=BUTTON_FOCUS, lasers=0):
    return Snapshot(
        frame=1,
        stage=1,
        player_state=0,
        x=x,
        y=y,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.828427,
        focus_diagonal_speed=1.414214,
        frame_multiplier=1.0,
        input_mask=input_mask,
        bullets=tuple(bullets),
        laser_count=lasers,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
    )


class BaselineTests(unittest.TestCase):
    def test_native_direction_precedence(self):
        self.assertEqual(action_from_input(BUTTON_LEFT).name, "left")

    def test_bomb_is_never_an_action(self):
        self.assertEqual(BUTTON_BOMB, 0x02)
        self.assertNotIn("bomb", {action.name for action in ACTIONS})
        self.assertNotIn("bomb", Keyboard.SCANCODES)
        self.assertEqual(Keyboard.SCANCODES["skip"], (0x1D, False))

    def test_complete_mask_transition_is_one_batch(self):
        keyboard = object.__new__(Keyboard)
        keyboard.held = {"shoot", "focus", "left"}
        keyboard.base_desired = {"shoot", "focus", "left"}
        keyboard.auxiliary_desired = set()
        batches = []
        keyboard._events = lambda events: batches.append(events)

        events = keyboard.apply(ACTION_BY_VECTOR[(1, 0)])

        self.assertEqual(events, (("left", False), ("right", True)))
        self.assertEqual(batches, [events])
        self.assertEqual(keyboard.base_input_mask, 0x85)
        self.assertFalse(keyboard.base_input_mask & BUTTON_BOMB)

    def test_missing_authority_is_not_no_write(self):
        self.assertTrue(
            authority_unavailable(Decision(None, (), 0.0, 16, "hard-safe-set-empty"))
        )
        self.assertTrue(
            authority_unavailable(Decision(None, (), 0.0, 0, "unsupported-active-laser"))
        )
        self.assertFalse(authority_unavailable(Decision(None, (), 0.0, 0, "menu")))

    def test_practice_stage_selection_fails_if_locked(self):
        process = type("Process", (), {"cursor": 0})()

        class KeyboardStub:
            def tap(self, key):
                self.assertEqual(key, "down")
                process.cursor = (process.cursor + 1) % 3

            assertEqual = self.assertEqual

        original = menu.read_menu_state
        menu.read_menu_state = lambda _process: (17, process.cursor, 30)
        try:
            with self.assertRaisesRegex(RuntimeError, "not unlocked"):
                _select_unlocked_practice_stage(process, KeyboardStub(), stage=4)
        finally:
            menu.read_menu_state = original

    def test_trial_process_handle_can_verify_termination(self):
        self.assertTrue(PROCESS_ACCESS & 0x00100000)  # SYNCHRONIZE
        self.assertTrue(PROCESS_ACCESS & 0x0001)  # PROCESS_TERMINATE

    def test_practice_stage_uses_zero_based_menu_cursor(self):
        process = type("Process", (), {"cursor": 0})()

        class KeyboardStub:
            def tap(self, key):
                self.assertEqual(key, "down")
                process.cursor = (process.cursor + 1) % 6

            assertEqual = self.assertEqual

        original = menu.read_menu_state
        menu.read_menu_state = lambda _process: (17, process.cursor, 30)
        try:
            _select_unlocked_practice_stage(process, KeyboardStub(), stage=6)
            self.assertEqual(process.cursor, 5)
        finally:
            menu.read_menu_state = original

    def test_head_on_bullet_rejects_stay(self):
        bullet = Bullet(192.0, 360.0, 0.0, 3.0, 2.0, 2.0, 1)
        safe = certify_actions(snapshot(bullet), horizon=8)
        self.assertNotIn(ACTION_BY_VECTOR[(0, 0)], {candidate.action for candidate in safe})
        self.assertTrue(safe)

    def test_pickup_delay_branch_rejects_late_escape(self):
        bullet = Bullet(192.0, 371.0, 0.0, 2.0, 2.0, 2.0, 1)
        safe = certify_actions(snapshot(bullet), horizon=5)
        self.assertNotIn(ACTION_BY_VECTOR[(1, 0)], {candidate.action for candidate in safe})

    def test_adaptive_horizon_grows_near_hazard(self):
        far = snapshot(Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1))
        near = snapshot(Bullet(192.0, 390.0, 0.0, 0.0, 2.0, 2.0, 1))
        self.assertGreater(adaptive_horizon(near), adaptive_horizon(far))

    def test_laser_fails_closed(self):
        decision = Solver().decide(snapshot(lasers=1))
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "unsupported-active-laser")

    def test_non_unit_native_timing_fails_closed(self):
        state = snapshot()
        state = Snapshot(**{**state.__dict__, "frame_multiplier": 0.8})
        decision = Solver().decide(state)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "unsupported-frame-multiplier")

    def test_replay_fails_closed(self):
        state = snapshot()
        state = Snapshot(**{**state.__dict__, "replay_or_demo": True})
        decision = Solver().decide(state)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "replay-or-demo")

    def test_ranker_can_only_choose_from_safe_set(self):
        state = snapshot()
        allowed = tuple(candidate for candidate in certify_actions(state, 8) if candidate.action.name in ("stay", "right"))
        chosen = ProposalRanker().choose(state, allowed)
        self.assertIn(chosen, allowed)

    def test_ranker_recovers_from_top_right_boundary(self):
        state = snapshot(x=376.0, y=16.0)
        candidates = certify_actions(state, 8)
        chosen = ProposalRanker().choose(state, candidates)
        self.assertLess(chosen.final_x, state.x)
        self.assertGreater(chosen.final_y, state.y)


if __name__ == "__main__":
    unittest.main()
