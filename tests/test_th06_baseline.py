import unittest
import struct

from th06.model import (
    ACTION_BY_VECTOR,
    ACTIONS,
    BUTTON_BOMB,
    BUTTON_FOCUS,
    BUTTON_LEFT,
    BUTTON_SHOOT,
    Bullet,
    EnemyBody,
    Laser,
    SafeAction,
    Snapshot,
    action_from_input,
)
from th06.ranking import ProposalRanker
from th06.safety import certify_actions
from th06.hazards.bullets import hazard_box
from th06.hazards.enemies import future_boxes as future_enemy_boxes
from th06.hazards.lasers import future_hazards, signed_laser_clearance
from th06.solver import HARD_SAFETY_HORIZON, Solver, adaptive_horizon
from th06.actuator import Keyboard
from th06.dialogue import DialogueSkipper
from th06.input_lease import InputLease
from th06.agent import authority_unavailable
from th06.menu import _select_unlocked_practice_stage
from th06 import dialogue, menu
from th06.native import (
    ADDR_CHAIN,
    ADDR_ENEMY_CALC_CHAIN,
    ADDR_ENEMY_MANAGER,
    ENEMY_MANAGER_SIZE,
    PROCESS_ACCESS,
    RESULT_SCREEN_ON_UPDATE,
    read_result_screen,
)
from th06.replay import ALPHABET, _move_character, _next_character_key, validate_replay_bytes
from th06.model import Decision
from th06.trial import (
    PracticeTrial,
    SUPERVISOR_GAMEPLAY,
    SUPERVISOR_MAIN_MENU,
    SUPERVISOR_RESULT_FROM_GAME,
    physical_hit,
)


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


def enemy_body(**changes):
    values = dict(
        x=192.0,
        y=380.0,
        half_width=4.0,
        half_height=4.0,
        velocity_x=0.0,
        velocity_y=0.0,
        angle=0.0,
        angular_velocity=0.0,
        speed=0.0,
        acceleration=0.0,
        movement_mode=0,
        movement_ease=0,
        invert_x=False,
        move_interp_x=0.0,
        move_interp_y=0.0,
        move_start_x=0.0,
        move_start_y=0.0,
        move_timer=0,
        move_timer_float=0.0,
        move_start_time=0,
    )
    values.update(changes)
    return EnemyBody(**values)


