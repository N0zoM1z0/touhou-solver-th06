import os
import unittest
import struct
from unittest import mock

from th06.model import (
    ACTION_BY_VECTOR,
    ACTIONS,
    BUTTON_BOMB,
    BUTTON_DOWN,
    BUTTON_FOCUS,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_SHOOT,
    CONTROL_ACTIONS,
    FAST_ACTIONS,
    FAST_ACTION_BY_VECTOR,
    Bullet,
    EnemyBody,
    EclInstruction,
    Laser,
    SafeAction,
    Snapshot,
    action_from_input,
)
from th06.ranking import ProposalRanker
from th06.safety import DELIVERY_DELAYS, certify_actions, transition_actions
from th06.hazards.bullets import hazard_box, hazards_by_frame as bullet_hazards_by_frame
from th06.hazards.enemies import future_boxes as future_enemy_boxes
from th06.hazards.lasers import future_hazards, signed_laser_clearance, track_motion
from th06.kernels.safety import NativeSafetyKernel
from th06.solver import HARD_SAFETY_HORIZON, Solver
from th06.actuator import Keyboard
from th06.dialogue import DialogueSkipper
from th06.input_lease import (
    InputLease,
    bounded_delivery_age,
    covered_current_retry,
)
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
    stop_trial_now,
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
        self.assertEqual(action_from_input(BUTTON_LEFT).name, "left_fast")
        self.assertEqual(
            action_from_input(BUTTON_FOCUS | BUTTON_LEFT).name,
            "left",
        )

    def test_bomb_is_never_an_action(self):
        self.assertEqual(BUTTON_BOMB, 0x02)
        self.assertNotIn("bomb", {action.name for action in CONTROL_ACTIONS})
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

    def test_fast_transition_releases_focus_without_a_bomb_mapping(self):
        keyboard = object.__new__(Keyboard)
        keyboard.held = {"shoot", "focus", "left"}
        keyboard.base_desired = {"shoot", "focus", "left"}
        keyboard.auxiliary_desired = set()
        keyboard.suppressed = set()
        batches = []
        keyboard._events = lambda events: batches.append(events)

        events = keyboard.apply(FAST_ACTION_BY_VECTOR[(1, 0)])

        self.assertEqual(
            events,
            (("focus", False), ("left", False), ("right", True)),
        )
        self.assertEqual(batches, [events])
        self.assertEqual(keyboard.base_input_mask, BUTTON_SHOOT | 0x80)
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
        self.assertTrue(covered_current_retry(10, 15, 6, down, safe))
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

    def test_terminal_trial_releases_input_before_exact_process_stop(self):
        events = []
        keyboard = mock.Mock()
        process = mock.Mock()
        keyboard.release_all.side_effect = lambda: events.append("release")
        process.terminate.side_effect = lambda: events.append("terminate")

        stop_trial_now(process, keyboard, True)

        self.assertEqual(events, ["release", "terminate"])

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
        self.assertEqual(
            bullet_hazards_by_frame(snapshot(bullet), 3)[-1][0],
            (left, top, right, bottom),
        )

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
        self.assertEqual(
            bullet_hazards_by_frame(snapshot(bullet), 4)[-1][0],
            (left, top, right, bottom),
        )

    def test_bulk_bullet_projection_matches_single_frame_reference(self):
        bullets = (
            Bullet(20.0, 30.0, 1.0, -0.5, 2.0, 3.0, 1),
            Bullet(40.0, 50.0, -2.0, 1.0, 2.0, 2.0, 2),
            Bullet(
                80.0, 90.0, 1.0, 2.0, 2.0, 2.0, 1,
                ex_flags=0x10,
                acceleration_x=0.25,
                acceleration_y=-0.5,
                acceleration_duration=4,
            ),
            Bullet(
                120.0, 140.0, -1.0, 0.5, 3.0, 3.0, 1,
                ex_flags=0x100,
                speed=2.0,
                turn_speed=3.0,
                acceleration=0.1,
            ),
        )

        actual = bullet_hazards_by_frame(snapshot(*bullets), 6)

        self.assertEqual(actual, [
            tuple(hazard_box(bullet, frame) for bullet in bullets)
            for frame in range(1, 7)
        ])

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



    def test_fast_action_uses_source_normal_movement_speed(self):
        state = snapshot(x=192.0, y=380.0)
        focused = certify_actions(
            state,
            2,
            (0,),
            actions=(ACTION_BY_VECTOR[(-1, 0)],),
        )[0]
        fast = certify_actions(
            state,
            2,
            (0,),
            actions=(FAST_ACTION_BY_VECTOR[(-1, 0)],),
        )[0]

        self.assertEqual(focused.final_x, 188.0)
        self.assertEqual(fast.final_x, 184.0)

    def test_native_fast_action_matches_the_reference_speed_model(self):
        if os.name != "nt":
            self.skipTest("native kernel is loaded only by Windows Python")
        state = snapshot(x=192.0, y=380.0)
        action = FAST_ACTION_BY_VECTOR[(-1, 0)]
        expected = certify_actions(state, 2, (0, 1, 2, 3), actions=(action,))
        actual = NativeSafetyKernel().certify_selected(
            state,
            2,
            (action,),
            collision_margin=0.35,
        )

        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].action, expected[0].action)
        self.assertAlmostEqual(actual[0].final_x, expected[0].final_x, places=5)

    def test_ecl_graph_budget_prioritizes_direct_fallthrough(self):
        start = EclInstruction(
            0x1000,
            0,
            116,
            16,
            0xFF,
            (bytes(12) + struct.pack("<i", 0)).hex(),
        )
        fallthrough = EclInstruction(
            0x1010, -1, 0, 12, 0xFF, bytes(12).hex()
        )
        instructions = {start.address: start, fallthrough.address: fallthrough}
        for index in range(native.ECL_PROGRAM_INSTRUCTION_LIMIT + 2):
            address = 0x2000 + index * 12
            instructions[address] = EclInstruction(
                address,
                0 if index <= native.ECL_PROGRAM_INSTRUCTION_LIMIT else -1,
                0,
                12,
                0xFF,
                bytes(12).hex(),
            )

        process = type("Process", (), {
            "ecl_subroutines": (0x2000,),
            "read_ecl_instruction": lambda _self, address: instructions[address],
        })()

        program = native._read_ecl_program(process, start.address)

        self.assertIn(fallthrough.address, {
            instruction.address for instruction in program
        })

    def test_native_spatial_replanning_matches_reference_scores(self):
        if os.name != "nt":
            self.skipTest("native kernel is loaded only by Windows Python")
        state = snapshot(
            Bullet(31.5, 376.0, 0.0, 0.8, 2.0, 2.0, 1),
            Bullet(64.5, 380.0, -1.0, 0.0, 4.0, 3.0, 1),
            x=34.0,
            y=380.0,
            input_mask=BUTTON_FOCUS | BUTTON_LEFT,
        )
        candidates = certify_actions(state, HARD_SAFETY_HORIZON)

        expected = replanning_scores(state, candidates, split=4, horizon=8)
        actual = NativeSafetyKernel().replanning_scores(
            state,
            candidates,
            split=4,
            horizon=8,
            collision_margin=0.35,
        )

        self.assertEqual(actual, expected)

    def test_replanning_counts_unique_reachable_corner_states(self):
        state = snapshot(x=376.0, y=432.0)
        candidates = certify_actions(state, HARD_SAFETY_HORIZON)

        scores = replanning_scores(state, candidates, split=4, horizon=8)

        self.assertEqual(scores[ACTION_BY_VECTOR[(-1, -1)]], 9)
        self.assertEqual(scores[ACTION_BY_VECTOR[(0, 0)]], 6)
        self.assertEqual(scores[ACTION_BY_VECTOR[(1, 0)]], 6)
        self.assertEqual(scores[ACTION_BY_VECTOR[(0, 1)]], 6)
        if os.name == "nt":
            kernel = NativeSafetyKernel()
            self.assertEqual(
                kernel.replanning_scores(state, candidates, 4, 8, 0.35),
                scores,
            )
            self.assertEqual(
                kernel.nominal_policy_counts(state, candidates, 4, 8, 0.35),
                scores,
            )















    def test_native_dense_followup_reuses_the_prepared_hazards(self):
        state = snapshot()
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        held = action_from_input(state.input_mask)
        held_effort = tuple(
            candidate for candidate in hard if candidate.action == held
        )
        prepared = object()
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepared_snapshot = None
        kernel._prepared_horizon = 0
        kernel._prepared_hazards = None
        kernel._prepare = mock.Mock(return_value=prepared)
        kernel._certify_prepared = mock.Mock(side_effect=(
            (hard, hard, ()),
            (held_effort, (), ()),
            (hard, (), ()),
        ))

        combined = kernel.certify_delivery_sets_with_selected(
            state,
            HARD_SAFETY_HORIZON,
            6,
            (held,),
            collision_margin=0.35,
        )
        effort = kernel.certify(state, 6, collision_margin=0.35)

        self.assertEqual(combined, (hard, hard, held_effort))
        self.assertEqual(effort, hard)
        kernel._prepare.assert_called_once_with(state, 6)

    def test_native_fast_pair_prepares_the_long_horizon_once(self):
        state = snapshot()
        fast_hard = certify_actions(
            state,
            HARD_SAFETY_HORIZON,
            actions=FAST_ACTIONS,
        )
        fast_long = fast_hard[:3]
        prepared = object()
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepared_snapshot = None
        kernel._prepared_horizon = 0
        kernel._prepared_hazards = None
        kernel._prepare = mock.Mock(return_value=prepared)
        kernel._certify_prepared = mock.Mock(side_effect=(
            (fast_hard, (), ()),
            (fast_long, (), ()),
        ))

        actual = kernel.certify_selected_pair(
            state,
            HARD_SAFETY_HORIZON,
            40,
            FAST_ACTIONS,
            collision_margin=0.35,
        )

        self.assertEqual(actual, (fast_hard, fast_long))
        kernel._prepare.assert_called_once_with(state, 40)
        self.assertEqual(kernel._certify_prepared.call_count, 2)

    def test_native_held_frontier_reuses_the_effort_hazards(self):
        state = snapshot()
        held = action_from_input(state.input_mask)
        prepared = object()
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepared_snapshot = state
        kernel._prepared_horizon = 8
        kernel._prepared_hazards = prepared
        kernel._prepare = mock.Mock()
        kernel._certify_prepared = mock.Mock(side_effect=(
            ((), (), ()),
            ((), (), ()),
            ((SafeAction(held, 1.0, state.x, state.y),), (), ()),
        ))

        horizon = kernel.longest_selected_horizon(
            state,
            5,
            7,
            (held,),
            collision_margin=0.35,
        )

        self.assertEqual(horizon, 5)
        kernel._prepare.assert_not_called()
        self.assertEqual(kernel._certify_prepared.call_count, 3)









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

    def test_new_short_laser_uses_an_angle_independent_hard_bound(self):
        laser = Laser(
            190.04, 106.99, 1.28, 0.0, 4.0, 192.0, 6.0, 4.0,
            0, 0, 9999, 30, 30, 1, 1.0, 0, 1, slot=0,
        )
        state = snapshot(x=274.62, y=391.88, lasers=1)
        state = Snapshot(**{**state.__dict__, "lasers": (laser,)})

        decision = Solver().decide(state)

        self.assertIsNotNone(decision.action)
        self.assertNotEqual(decision.reason, "unsupported-laser-motion")

    def test_unknown_laser_motion_fails_closed_when_its_envelope_can_reach(self):
        laser = Laser(
            192.0, 380.0, 0.0, 0.0, 384.0, 384.0, 16.0, 0.0,
            0, 0, 120, 30, 10, 0, 0.0, 0, 1,
        )
        state = snapshot(lasers=1)
        state = Snapshot(**{**state.__dict__, "lasers": (laser,)})

        decision = Solver().decide(state)

        self.assertIsNone(decision.action)
        self.assertEqual(decision.reason, "unsupported-laser-motion")

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



if __name__ == "__main__":
    unittest.main()
