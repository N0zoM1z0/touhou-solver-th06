import unittest
import struct
from unittest import mock

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
from th06.safety import DELIVERY_DELAYS, certify_actions, transition_actions
from th06.hazards.bullets import hazard_box
from th06.hazards.enemies import future_boxes as future_enemy_boxes
from th06.hazards.lasers import future_hazards, signed_laser_clearance, track_motion
from th06.solver import HARD_SAFETY_HORIZON, Solver, adaptive_horizon
from th06.actuator import Keyboard
from th06.dialogue import DialogueSkipper
from th06.input_lease import InputLease, bounded_delivery_age, covered_current_retry
from th06.agent import authority_unavailable
from th06.menu import _select_unlocked_practice_stage
from th06 import dialogue, menu, native
from th06.native import (
    ADDR_CHAIN,
    ADDR_ENEMY_CALC_CHAIN,
    ADDR_ENEMY_MANAGER,
    BULLET_POSITION_OFFSET,
    BULLET_ACCEL_SPEED_OFFSET,
    BULLET_ACCELERATION_DURATION_OFFSET,
    BULLET_CURVE_ANGULAR_VELOCITY_OFFSET,
    BULLET_DIRECTION_MAX_TIMES_OFFSET,
    BULLET_EX_FLAGS_OFFSET,
    BULLET_SIZE_OFFSET,
    BULLET_STATE_OFFSET,
    BULLET_STRIDE,
    ENEMY_MANAGER_SIZE,
    NativeDecodeError,
    PROCESS_ACCESS,
    RESULT_SCREEN_ON_UPDATE,
    _decode_bullet_tail,
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
from th06.viability import replanning_scores


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
    def test_snapshot_read_retries_a_torn_game_frame(self):
        first = snapshot()
        second = Snapshot(**{**first.__dict__, "frame": 2})
        process = object()

        with mock.patch.object(
            native,
            "read_game_frame",
            side_effect=(1, 2, 2, 2),
        ), mock.patch.object(
            native,
            "_read_snapshot_once",
            side_effect=(first, second),
        ):
            coherent = native.read_snapshot(process)

        self.assertEqual(coherent.frame, 2)

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

    def test_stale_issue_retries_only_inside_certified_pickup_window(self):
        self.assertEqual(bounded_delivery_age(10, 10), 0)
        self.assertEqual(bounded_delivery_age(10, 12), 2)
        self.assertIsNone(bounded_delivery_age(10, 13))
        self.assertIsNone(bounded_delivery_age(10, 9))

    def test_late_retry_only_holds_an_explicitly_safe_current_action(self):
        down = ACTION_BY_VECTOR[(0, 1)]
        up = ACTION_BY_VECTOR[(0, -1)]
        safe = (SafeAction(down, 20.0, 192.0, 388.0),)

        self.assertTrue(covered_current_retry(10, 13, 4, down, safe))
        self.assertFalse(covered_current_retry(10, 13, 4, up, safe))
        self.assertFalse(covered_current_retry(10, 14, 4, down, safe))
        self.assertFalse(covered_current_retry(10, 13, 3, down, safe))

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

    def test_published_bullet_without_geometry_fails_closed(self):
        tail = bytearray(BULLET_STRIDE - BULLET_SIZE_OFFSET)
        struct.pack_into("<H", tail, BULLET_STATE_OFFSET - BULLET_SIZE_OFFSET, 1)

        with self.assertRaises(NativeDecodeError) as raised:
            _decode_bullet_tail(tail, 271)

        self.assertEqual(raised.exception.evidence["slot"], 271)
        self.assertEqual(raised.exception.evidence["state"], 1)

    def test_bullet_is_accepted_after_geometry_publication(self):
        tail = bytearray(BULLET_STRIDE - BULLET_SIZE_OFFSET)
        struct.pack_into("<ff", tail, 0, 4.0, 6.0)
        struct.pack_into(
            "<ff", tail, BULLET_POSITION_OFFSET - BULLET_SIZE_OFFSET, 123.0, 234.0
        )
        struct.pack_into("<H", tail, BULLET_STATE_OFFSET - BULLET_SIZE_OFFSET, 1)

        bullet = _decode_bullet_tail(tail, 271)

        self.assertEqual((bullet.x, bullet.y), (123.0, 234.0))
        self.assertEqual((bullet.half_width, bullet.half_height), (2.0, 3.0))

    def test_bullet_acceleration_duration_uses_source_layout(self):
        tail = bytearray(BULLET_STRIDE - BULLET_SIZE_OFFSET)
        struct.pack_into("<ff", tail, 0, 4.0, 4.0)
        struct.pack_into("<H", tail, BULLET_STATE_OFFSET - BULLET_SIZE_OFFSET, 1)
        struct.pack_into(
            "<H", tail, BULLET_EX_FLAGS_OFFSET - BULLET_SIZE_OFFSET, 0x14
        )
        struct.pack_into(
            "<i",
            tail,
            BULLET_ACCELERATION_DURATION_OFFSET - BULLET_SIZE_OFFSET,
            140,
        )

        bullet = _decode_bullet_tail(tail, 8)

        self.assertEqual(bullet.acceleration_duration, 140)

    def test_curve_acceleration_uses_source_layout(self):
        tail = bytearray(BULLET_STRIDE - BULLET_SIZE_OFFSET)
        struct.pack_into("<ff", tail, 0, 4.0, 4.0)
        struct.pack_into("<H", tail, BULLET_STATE_OFFSET - BULLET_SIZE_OFFSET, 1)
        struct.pack_into(
            "<H", tail, BULLET_EX_FLAGS_OFFSET - BULLET_SIZE_OFFSET, 0x20
        )
        struct.pack_into(
            "<f", tail, BULLET_ACCEL_SPEED_OFFSET - BULLET_SIZE_OFFSET, -0.025
        )
        struct.pack_into(
            "<f",
            tail,
            BULLET_CURVE_ANGULAR_VELOCITY_OFFSET - BULLET_SIZE_OFFSET,
            0.015,
        )
        struct.pack_into(
            "<i",
            tail,
            BULLET_ACCELERATION_DURATION_OFFSET - BULLET_SIZE_OFFSET,
            128,
        )

        bullet = _decode_bullet_tail(tail, 9)

        self.assertAlmostEqual(bullet.curve_speed_acceleration, -0.025)
        self.assertAlmostEqual(bullet.curve_angular_velocity, 0.015)
        self.assertEqual(bullet.acceleration_duration, 128)

    def test_direction_schedule_without_an_interval_fails_closed(self):
        tail = bytearray(BULLET_STRIDE - BULLET_SIZE_OFFSET)
        struct.pack_into("<ff", tail, 0, 4.0, 4.0)
        struct.pack_into("<H", tail, BULLET_STATE_OFFSET - BULLET_SIZE_OFFSET, 1)
        struct.pack_into(
            "<H", tail, BULLET_EX_FLAGS_OFFSET - BULLET_SIZE_OFFSET, 0x40
        )
        struct.pack_into(
            "<i", tail, BULLET_DIRECTION_MAX_TIMES_OFFSET - BULLET_SIZE_OFFSET, 1
        )

        with self.assertRaisesRegex(NativeDecodeError, "direction schedule"):
            _decode_bullet_tail(tail, 8)

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
            timer=0,
            acceleration_duration=6,
        )
        left, top, right, bottom = hazard_box(bullet, 12)
        self.assertAlmostEqual(left, 85.658, places=3)
        self.assertAlmostEqual(right, 89.658, places=3)
        self.assertAlmostEqual(top, 335.083, places=3)
        self.assertAlmostEqual(bottom, 339.083, places=3)

    def test_curve_acceleration_uses_source_motion_not_all_directions(self):
        bullet = Bullet(
            0.0,
            0.0,
            1.0,
            0.0,
            1.0,
            1.0,
            1,
            ex_flags=0x20,
            speed=1.0,
            angle=0.0,
            timer=0,
            acceleration_duration=2,
            curve_speed_acceleration=0.5,
            curve_angular_velocity=3.141592653589793 / 2.0,
        )

        left, top, right, bottom = hazard_box(bullet, 3)

        self.assertAlmostEqual(left, -5.0)
        self.assertAlmostEqual(right, -3.0)
        self.assertAlmostEqual(top, 0.5)
        self.assertAlmostEqual(bottom, 2.5)

    def test_timed_direction_rotation_uses_source_deceleration(self):
        bullet = Bullet(
            192.0,
            200.0,
            0.0,
            2.9,
            2.5,
            2.5,
            1,
            ex_flags=0x42,
            speed=5.8,
            turn_speed=5.8,
            angle=3.141592653589793 / 2.0,
            timer=10,
            timer_float=10.0,
            direction_interval=20,
            direction_num_times=0,
            direction_max_times=1,
        )

        left, top, right, bottom = hazard_box(bullet, 4)

        self.assertEqual((left, right), (189.5, 194.5))
        self.assertGreater(top, 207.3)
        self.assertLess(bottom, 212.5)

    def test_pickup_delay_branch_rejects_late_escape(self):
        bullet = Bullet(192.0, 371.0, 0.0, 2.0, 2.0, 2.0, 1)
        safe = certify_actions(snapshot(bullet), horizon=5)
        self.assertNotIn(ACTION_BY_VECTOR[(1, 0)], {candidate.action for candidate in safe})

    def test_delivery_plus_pickup_delay_rejects_stale_escape(self):
        # Right escapes when sampled by delay 2, but not after one frame of
        # delivery age plus the measured two-frame native pickup.
        state = snapshot(Bullet(173.5, 380.0, 4.25, 0.0, 2.0, 2.0, 1))
        safe = certify_actions(state, horizon=4)
        self.assertNotIn(ACTION_BY_VECTOR[(1, 0)], {item.action for item in safe})

    def test_release_press_prefix_rejects_unsafe_compound_turn(self):
        down = ACTION_BY_VECTOR[(0, 1)]
        up_left = ACTION_BY_VECTOR[(-1, -1)]
        self.assertEqual(
            tuple(action.name for action in transition_actions(down, up_left)),
            ("stay", "left"),
        )

        # All ordinary current/target pickup paths miss this tiny obstacle;
        # the observed release-down, press-left prefix crosses it.
        state = snapshot(
            Bullet(92.0, 94.5, 0.0, 0.0, 0.25, 0.25, 1),
            x=100.0,
            y=100.0,
            input_mask=BUTTON_FOCUS | 0x20,
        )
        expected = certify_actions(state, horizon=4)
        decision = Solver().decide(state)
        self.assertNotIn(up_left, {item.action for item in expected})
        self.assertEqual(
            {item.action for item in decision.safe_actions},
            {item.action for item in expected},
        )

    def test_empty_stale_set_keeps_a_same_frame_authority(self):
        state = snapshot(
            Bullet(
                191.4767, 364.4699, 0.3829, 2.2426,
                2.0, 1.5, 1, ex_flags=4, speed=2.2751, angle=1.4017,
            ),
            Bullet(
                202.9616, 380.8156, 1.2553, 2.9684,
                2.0, 2.0, 1, ex_flags=4, speed=3.2230, angle=1.1707,
            ),
            input_mask=BUTTON_FOCUS | 0x10,
        )
        fixed = certify_actions(state, HARD_SAFETY_HORIZON)
        same_frame = certify_actions(
            state,
            HARD_SAFETY_HORIZON,
            DELIVERY_DELAYS[:-1],
        )
        decision = Solver().decide(state)

        self.assertFalse(fixed)
        self.assertTrue(same_frame)
        self.assertEqual(decision.reason, "same-frame-delivery-only")
        self.assertIn(decision.action, {item.action for item in same_frame})

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

    def test_dense_scene_reduces_effort_without_changing_hard_authority(self):
        bullets = tuple(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(220)
        )
        state = snapshot(*bullets)

        self.assertEqual(adaptive_horizon(state), 8)
        self.assertEqual(
            {item.action for item in Solver().decide(state).safe_actions},
            {item.action for item in certify_actions(state, HARD_SAFETY_HORIZON)},
        )

    def test_extreme_density_bounds_effort_near_the_hard_horizon(self):
        bullets = tuple(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        )
        state = snapshot(*bullets)
        decision = Solver().decide(state)

        self.assertEqual(adaptive_horizon(state), 6)
        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        self.assertEqual(
            {item.action for item in decision.safe_actions},
            {item.action for item in certify_actions(state, HARD_SAFETY_HORIZON)},
        )

    def test_extreme_density_skips_open_native_effort(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        ))
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (hard, hard)
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(len(hard), len(ACTIONS))
        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        kernel.certify.assert_not_called()

    def test_high_density_publishes_open_hard_authority_first(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(350)
        ))
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (hard, hard)
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(adaptive_horizon(state), 8)
        self.assertEqual(decision.safe_actions, hard)
        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        kernel.certify.assert_not_called()

    def test_high_density_retains_effort_when_a_broad_path_is_close(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(350)
        ))
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        close = (
            SafeAction(
                hard[0].action,
                2.0,
                hard[0].final_x,
                hard[0].final_y,
            ),
        ) + hard[1:]
        effort = close[:-1]
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (close, close)
        kernel.certify.return_value = effort
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(len(close), len(ACTIONS))
        self.assertEqual(decision.effort_horizon, 8)
        kernel.certify.assert_called_once_with(
            state,
            8,
            collision_margin=0.35,
        )

    def test_extreme_density_skips_effort_while_hard_authority_is_broad(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        ))
        broad = certify_actions(state, HARD_SAFETY_HORIZON)[:-1]
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (broad, broad)
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(len(broad), len(ACTIONS) - 1)
        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        kernel.certify.assert_not_called()

    def test_extreme_density_retains_effort_when_hard_set_is_constrained(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        ))
        constrained = certify_actions(state, HARD_SAFETY_HORIZON)[:5]
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (constrained, constrained)
        kernel.certify.return_value = constrained
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.effort_horizon, 6)
        kernel.certify.assert_called_once_with(
            state,
            6,
            collision_margin=0.35,
        )

    def test_extreme_density_publishes_a_narrow_hard_set_immediately(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        ))
        narrow = certify_actions(state, HARD_SAFETY_HORIZON)[:3]
        kernel = mock.Mock()
        kernel.certify_delivery_sets.return_value = (narrow, narrow)
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        kernel.certify.assert_not_called()

    def test_mixed_hazard_density_bounds_adaptive_effort(self):
        bullets = tuple(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(100)
        )
        state = snapshot(*bullets)
        state = Snapshot(
            **{**state.__dict__, "enemies": (enemy_body(x=20.0, y=20.0),)}
        )

        self.assertEqual(adaptive_horizon(state), 12)

    def test_last_viable_frontier_ranks_when_full_proposals_are_empty(self):
        extended = Bullet(
            50.0, 345.0, 0.0, 0.0, 3.0, 3.0, 1, ex_flags=0x01,
        )
        state = snapshot(
            extended,
            x=20.0,
            y=300.0,
            input_mask=BUTTON_FOCUS | 0x20 | BUTTON_LEFT,
        )
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        effort_horizon = adaptive_horizon(state)
        frontier = certify_actions(state, effort_horizon - 2)

        self.assertEqual(effort_horizon, 12)
        self.assertFalse(certify_actions(state, effort_horizon))
        self.assertFalse(certify_actions(state, effort_horizon - 1))
        self.assertFalse(any(
            replanning_scores(
                state,
                hard,
                HARD_SAFETY_HORIZON,
                effort_horizon,
            ).values()
        ))
        self.assertEqual(
            {candidate.action.name for candidate in frontier},
            {"up"},
        )
        decision = Solver().decide(state)
        self.assertEqual(decision.action.name, "up")
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )

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
            0, 0, 120, 30, 10, 0, 0.0, 0, 1, motion_known=True,
        )
        hazard = future_hazards(laser, 1)[0][0]
        self.assertLess(signed_laser_clearance(192.0, 380.0, 1.25, 1.25, hazard), 0.0)
        state = snapshot()
        state = Snapshot(**{**state.__dict__, "laser_count": 1, "lasers": (laser,)})
        decision = Solver().decide(state)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "hard-safe-set-empty")

    def test_observed_laser_rotation_precedes_next_hitbox(self):
        previous = Laser(
            192.0, 116.0, 1.5065950, 64.0, 500.0, 500.0, 24.0, 0.0,
            25, 25, 58, 16, 14, 5, 5.0, 0, 2, slot=3,
        )
        current = Laser(
            192.0, 116.0, 1.5147904, 64.0, 500.0, 500.0, 24.0, 0.0,
            25, 25, 58, 16, 14, 6, 6.0, 0, 2, slot=3,
        )
        tracked = track_motion((previous,), (current,), 1)[0]
        hazard = future_hazards(tracked, 1)[0][0]

        self.assertTrue(tracked.motion_known)
        self.assertAlmostEqual(tracked.angular_velocity, 0.0081954, places=6)
        self.assertLess(
            signed_laser_clearance(198.4020, 393.0986, 1.25, 1.25, hazard),
            0.0,
        )

    def test_long_laser_effort_refines_only_the_soft_proposal(self):
        rotating_warning = Laser(
            192.0, 116.0, 2.2086773, 64.0, 500.0, 500.0, 24.0, 0.0,
            25, 25, 75, 16, 14, 18, 18.0, 0, 0,
            slot=5,
            angular_velocity=-0.0081954,
            motion_known=True,
        )
        state = snapshot(
            x=56.7696,
            y=312.3098,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
            lasers=1,
        )
        state = Snapshot(**{**state.__dict__, "lasers": (rotating_warning,)})

        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        long_laser = certify_actions(state, 24)
        decision = Solver().decide(state)

        self.assertEqual(len(hard), 9)
        self.assertEqual(
            {candidate.action.name for candidate in long_laser},
            {"up", "left", "up_left"},
        )
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )
        self.assertIn(decision.action, {candidate.action for candidate in long_laser})

    def test_empty_mixed_proposal_only_retains_an_existing_laser_corridor(self):
        rotating_warning = Laser(
            192.0, 116.0, 2.2086773, 64.0, 500.0, 500.0, 24.0, 0.0,
            25, 25, 75, 16, 14, 18, 18.0, 0, 0,
            slot=5,
            angular_velocity=-0.0081954,
            motion_known=True,
        )
        extended = Bullet(
            75.0, 290.0, 0.0, 0.0, 3.0, 3.0, 1, ex_flags=0x01,
        )
        state = snapshot(
            extended,
            x=56.7696,
            y=312.3098,
            input_mask=BUTTON_FOCUS | BUTTON_LEFT,
            lasers=1,
        )
        state = Snapshot(**{**state.__dict__, "lasers": (rotating_warning,)})

        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        long_laser = certify_actions(
            Snapshot(**{**state.__dict__, "bullets": ()}),
            24,
        )
        decision = Solver().decide(state)

        self.assertFalse(certify_actions(state, 16))
        self.assertFalse(certify_actions(state, HARD_SAFETY_HORIZON + 1))
        self.assertFalse(any(replanning_scores(state, hard, 4, 16).values()))
        self.assertIn(action_from_input(state.input_mask), {
            candidate.action for candidate in long_laser
        })
        self.assertEqual(decision.action, action_from_input(state.input_mask))
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )

        entering = Snapshot(**{
            **state.__dict__,
            "input_mask": BUTTON_FOCUS | 0x20 | 0x80,
        })
        entering_laser = certify_actions(
            Snapshot(**{**entering.__dict__, "bullets": ()}),
            24,
        )
        entering_decision = Solver().decide(entering)
        self.assertNotIn(entering_decision.action, {
            candidate.action for candidate in entering_laser
        })

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
        state = snapshot(x=374.0, y=416.0)
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

    def test_ranker_egresses_a_wall_before_following_trapped_durability(self):
        state = snapshot(x=374.0, y=432.0, input_mask=BUTTON_FOCUS | 0x20)
        trapped = SafeAction(ACTION_BY_VECTOR[(1, 1)], 20.0, 376.0, 432.0)
        egress = SafeAction(ACTION_BY_VECTOR[(0, -1)], 2.0, 374.0, 430.0)

        chosen = ProposalRanker().choose(
            state,
            (trapped, egress),
            durable_actions=frozenset((trapped.action,)),
        )

        self.assertEqual(chosen, egress)

    def test_ranker_keeps_durability_along_a_noncorner_wall(self):
        state = snapshot(
            x=233.657,
            y=432.0,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
        )
        durable = SafeAction(
            ACTION_BY_VECTOR[(1, 0)], 1.0, 241.657, 432.0
        )
        short_egress = SafeAction(
            ACTION_BY_VECTOR[(1, -1)], 8.0, 239.314, 426.343
        )

        chosen = ProposalRanker().choose(
            state,
            (durable, short_egress),
            durable_actions=frozenset((durable.action,)),
        )

        self.assertEqual(chosen, durable)

    def test_ranker_keeps_the_current_corridor_along_one_wall(self):
        state = snapshot(
            x=184.885,
            y=421.081,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
        )
        right = SafeAction(
            ACTION_BY_VECTOR[(1, 0)], 1.364, 191.13, 425.32
        )
        down_right = SafeAction(
            ACTION_BY_VECTOR[(1, 1)], 3.600, 190.54, 426.74
        )

        chosen = ProposalRanker().choose(
            state,
            (right, down_right),
            durable_actions=frozenset((right.action, down_right.action)),
        )

        self.assertEqual(chosen, down_right)

    def test_ranker_leaves_one_wall_while_the_hard_set_is_open(self):
        state = snapshot(
            x=337.816,
            y=421.348,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
        )
        allowed = certify_actions(state, HARD_SAFETY_HORIZON)
        current = action_from_input(state.input_mask)

        chosen = ProposalRanker().choose(
            state,
            allowed,
            durable_actions=frozenset(
                candidate.action for candidate in allowed
            ),
        )

        self.assertEqual(len(allowed), len(ACTIONS))
        self.assertNotEqual(chosen.action, current)
        self.assertEqual(chosen.action.dy, -1)

    def test_open_hard_set_keeps_margin_before_wall_relief(self):
        state = snapshot(*(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(400)
        ),
            x=192.686,
            y=402.588,
            input_mask=BUTTON_FOCUS | 0x10 | 0x40,
        )
        clearances = (6.986, 5.096, 8.923, 7.292, 7.722, 5.878, 5.369, 8.706, 8.792)
        allowed = tuple(
            SafeAction(
                action,
                clearance,
                state.x + action.dx * 2.0,
                state.y + action.dy * 2.0,
            )
            for action, clearance in zip(ACTIONS, clearances)
        )

        chosen = ProposalRanker().choose(
            state,
            allowed,
            durable_actions=frozenset(ACTIONS),
        )

        self.assertGreaterEqual(chosen.clearance, max(clearances) - 1.0)
        self.assertEqual(chosen.action.dy, 1)

    def test_solver_keeps_a_replanning_corridor_off_one_wall(self):
        state = snapshot(
            x=164.5,
            y=402.697,
            input_mask=BUTTON_FOCUS | 0x80,
        )
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        right = ACTION_BY_VECTOR[(1, 0)]
        down_right = ACTION_BY_VECTOR[(1, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action == down_right
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        kernel.replanning_scores.return_value = {
            right: 1,
            down_right: 2,
        }
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, right)
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )

    def test_solver_prefers_the_stronger_tangent_toward_one_wall(self):
        state = snapshot(
            x=230.51,
            y=401.888,
            input_mask=BUTTON_FOCUS | 0x20,
        )
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        down = ACTION_BY_VECTOR[(0, 1)]
        down_right = ACTION_BY_VECTOR[(1, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action in (down, down_right)
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        kernel.replanning_scores.return_value = {
            down: 1,
            down_right: 2,
        }
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, down_right)
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )

    def test_solver_skips_wall_search_after_hard_authority_narrows(self):
        state = snapshot(
            x=295.078,
            y=401.696,
            input_mask=BUTTON_FOCUS | 0x20,
        )
        all_hard = certify_actions(state, HARD_SAFETY_HORIZON)
        down = ACTION_BY_VECTOR[(0, 1)]
        constrained = tuple(
            candidate for candidate in all_hard
            if candidate.action.name in (
                "stay", "up", "down", "right", "up_right", "down_right"
            )
        )
        descending = tuple(
            candidate for candidate in constrained
            if candidate.action == down
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            constrained,
            descending,
            constrained,
        )
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(len(constrained), 6)
        self.assertEqual(decision.action, down)
        kernel.replanning_scores.assert_not_called()

    def test_solver_skips_wall_search_with_multiple_enemy_bodies(self):
        state = snapshot(
            x=99.064,
            y=400.378,
            input_mask=BUTTON_FOCUS | 0x20,
        )
        state = Snapshot(**{
            **state.__dict__,
            "enemies": tuple(
                enemy_body(x=20.0 + index * 20.0, y=40.0)
                for index in range(4)
            ),
        })
        hard = certify_actions(snapshot(), HARD_SAFETY_HORIZON)
        down = ACTION_BY_VECTOR[(0, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action == down
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, down)
        kernel.replanning_scores.assert_not_called()

    def test_solver_uses_a_tied_replan_to_leave_a_bullet_corner(self):
        state = snapshot(
            x=38.703,
            y=401.880,
            input_mask=BUTTON_FOCUS | 0x20 | 0x80,
        )
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        down = ACTION_BY_VECTOR[(0, 1)]
        down_left = ACTION_BY_VECTOR[(-1, 1)]
        down_right = ACTION_BY_VECTOR[(1, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action == down
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        kernel.replanning_scores.return_value = {
            down: 1,
            down_left: 1,
            down_right: 1,
        }
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, down_right)
        self.assertEqual(
            {candidate.action for candidate in decision.safe_actions},
            {candidate.action for candidate in hard},
        )

    def test_solver_starts_corner_search_one_hard_segment_early(self):
        state = snapshot(
            *(
                Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
                for _ in range(100)
            ),
            x=47.35,
            y=392.46,
            input_mask=BUTTON_FOCUS | 0x20 | 0x40,
        )
        state = Snapshot(**{
            **state.__dict__,
            "enemies": (enemy_body(x=192.0, y=128.0),),
        })
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        down = ACTION_BY_VECTOR[(0, 1)]
        left = ACTION_BY_VECTOR[(-1, 0)]
        up_left = ACTION_BY_VECTOR[(-1, -1)]
        down_left = ACTION_BY_VECTOR[(-1, 1)]
        down_right = ACTION_BY_VECTOR[(1, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action in (down, left)
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        kernel.replanning_scores.return_value = {
            down: 1,
            left: 1,
            up_left: 1,
            down_left: 2,
            down_right: 1,
        }
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, down_right)
        self.assertEqual(len(decision.safe_actions), len(ACTIONS))
        kernel.replanning_scores.assert_called_once()

    def test_solver_starts_single_wall_search_one_hard_segment_early(self):
        state = snapshot(
            *(
                Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
                for _ in range(100)
            ),
            x=79.69,
            y=392.15,
            input_mask=BUTTON_FOCUS | 0x20 | 0x40,
        )
        state = Snapshot(**{
            **state.__dict__,
            "enemies": (enemy_body(x=192.0, y=128.0),),
        })
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        stay = ACTION_BY_VECTOR[(0, 0)]
        down = ACTION_BY_VECTOR[(0, 1)]
        left = ACTION_BY_VECTOR[(-1, 0)]
        right = ACTION_BY_VECTOR[(1, 0)]
        down_left = ACTION_BY_VECTOR[(-1, 1)]
        down_right = ACTION_BY_VECTOR[(1, 1)]
        descending = tuple(
            candidate for candidate in hard
            if candidate.action in (down, down_left, down_right)
        )
        kernel = mock.Mock()
        kernel.certify_pair_with_age_zero.return_value = (
            hard,
            descending,
            hard,
        )
        kernel.replanning_scores.return_value = {
            stay: 3,
            down: 6,
            left: 4,
            right: 3,
            down_left: 6,
            down_right: 5,
        }
        solver = Solver()
        solver.kernel = kernel

        decision = solver.decide(state)

        self.assertEqual(decision.action, right)
        self.assertEqual(len(decision.safe_actions), len(ACTIONS))
        kernel.replanning_scores.assert_called_once()

    def test_ranker_turns_inward_before_delivery_reaches_a_corner(self):
        state = snapshot(
            x=21.314,
            y=407.373,
            input_mask=BUTTON_FOCUS | 0x20 | 0x40,
        )
        trapped = SafeAction(
            ACTION_BY_VECTOR[(-1, 1)], 40.0, 10.0, 418.686
        )
        inward = SafeAction(
            ACTION_BY_VECTOR[(1, 0)], 1.0, 19.071, 411.615
        )

        chosen = ProposalRanker().choose(
            state,
            (trapped, inward),
            durable_actions=frozenset((trapped.action, inward.action)),
        )

        self.assertEqual(chosen, inward)

    def test_replanning_proposal_can_turn_after_a_hard_safe_first_segment(self):
        state = snapshot(Bullet(190.5, 369.0, 1.0, 1.0, 2.0, 2.0, 1))
        candidates = certify_actions(state, HARD_SAFETY_HORIZON)
        right = ACTION_BY_VECTOR[(1, 0)]
        self.assertIn(right, {candidate.action for candidate in candidates})
        self.assertNotIn(right, {candidate.action for candidate in certify_actions(state, 8)})

        scores = replanning_scores(state, candidates)

        self.assertGreater(scores[right], 0)
        chosen = ProposalRanker().choose(
            state,
            candidates,
            repairable_actions=frozenset((right,)),
        )
        self.assertEqual(chosen.action, right)

    def test_replanning_proposal_covers_delivery_and_pickup_delays(self):
        state = snapshot(
            Bullet(
                1.96, 387.60, -1.670, -1.338, 2.0, 2.0, 1,
                ex_flags=4, speed=2.140, turn_speed=2.140, angle=3.817,
            ),
            Bullet(
                12.49, 422.61, -0.830, -3.381, 4.0, 4.0, 1,
                ex_flags=4, speed=3.481, turn_speed=3.481, angle=4.472,
            ),
            Bullet(
                27.59, 437.31, 0.113, -1.322, 4.0, 3.0, 1,
                ex_flags=4, speed=1.326, turn_speed=1.326, angle=4.797,
            ),
            x=10.25,
            y=405.0,
            input_mask=BUTTON_FOCUS | 0x10 | BUTTON_LEFT,
        )
        candidates = certify_actions(state, HARD_SAFETY_HORIZON)
        scores = replanning_scores(state, candidates)

        # Right is now rejected by hard transition-prefix coverage.  Among
        # the remaining hard candidates, only up-right retains a continuation
        # across both command delivery windows and their observable prefixes.
        self.assertNotIn(
            ACTION_BY_VECTOR[(1, 0)],
            {candidate.action for candidate in candidates},
        )
        self.assertEqual(scores[ACTION_BY_VECTOR[(1, -1)]], 1)

    def test_selective_repair_proposal_survives_one_hard_segment(self):
        ranker = ProposalRanker()
        right = ACTION_BY_VECTOR[(1, 0)]
        down = ACTION_BY_VECTOR[(0, 1)]
        right_candidate = SafeAction(right, 1.0, 194.0, 380.0)
        down_candidate = SafeAction(down, 10.0, 192.0, 382.0)
        state = snapshot()

        chosen = ranker.choose(
            state,
            (right_candidate, down_candidate),
            repairable_actions=frozenset((right,)),
            repair_span=HARD_SAFETY_HORIZON,
        )
        self.assertEqual(chosen.action, right)

        continued_state = Snapshot(**{**state.__dict__, "frame": state.frame + 1})
        chosen = ranker.choose(continued_state, (right_candidate, down_candidate))
        self.assertEqual(chosen.action, right)

        expired_state = Snapshot(
            **{**state.__dict__, "frame": state.frame + HARD_SAFETY_HORIZON}
        )
        chosen = ranker.choose(expired_state, (right_candidate, down_candidate))
        self.assertEqual(chosen.action, down)

        veto_ranker = ProposalRanker()
        veto_ranker.choose(
            state,
            (right_candidate, down_candidate),
            repairable_actions=frozenset((right,)),
        )
        chosen = veto_ranker.choose(continued_state, (down_candidate,))
        self.assertEqual(chosen.action, down)

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

    def test_replanning_score_ranks_but_cannot_add_an_action(self):
        stay = SafeAction(ACTION_BY_VECTOR[(0, 0)], 2.0, 192.0, 380.0)
        right = SafeAction(ACTION_BY_VECTOR[(1, 0)], 1.0, 194.0, 380.0)

        class ReplanningKernel:
            def certify_pair(self, _snapshot, _hard, _effort, collision_margin):
                self.assertEqual(collision_margin, 0.35)
                return (stay, right), ()

            def replanning_scores(
                self, _snapshot, candidates, split, horizon, collision_margin
            ):
                self.assertEqual(candidates, (stay, right))
                self.assertEqual((split, horizon, collision_margin), (4, 8, 0.35))
                return {stay.action: 0, right.action: 3}

            assertEqual = self.assertEqual

        solver = Solver()
        solver.kernel = ReplanningKernel()
        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, right.action)
        self.assertEqual(decision.safe_actions, (stay, right))
        self.assertEqual(decision.repairable_count, 1)

    def test_replanning_uses_the_allocated_adaptive_horizon(self):
        stay = SafeAction(ACTION_BY_VECTOR[(0, 0)], 2.0, 192.0, 380.0)

        class ReplanningKernel:
            def certify_pair(
                self, _snapshot, _hard, effort, collision_margin
            ):
                self.assertEqual(collision_margin, 0.35)
                self.effort = effort
                return (stay,), ()

            def replanning_scores(
                self, _snapshot, _candidates, split, horizon, collision_margin
            ):
                self.assertEqual(collision_margin, 0.35)
                self.repair = (split, horizon)
                return {stay.action: 1}

            assertEqual = self.assertEqual

        state = snapshot()
        state = Snapshot(**{**state.__dict__, "enemies": (enemy_body(x=20.0, y=20.0),)})
        solver = Solver()
        solver.kernel = ReplanningKernel()

        solver.decide(state)

        self.assertEqual(solver.kernel.effort, 16)
        self.assertEqual(solver.kernel.repair, (HARD_SAFETY_HORIZON, 16))

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