class BaselineTests(unittest.TestCase):
    def test_native_direction_precedence(self):
        self.assertEqual(action_from_input(BUTTON_LEFT).name, "left")

    def test_bomb_is_never_an_action(self):
        self.assertEqual(BUTTON_BOMB, 0x02)
        self.assertNotIn("bomb", {action.name for action in ACTIONS})
        self.assertNotIn("bomb", Keyboard.SCANCODES)
        self.assertEqual(Keyboard.SCANCODES["skip"], (0x1D, False))
        self.assertEqual(Keyboard.SCANCODES["menu"], (0x01, False))

    def test_complete_mask_transition_is_one_batch(self):
        keyboard = object.__new__(Keyboard)
        keyboard.held = {"shoot", "focus", "left"}
        keyboard.base_desired = {"shoot", "focus", "left"}
        keyboard.auxiliary_desired = set()
        keyboard.suppressed = set()
        batches = []
        keyboard._events = lambda events: batches.append(events)

        events = keyboard.apply(ACTION_BY_VECTOR[(1, 0)])

        self.assertEqual(events, (("left", False), ("right", True)))
        self.assertEqual(batches, [events])
        self.assertEqual(keyboard.base_input_mask, 0x85)
        self.assertFalse(keyboard.base_input_mask & BUTTON_BOMB)

    def test_input_lease_waits_for_native_pickup(self):
        lease = InputLease()
        right = ACTION_BY_VECTOR[(1, 0)]
        lease.issued(10, right)

        self.assertEqual(lease.status(BUTTON_FOCUS | BUTTON_LEFT, 11).action, right)
        self.assertIsNone(lease.status(BUTTON_FOCUS | 0x80, 12).action)
        lease.cleared()
        self.assertIsNone(lease.status(BUTTON_FOCUS | BUTTON_LEFT, 12).action)

    def test_shoot_suppression_is_a_nonblocking_edge(self):
        keyboard = object.__new__(Keyboard)
        keyboard.held = {"shoot", "focus"}
        keyboard.base_desired = {"shoot", "focus"}
        keyboard.auxiliary_desired = set()
        keyboard.suppressed = set()
        batches = []
        keyboard._events = lambda events: batches.append(events)

        keyboard.set_suppressed("shoot", True)
        keyboard.set_suppressed("shoot", False)

        self.assertEqual(batches, [(('shoot', False),), (('shoot', True),)])

    def test_dialogue_wait_pulse_advances_without_sleeping(self):
        class KeyboardStub:
            def __init__(self):
                self.suppression = []

            def set_auxiliary(self, _key, _enabled):
                pass

            def set_suppressed(self, key, enabled):
                self.suppression.append((key, enabled))

        ticks = iter((1.0, 1.04, 1.06))
        original_read = dialogue.read_dialogue_state
        original_clock = dialogue.time.monotonic
        dialogue.read_dialogue_state = lambda _process: (True, False)
        dialogue.time.monotonic = lambda: next(ticks)
        try:
            keyboard = KeyboardStub()
            skipper = DialogueSkipper(object(), keyboard)
            self.assertFalse(skipper.update(True).pulsed_shoot)
            self.assertFalse(skipper.update(True).pulsed_shoot)
            self.assertTrue(skipper.update(True).pulsed_shoot)
            self.assertEqual(
                keyboard.suppression,
                [("shoot", True), ("shoot", False)],
            )
        finally:
            dialogue.read_dialogue_state = original_read
            dialogue.time.monotonic = original_clock

    def test_input_lease_fails_closed_after_pickup_bound(self):
        lease = InputLease()
        lease.issued(10, ACTION_BY_VECTOR[(1, 0)])
        self.assertTrue(lease.status(BUTTON_FOCUS | BUTTON_LEFT, 12).timed_out)

    def test_input_lease_age_starts_at_physical_issue_frame(self):
        lease = InputLease()
        # A dialogue edge may advance the game after the decision snapshot but
        # before SendInput. The post-SendInput frame is the lease boundary.
        lease.issued(13, ACTION_BY_VECTOR[(1, 0)])
        status = lease.status(BUTTON_FOCUS | BUTTON_LEFT, 14)
        self.assertFalse(status.timed_out)
        self.assertEqual(status.action, ACTION_BY_VECTOR[(1, 0)])

    def test_missing_authority_is_not_no_write(self):
        self.assertTrue(
            authority_unavailable(Decision(None, (), 0.0, 16, "hard-safe-set-empty"))
        )
        self.assertTrue(
            authority_unavailable(Decision(None, (), 0.0, 0, "unsupported-active-laser"))
        )
        self.assertFalse(authority_unavailable(Decision(None, (), 0.0, 0, "menu")))

    def test_first_physical_hit_stops_authority(self):
        self.assertTrue(physical_hit(0, 2))
        self.assertFalse(physical_hit(3, 2))
        self.assertTrue(
            authority_unavailable(Decision(None, (), 0.0, 6, "physical-hit", 6))
        )

    def test_practice_only_completes_after_gameplay(self):
        trial = PracticeTrial()
        self.assertFalse(trial.observe_supervisor(SUPERVISOR_MAIN_MENU))
        self.assertFalse(trial.observe_supervisor(SUPERVISOR_GAMEPLAY))
        self.assertTrue(trial.observe_supervisor(SUPERVISOR_RESULT_FROM_GAME))

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

    def test_enemy_manager_layout_ends_at_mapped_calc_chain(self):
        self.assertEqual(ADDR_ENEMY_MANAGER + ENEMY_MANAGER_SIZE, ADDR_ENEMY_CALC_CHAIN)

    def test_result_screen_is_found_through_calc_chain(self):
        chain_elem = bytearray(0x20)
        struct.pack_into("<I", chain_elem, 0x4, RESULT_SCREEN_ON_UPDATE)
        struct.pack_into("<I", chain_elem, 0x1C, 0x200000)
        result = bytearray(0x34)
        struct.pack_into("<iii", result, 0x4, 90, 15, 0)
        struct.pack_into("<ii", result, 0x1C, 0, 0)
        memory = {
            (ADDR_CHAIN + 0x14, 4): struct.pack("<I", 0x100000),
            (0x100000, 0x20): bytes(chain_elem),
            (0x200000, 0x34): bytes(result),
        }
        process = type("Process", (), {"read": lambda _self, address, size: memory[(address, size)]})()
        state = read_result_screen(process)
        self.assertEqual((state.address, state.frame_timer, state.state), (0x200000, 90, 15))

    def test_replay_keyboard_reaches_end_without_space_cells(self):
        current = 0
        for _ in range(32):
            if current == 95:
                break
            current = _move_character(current, _next_character_key(current, 95))
            self.assertNotEqual(ALPHABET[current], " ")
        self.assertEqual(current, 95)

    def test_replay_checksum_validation_matches_source_algorithm(self):
        decoded = bytearray(0x60)
        decoded[:4] = b"T6RP"
        struct.pack_into("<H", decoded, 4, 0x102)
        decoded[0xE] = 0x41
        for index in range(0xF, len(decoded)):
            decoded[index] = (index * 3) & 0xFF
        checksum = (0x3F000318 + sum(decoded[0xE:])) & 0xFFFFFFFF
        struct.pack_into("<I", decoded, 0x8, checksum)
        encoded = bytearray(decoded)
        offset = encoded[0xE]
        for index in range(0xF, len(encoded)):
            encoded[index] = (encoded[index] + offset) & 0xFF
            offset = (offset + 7) & 0xFF
        validate_replay_bytes(bytes(encoded))

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

    def test_fired_fixed_acceleration_uses_source_motion_not_all_directions(self):
        bullet = Bullet(
            100.0,
            300.0,
            -1.0,
            3.0,
            2.0,
            2.0,
            1,
            ex_flags=0x14,
            acceleration=0.02,
            acceleration_x=-0.006,
            acceleration_y=0.019,
        )
        left, top, right, bottom = hazard_box(bullet, 12)
        self.assertGreater(left, 80.0)
        self.assertLess(right, 91.0)
        self.assertGreaterEqual(top, 334.0)
        self.assertLess(bottom, 340.0)

    def test_pickup_delay_branch_rejects_late_escape(self):
        bullet = Bullet(192.0, 371.0, 0.0, 2.0, 2.0, 2.0, 1)
        safe = certify_actions(snapshot(bullet), horizon=5)
        self.assertNotIn(ACTION_BY_VECTOR[(1, 0)], {candidate.action for candidate in safe})

    def test_input_lease_can_only_hold_a_hard_safe_action(self):
        right = ACTION_BY_VECTOR[(1, 0)]
        open_decision = Solver().decide(snapshot(), required_action=right)
        self.assertEqual(open_decision.action, right)

        blocked = snapshot(Bullet(196.0, 380.0, 0.0, 0.0, 2.0, 2.0, 1))
        blocked_decision = Solver().decide(blocked, required_action=right)
        self.assertIsNone(blocked_decision.action)
        self.assertEqual(blocked_decision.reason, "input-lease-unsafe")
        self.assertTrue(blocked_decision.safe_actions)

    def test_pending_action_uses_only_the_remaining_pickup_frame(self):
        # Reduced from the physical input-pipeline CE: extending the pending
        # command as if newly issued rejects right, although both possible
        # inputs on the sole remaining pickup frame are safe.
        state = snapshot(
            Bullet(
                64.37475, 376.03484, 0.0, 2.3,
                2.0, 2.0, 1, ex_flags=4, speed=2.3, turn_speed=2.3,
            ),
            x=64.4436,
            y=382.3603,
            input_mask=BUTTON_SHOOT | BUTTON_FOCUS | 0x20 | BUTTON_LEFT,
        )
        right = ACTION_BY_VECTOR[(1, 0)]
        self.assertNotIn(right, {item.action for item in certify_actions(state, 4)})

        pending = Solver().decide(state, required_action=right)
        self.assertEqual(pending.action, right)
        self.assertEqual(pending.horizon, 1)

    def test_adaptive_horizon_grows_near_hazard(self):
        far = snapshot(Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1))
        near = snapshot(Bullet(192.0, 390.0, 0.0, 0.0, 2.0, 2.0, 1))
        self.assertGreater(adaptive_horizon(near), adaptive_horizon(far))

    def test_laser_fails_closed(self):
        decision = Solver().decide(snapshot(lasers=1))
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "unsupported-laser-decode")

    def test_laser_warning_before_hitbox_start_is_not_a_hazard(self):
        laser = Laser(
            0.0, 380.0, 0.0, 0.0, 384.0, 384.0, 16.0, 0.0,
            60, 45, 120, 30, 10, 0, 0.0, 0, 0,
        )
        self.assertTrue(all(not frame for frame in future_hazards(laser, 16)))

    def test_active_laser_uses_rotated_source_hitbox(self):
        laser = Laser(
            0.0, 380.0, 0.0, 0.0, 384.0, 384.0, 16.0, 0.0,
            0, 0, 120, 30, 10, 0, 0.0, 0, 1,
        )
        hazard = future_hazards(laser, 1)[0][0]
        self.assertLess(signed_laser_clearance(192.0, 380.0, 1.25, 1.25, hazard), 0.0)
        state = snapshot()
        state = Snapshot(**{**state.__dict__, "laser_count": 1, "lasers": (laser,)})
        decision = Solver().decide(state)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "hard-safe-set-empty")

    def test_enemy_body_is_a_hard_hazard(self):
        state = snapshot()
        state = Snapshot(**{**state.__dict__, "enemies": (enemy_body(),)})
        decision = Solver().decide(state)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "hard-safe-set-empty")

    def test_enemy_body_follows_source_axis_move(self):
        body = enemy_body(x=100.0, y=200.0, velocity_x=2.0, velocity_y=3.0)
        boxes = future_enemy_boxes(body, 2)
        self.assertEqual(boxes[0], (98.0, 199.0, 106.0, 207.0))
        self.assertEqual(boxes[1], (100.0, 202.0, 108.0, 210.0))

    def test_laser_warmup_fallthrough_keeps_midpoint_hitbox(self):
        laser = Laser(
            0.0, 380.0, 0.0, 0.0, 384.0, 384.0, 16.0, 0.0,
            30, 0, 120, 30, 10, 30, 30.0, 0, 0,
        )
        hazards = future_hazards(laser, 1)[0]
        self.assertEqual(len(hazards), 2)
        self.assertEqual(hazards[0].size_x, hazards[1].size_x)
        self.assertLess(hazards[1].size_x, 16.0)

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

    def test_longer_rollout_ranks_but_does_not_authorize(self):
        state = snapshot(x=376.0, y=416.0)
        allowed = certify_actions(state, HARD_SAFETY_HORIZON)
        up = ACTION_BY_VECTOR[(0, -1)]
        chosen = ProposalRanker().choose(state, allowed, frozenset((up,)))
        self.assertEqual(chosen.action, up)
        self.assertIn(chosen, allowed)

    def test_ranker_egresses_corner_when_durable_rollout_is_empty(self):
        state = snapshot(x=8.0, y=426.0, input_mask=BUTTON_FOCUS | 0x20 | 0x40)
        trapped = SafeAction(ACTION_BY_VECTOR[(-1, 1)], 22.0, 8.0, 432.0)
        egress = SafeAction(ACTION_BY_VECTOR[(1, -1)], 10.0, 10.8, 426.0)
        chosen = ProposalRanker().choose(state, (trapped, egress))
        self.assertEqual(chosen, egress)

    def test_adaptive_effort_cannot_remove_hard_allowed_actions(self):
        bullets = tuple(
            Bullet(120.0 + index * 4.0, 360.0, 0.0, 4.0, 2.0, 2.0, 1, ex_flags=8)
            for index in range(20)
        )
        state = snapshot(*bullets, x=192.0, y=420.0)
        decision = Solver().decide(state)
        expected = certify_actions(state, HARD_SAFETY_HORIZON)
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in expected},
        )
        self.assertEqual(decision.horizon, HARD_SAFETY_HORIZON)

    def test_native_pair_keeps_hard_and_effort_sets_separate(self):
        hard = (SafeAction(ACTION_BY_VECTOR[(0, 0)], 10.0, 192.0, 380.0),)
        effort = (SafeAction(ACTION_BY_VECTOR[(0, 0)], 4.0, 192.0, 380.0),)

        class PairKernel:
            def __init__(self):
                self.calls = []

            def certify_pair(self, _snapshot, hard_horizon, effort_horizon, collision_margin):
                self.calls.append((hard_horizon, effort_horizon, collision_margin))
                return hard, effort

        solver = Solver()
        solver.kernel = PairKernel()
        decision = solver.decide(snapshot())

        self.assertEqual(decision.safe_actions, hard)
        self.assertEqual(decision.effort_safe_count, 1)
        self.assertEqual(
            solver.kernel.calls,
            [(HARD_SAFETY_HORIZON, 8, 0.35)],
        )

    def test_hard_issue_window_is_not_a_constant_action_rollout(self):
        # Reduced witness from the physical f7185 CE: both source-linear
        # bullets can be avoided by replanning, but no one direction can be
        # held for six complete frames at the right boundary.
        state = snapshot(
            Bullet(
                356.5753479, 388.9111633, 2.6534963, 3.9735920,
                3.0, 3.0, 1, ex_flags=4,
            ),
            Bullet(
                357.6143494, 376.7509155, 2.9544528, 4.2639613,
                3.0, 3.0, 1, ex_flags=4,
            ),
            x=376.0,
            y=404.1004944,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
        )
        self.assertFalse(certify_actions(state, 6))
        decision = Solver().decide(state)
        self.assertEqual(decision.horizon, HARD_SAFETY_HORIZON)
        self.assertTrue(decision.safe_actions)

    def test_ranker_recovers_from_top_right_boundary(self):
        state = snapshot(x=376.0, y=16.0)
        candidates = certify_actions(state, 8)
        chosen = ProposalRanker().choose(state, candidates)
        self.assertLess(chosen.final_x, state.x)
        self.assertGreater(chosen.final_y, state.y)


if __name__ == "__main__":
    unittest.main()
