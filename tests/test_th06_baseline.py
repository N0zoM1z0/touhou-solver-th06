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
    MessageInstruction,
    SafeAction,
    Snapshot,
    StageTimelineInstruction,
    action_from_input,
)
from th06.ranking import ProposalRanker
from th06.safety import DELIVERY_DELAYS, certify_actions, transition_actions
from th06.hazards.bullets import (
    _may_reach_player,
    extend_reachable_hazards_by_frame,
    extend_hazards_by_frame as extend_bullet_hazards_by_frame,
    hazard_box,
    hazards_by_frame as bullet_hazards_by_frame,
    reachable_hazards_by_frame,
)
from th06.hazards.enemies import future_boxes as future_enemy_boxes
from th06.hazards.lasers import (
    LaserHazard,
    future_hazards,
    signed_laser_clearance,
    track_motion,
)
from th06.hazards.world import (
    WorldBirthForecast,
    WorldForecastContinuation,
)
from th06.kernels.safety import NativeSafetyKernel
from th06.solver import (
    HARD_CURRENT_HOLD_HORIZON,
    HARD_SAFETY_HORIZON,
    Solver,
)
from th06.actuator import Keyboard
from th06.dialogue import DialogueSkipper
from th06.input_lease import (
    InputLease,
    bounded_delivery_age,
    covered_current_retry,
)
from th06.agent import authority_unavailable, parse_args
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
    BULLET_IS_GRAZED_OFFSET,
    BULLET_SIZE_OFFSET,
    BULLET_STATE_OFFSET,
    BULLET_STRIDE,
    ENEMY_MANAGER_SIZE,
    NativeDecodeError,
    PROCESS_ACCESS,
    RESULT_SCREEN_ON_UPDATE,
    _current_message_waits,
    _decode_bullet_tail,
    _message_opening_guarantees_wait,
    _message_minimum_waits,
    _read_message_program,
    _read_stage_timeline,
    _timeline_subroutine_traits,
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
    def test_loaded_message_program_is_decoded_and_cached(self):
        msg_file = 0x10000
        program_address = 0x11000
        wait = struct.pack("<HBBi", 0, 4, 4, 120)
        delete = struct.pack("<HBB", 1, 0, 0)
        regions = {
            msg_file: struct.pack("<iI", 1, program_address),
            program_address: wait + delete,
        }

        class Process:
            message_program_cache = {}

            def __init__(self):
                self.reads = 0

            def read(self, address, size):
                self.reads += 1
                for start, data in regions.items():
                    if start <= address and address + size <= start + len(data):
                        offset = address - start
                        return data[offset:offset + size]
                raise AssertionError(f"unexpected read 0x{address:x}+{size}")

        process = Process()
        program = _read_message_program(process, msg_file, 0)
        first_read_count = process.reads

        self.assertEqual(
            [(item.time, item.opcode, item.arg_size) for item in program],
            [(0, 4, 4), (1, 0, 0)],
        )
        self.assertIs(_read_message_program(process, msg_file, 0), program)
        self.assertEqual(process.reads, first_read_count)

    def test_message_opening_bound_assumes_fastest_wait_skip(self):
        skippable = MessageInstruction(
            0x1000, 0, 13, 4, struct.pack("<HBBi", 0, 13, 4, 1).hex()
        )
        wait = MessageInstruction(
            0x1008, 0, 4, 4, struct.pack("<HBBi", 0, 4, 4, 120).hex()
        )
        delete = MessageInstruction(
            0x1010, 0, 0, 0, struct.pack("<HBB", 0, 0, 0).hex()
        )
        resume = MessageInstruction(
            0x1020, 0, 6, 0, struct.pack("<HBB", 0, 6, 0).hex()
        )
        later = MessageInstruction(
            0x1024, 1, 0, 0, struct.pack("<HBB", 1, 0, 0).hex()
        )

        self.assertFalse(_message_opening_guarantees_wait(
            (skippable, wait, delete), skip_pressed=False
        ))
        self.assertFalse(_message_opening_guarantees_wait(
            (skippable, wait, delete), skip_pressed=True
        ))
        self.assertEqual(_message_minimum_waits((resume, later)), 0)

    def test_message_time_groups_bound_fastest_dialogue_release(self):
        program = (
            MessageInstruction(
                0x2000, 0, 1, 0, struct.pack("<HBB", 0, 1, 0).hex()
            ),
            MessageInstruction(
                0x2004, 0, 13, 4,
                struct.pack("<HBBi", 0, 13, 4, 0).hex(),
            ),
            MessageInstruction(
                0x200C, 60, 3, 0, struct.pack("<HBB", 60, 3, 0).hex()
            ),
            MessageInstruction(
                0x2010, 150, 3, 0, struct.pack("<HBB", 150, 3, 0).hex()
            ),
            MessageInstruction(
                0x2014, 240, 0, 0, struct.pack("<HBB", 240, 0, 0).hex()
            ),
        )

        self.assertEqual(_message_minimum_waits(program), 240)
        self.assertEqual(
            _message_minimum_waits(
                program,
                current_instruction=program[3].address,
                timer=150,
                dialogue_skippable=False,
            ),
            90,
        )
        process = type("Process", (), {
            "message_program_cache": {(0x10000, 0): program}
        })()
        self.assertEqual(
            _current_message_waits(
                process, 0x10000, 0, program[0].address, 0,
                0, 0, True,
            ),
            240,
        )

    def test_message_wait_uses_source_eight_frame_shoot_floor(self):
        wait = MessageInstruction(
            0x3000, 0, 4, 4, struct.pack("<HBBi", 0, 4, 4, 120).hex()
        )
        delete = MessageInstruction(
            0x3008, 0, 0, 0, struct.pack("<HBB", 0, 0, 0).hex()
        )

        self.assertEqual(
            _message_minimum_waits(
                (wait, delete),
                dialogue_skippable=False,
            ),
            8,
        )

    def test_source_stage_timeline_is_decoded_and_cached_by_pointer(self):
        first = struct.pack("<hhhh", 100, 7, 4, 0x18) + bytes(0x10)
        second = struct.pack("<hhhh", 120, 8, 9, 0x08)
        sentinel = struct.pack("<hhhh", -1, 0, 0, 0)
        memory = first + second + sentinel

        class Process:
            ecl_timeline_instruction_cache = {}
            ecl_timeline_cache = {}

            def __init__(self):
                self.reads = 0

            def read(self, address, size):
                self.reads += 1
                offset = address - 0x10000
                return memory[offset:offset + size]

        process = Process()
        decoded = _read_stage_timeline(process, 0x10000)
        first_read_count = process.reads

        self.assertEqual(
            [(item.time, item.arg0, item.opcode, item.size) for item in decoded],
            [(100, 7, 4, 0x18), (120, 8, 9, 0x08), (-1, 0, 0, 0)],
        )
        self.assertEqual(decoded[1].raw_hex, second.hex())
        self.assertIs(_read_stage_timeline(process, 0x10000), decoded)
        self.assertEqual(process.reads, first_read_count)

    def test_timeline_subroutine_traits_are_source_graph_properties(self):
        timeline = (
            StageTimelineInstruction(0x3000, 10, 0, 0, 8, "00" * 8),
            StageTimelineInstruction(0x3008, 20, 1, 0, 8, "00" * 8),
        )
        emitter = EclInstruction(0x1000, 0, 76, 16, 0xFF, "00" * 16)
        boss_raw = bytearray(16)
        struct.pack_into("<i", boss_raw, 0x0C, 0)
        boss = EclInstruction(0x2000, 0, 101, 16, 0xFF, boss_raw.hex())

        class Process:
            ecl_subroutines = (0x1000, 0x2000)
            ecl_subroutine_traits = {}

        process = Process()
        with mock.patch.object(
            native,
            "_read_ecl_program",
            side_effect=((emitter,), (boss,)),
        ) as read_program:
            emitter_subs, boss_subs = _timeline_subroutine_traits(
                process, timeline
            )
            cached = _timeline_subroutine_traits(process, timeline)

        self.assertEqual(emitter_subs, (0,))
        self.assertEqual(boss_subs, (1,))
        self.assertEqual(cached, (emitter_subs, boss_subs))
        self.assertEqual(read_program.call_count, 2)

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

    def test_snapshot_read_retries_an_incomplete_calc_phase(self):
        coherent_state = Snapshot(**{**snapshot().__dict__, "frame": 2})
        process = object()

        with mock.patch.object(
            native,
            "read_game_frame",
            side_effect=(2, 2, 2),
        ), mock.patch.object(
            native,
            "_read_snapshot_once",
            side_effect=(
                native._SnapshotPhaseIncomplete(2, 1),
                coherent_state,
            ),
        ):
            coherent = native.read_snapshot(process)

        self.assertIs(coherent, coherent_state)

    def test_snapshot_read_retries_a_torn_boss_publication(self):
        coherent_state = Snapshot(**{**snapshot().__dict__, "frame": 2})
        process = object()

        with mock.patch.object(
            native,
            "read_game_frame",
            side_effect=(2, 2, 2),
        ), mock.patch.object(
            native,
            "_read_snapshot_once",
            side_effect=(
                native._SnapshotReadTorn(
                    "incoherent boss pointer at enemy slot 0"
                ),
                coherent_state,
            ),
        ):
            coherent = native.read_snapshot(process)

        self.assertIs(coherent, coherent_state)

    def test_snapshot_pool_phase_witness_rejects_cross_manager_tear(self):
        game = bytearray(
            native.GAME_STAGE_OFFSET + 4 - native.GAME_FLAGS_OFFSET
        )
        struct.pack_into(
            "<I",
            game,
            native.GAME_FRAMES_OFFSET - native.GAME_FLAGS_OFFSET,
            3063,
        )
        struct.pack_into(
            "<i",
            game,
            native.GAME_STAGE_OFFSET - native.GAME_FLAGS_OFFSET,
            1,
        )
        pool_start = native.ADDR_ENEMY_MANAGER + native.ENEMY_ARRAY_OFFSET
        pool_end = native.ADDR_BULLET_MANAGER + native.BULLET_MANAGER_SIZE
        pools = bytearray(pool_end - pool_start)
        bullet_timer = native.ADDR_BULLET_MANAGER - pool_start
        bullet_timer += native.BULLET_MANAGER_TIME_OFFSET
        struct.pack_into("<ifi", pools, bullet_timer, 3062, 0.0, 3063)

        class Process:
            ecl_cache_stage = 1

            @staticmethod
            def read(address, _size):
                if address == native.ADDR_GAME_MANAGER + native.GAME_FLAGS_OFFSET:
                    return bytes(game)
                if address == (
                    native.ADDR_BULLET_MANAGER
                    + native.BULLET_MANAGER_TIME_OFFSET
                    + 8
                ):
                    return struct.pack("<i", 3062)
                if address == pool_start:
                    return bytes(pools)
                if address == native.ADDR_ECL_EX_TABLE:
                    return bytes(native.ECL_EX_COUNT * 4)
                raise AssertionError(f"unexpected read at 0x{address:08X}")

        with self.assertRaisesRegex(
            native._SnapshotReadTorn,
            "3062->3063",
        ):
            native._read_snapshot_once(Process())

    def test_stale_timeline_boss_pointer_does_not_make_nonboss_incoherent(self):
        enemy_pool = bytearray(
            native.ENEMY_STRIDE * native.ENEMY_COUNT
        )
        boss_slots = (0,) + (-1,) * 7

        boss_id = native._decode_enemy_boss_id(
            enemy_pool, 0, 0, False, boss_slots
        )

        self.assertEqual(boss_id, -1)

    def test_true_boss_requires_its_own_id_pointer_to_be_published(self):
        enemy_pool = bytearray(
            native.ENEMY_STRIDE * native.ENEMY_COUNT
        )
        enemy_pool[native.ENEMY_BOSS_ID_OFFSET] = 3

        self.assertEqual(
            native._decode_enemy_boss_id(
                enemy_pool,
                0,
                0,
                True,
                (-1, -1, -1, 0, -1, -1, -1, -1),
            ),
            3,
        )
        with self.assertRaises(native._SnapshotReadTorn):
            native._decode_enemy_boss_id(
                enemy_pool, 0, 0, True, (-1,) * 8
            )

    def test_snapshot_epoch_excludes_local_decode_work(self):
        state = Snapshot(**{**snapshot().__dict__, "frame": 7})
        process = object()
        events = []

        def captured_then_decoded(_process, capture_epoch, _retries):
            capture_epoch(state.frame)
            events.append("decoded")
            return state

        with mock.patch.object(
            native,
            "read_game_frame",
            side_effect=lambda _process: events.append("epoch") or 7,
        ) as frame_reads, mock.patch.object(
            native,
            "_read_snapshot_once",
            side_effect=captured_then_decoded,
        ):
            coherent = native.read_snapshot(process)

        self.assertIs(coherent, state)
        self.assertEqual(events, ["epoch", "epoch", "decoded"])
        self.assertEqual(frame_reads.call_count, 2)

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

    def test_hard_authority_reserves_one_current_hold_retry_frame(self):
        state = snapshot()
        decision = Solver(decision_budget_ms=1e-9).decide(state)
        current = action_from_input(state.input_mask)

        self.assertEqual(decision.horizon, HARD_SAFETY_HORIZON)
        self.assertGreaterEqual(
            decision.held_horizon,
            HARD_CURRENT_HOLD_HORIZON,
        )
        self.assertTrue(
            covered_current_retry(
                state.frame,
                state.frame + HARD_SAFETY_HORIZON,
                decision.held_horizon,
                current,
                decision.safe_actions,
            )
        )

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

    def test_full_stage_diagnostic_is_an_explicit_option(self):
        args = parse_args((
            "--armed",
            "--patch-lives",
            "--practice-stage",
            "1",
            "--continue-on-failure",
        ))
        self.assertTrue(args.continue_on_failure)

    def test_history_capture_is_an_explicit_diagnostic_option(self):
        args = parse_args(("--stop-game", "--capture-history"))

        self.assertTrue(args.capture_history)

    def test_diagnostic_rng_seed_accepts_source_u16_notation(self):
        args = parse_args((
            "--armed",
            "--practice-stage",
            "5",
            "--rng-seed",
            "0x1234",
        ))
        self.assertEqual(args.rng_seed, 0x1234)

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
        tail[BULLET_IS_GRAZED_OFFSET - BULLET_SIZE_OFFSET] = 1

        bullet = _decode_bullet_tail(tail, 271)

        self.assertEqual((bullet.x, bullet.y), (123.0, 234.0))
        self.assertEqual((bullet.half_width, bullet.half_height), (2.0, 3.0))
        self.assertTrue(bullet.is_grazed)

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

    def test_bullet_projection_extension_matches_one_full_trajectory(self):
        bullets = (
            Bullet(20.0, 30.0, 1.0, -0.5, 2.0, 3.0, 1),
            Bullet(40.0, 50.0, -2.0, 1.0, 2.0, 2.0, 3),
            Bullet(
                80.0, 90.0, 1.0, 2.0, 2.0, 2.0, 1,
                ex_flags=0x10,
                acceleration_x=0.25,
                acceleration_y=-0.5,
                acceleration_duration=14,
            ),
            Bullet(
                120.0, 140.0, -1.0, 0.5, 3.0, 3.0, 1,
                ex_flags=0x100,
                speed=2.0,
                turn_speed=3.0,
                acceleration=0.1,
            ),
        )
        state = snapshot(*bullets)
        direct = bullet_hazards_by_frame(state, 16)
        prefix = bullet_hazards_by_frame(state, 5)
        middle = extend_bullet_hazards_by_frame(state, prefix, 12)
        extended = extend_bullet_hazards_by_frame(state, middle, 16)

        self.assertEqual(extended, direct)

    def test_reachable_bullet_sweep_keeps_contact_and_drops_separation(self):
        state = snapshot(x=192.0, y=380.0)
        horizon = 4
        margin = 0.35
        player_left = (
            max(8.0, state.x - state.normal_speed * horizon)
            - state.half_width
            - margin
        )
        touching = Bullet(
            player_left - 2.0,
            state.y,
            0.0,
            0.0,
            2.0,
            2.0,
            1,
        )
        separated = Bullet(
            player_left - 2.01,
            state.y,
            0.0,
            0.0,
            2.0,
            2.0,
            1,
        )

        self.assertTrue(_may_reach_player(
            state, touching, horizon, margin
        ))
        self.assertFalse(_may_reach_player(
            state, separated, horizon, margin
        ))

    def test_reachable_bullet_projection_extension_matches_direct(self):
        bullets = (
            Bullet(192.0, 350.0, 0.0, 2.0, 2.0, 2.0, 1),
            Bullet(20.0, 20.0, -1.0, -1.0, 2.0, 2.0, 1),
            Bullet(
                120.0,
                300.0,
                1.0,
                2.0,
                2.0,
                2.0,
                1,
                ex_flags=0x10,
                acceleration_x=0.25,
                acceleration_y=0.5,
                acceleration_duration=14,
            ),
        )
        state = snapshot(*bullets)
        direct = reachable_hazards_by_frame(state, 16, 0.35)
        prefix = reachable_hazards_by_frame(state, 5, 0.35)
        middle = extend_reachable_hazards_by_frame(
            state, prefix, 12, 0.35
        )
        extended = extend_reachable_hazards_by_frame(
            state, middle, 16, 0.35
        )

        self.assertEqual(
            NativeSafetyKernel._reachable_aabb_frames(
                state, extended, 0, 0.35
            ),
            NativeSafetyKernel._reachable_aabb_frames(
                state, direct, 0, 0.35
            ),
        )

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
        expected = certify_actions(
            state,
            horizon=4,
            actions=CONTROL_ACTIONS,
        )
        decision = Solver().decide(state)
        self.assertNotIn(up_left, {item.action for item in expected})
        self.assertEqual(
            {item.action for item in decision.safe_actions},
            {item.action for item in expected},
        )

    def test_shorter_delivery_set_cannot_replace_hard_authority(self):
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
        fixed = certify_actions(
            state,
            HARD_SAFETY_HORIZON,
            actions=CONTROL_ACTIONS,
        )
        same_frame = certify_actions(
            state,
            HARD_SAFETY_HORIZON,
            DELIVERY_DELAYS[:-1],
            actions=CONTROL_ACTIONS,
        )
        decision = Solver().decide(state)

        self.assertFalse(fixed)
        self.assertTrue(same_frame)
        self.assertEqual(decision.reason, "hard-safe-set-empty")
        self.assertIsNone(decision.action)
        self.assertFalse(decision.safe_actions)
        self.assertEqual(decision.repairable_count, len(same_frame))

    def test_input_lease_can_only_hold_a_hard_safe_action(self):
        right = ACTION_BY_VECTOR[(1, 0)]
        open_decision = Solver().decide(snapshot(), required_action=right)
        self.assertEqual(open_decision.action, right)

        blocked = snapshot(Bullet(196.0, 380.0, 0.0, 0.0, 2.0, 2.0, 1))
        blocked_decision = Solver().decide(blocked, required_action=right)
        self.assertIsNone(blocked_decision.action)
        self.assertEqual(blocked_decision.reason, "input-lease-unsafe")
        # A lease proof certifies only the command already in flight.  It no
        # longer computes unrelated focused alternatives for a retired
        # universal planner.
        self.assertFalse(blocked_decision.safe_actions)

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

    def test_ecl_graph_is_compiled_once_per_stage_cache(self):
        sentinel = EclInstruction(
            0x1010, -1, 0, 12, 0xFF, bytes(12).hex()
        )
        start = EclInstruction(
            0x1000, 0, 0, 16, 0xFF, (bytes(16)).hex()
        )
        instructions = {start.address: start, sentinel.address: sentinel}

        class Process:
            ecl_subroutines = ()

            def __init__(self):
                self.reads = 0
                self.ecl_program_cache = {}

            def read_ecl_instruction(self, address):
                self.reads += 1
                return instructions[address]

        process = Process()
        first = native._read_ecl_program(process, start.address)
        reads = process.reads
        second = native._read_ecl_program(process, start.address)

        self.assertIs(first, second)
        self.assertEqual(process.reads, reads)

    def test_ecl_graph_captures_spawned_enemy_subroutine(self):
        start = EclInstruction(
            0x1000,
            0,
            95,
            36,
            0xFF,
            (
                bytes(12)
                + struct.pack("<ifffhhi", 0, 10.0, 20.0, 0.0, 1, 0, 0)
            ).hex(),
        )
        fallthrough = EclInstruction(
            0x1024, -1, 0, 12, 0xFF, bytes(12).hex()
        )
        child = EclInstruction(
            0x2000, -1, 0, 12, 0xFF, bytes(12).hex()
        )
        instructions = {
            item.address: item for item in (start, fallthrough, child)
        }
        process = type("Process", (), {
            "ecl_subroutines": (child.address,),
            "read_ecl_instruction": lambda _self, address: instructions[address],
        })()

        program = native._read_ecl_program(process, start.address)

        self.assertEqual(
            {item.address for item in program},
            {start.address, fallthrough.address, child.address},
        )

    def test_live_interrupt_table_seeds_past_registered_subroutine(self):
        current = EclInstruction(
            0x1000, -1, -1, 12, 0xFF, bytes(12).hex()
        )
        interrupt = EclInstruction(
            0x2000, -1, -1, 12, 0xFF, bytes(12).hex()
        )
        instructions = {
            current.address: current,
            interrupt.address: interrupt,
        }
        process = type("Process", (), {
            "ecl_subroutines": (0x3000, interrupt.address),
            "read_ecl_instruction": lambda _self, address: instructions[address],
        })()

        program = native._with_installed_interrupt_programs(
            process,
            (current,),
            (1, -1, 1),
        )

        self.assertEqual(
            [instruction.address for instruction in program],
            [current.address, interrupt.address],
        )

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
        kernel = NativeSafetyKernel()
        actual = kernel.replanning_scores(
            state,
            candidates,
            split=4,
            horizon=8,
            collision_margin=0.35,
        )

        self.assertEqual(actual, expected)
        self.assertEqual(
            kernel.replanning_scores_budgeted(
                state,
                candidates,
                split=4,
                horizon=8,
                collision_margin=0.35,
                budget_ms=1000.0,
            ),
            expected,
        )
        self.assertEqual(
            kernel.replanning_scores_progressive_budgeted(
                state,
                candidates,
                split=4,
                horizon=8,
                collision_margin=0.35,
                budget_ms=1000.0,
            ),
            (expected, any(score > 0 for score in expected.values())),
        )
        self.assertEqual(
            kernel.replanning_viability_budgeted(
                state,
                candidates,
                split=4,
                horizon=8,
                collision_margin=0.35,
                budget_ms=1000.0,
            ),
            {
                action: int(score > 0)
                for action, score in expected.items()
            },
        )
        self.assertIsNone(
            kernel.replanning_scores_budgeted(
                state,
                candidates,
                split=4,
                horizon=8,
                collision_margin=0.35,
                budget_ms=0.000001,
            )
        )

    def test_progressive_replanning_does_not_fragment_residual_budget(self):
        action = CONTROL_ACTIONS[0]
        candidates = (SafeAction(action, 1.0, 192.0, 380.0),)

        class BudgetProbeKernel(NativeSafetyKernel):
            def __init__(self):
                self.budgeted_replanning_viability_function = object()
                self.budgeted_replanning_function = object()
                self.robustness_budget_ms = None

            def _prepare_fail_closed(self, *_args, **_kwargs):
                return (), (), (), ()

            def _replanning_prepared_budgeted(
                self,
                function,
                _snapshot,
                _candidates,
                _split,
                _horizon,
                _collision_margin,
                budget_ms,
                _prepared,
            ):
                if function is self.budgeted_replanning_viability_function:
                    return {action: 1}
                self.robustness_budget_ms = budget_ms
                return {action: 3} if budget_ms >= 6.0 else None

        kernel = BudgetProbeKernel()
        with mock.patch(
            "th06.kernels.safety.time.perf_counter",
            side_effect=(0.0, 0.0, 0.002),
        ):
            result = kernel.replanning_scores_progressive_budgeted(
                snapshot(),
                candidates,
                split=4,
                horizon=8,
                collision_margin=0.35,
                budget_ms=10.0,
            )

        self.assertEqual(result, ({action: 3}, True))
        self.assertAlmostEqual(kernel.robustness_budget_ms, 8.0)

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















    def test_native_hard_reuses_complete_selected_prefix(self):
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
        kernel._prepare_window = mock.Mock(return_value=prepared)
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
        kernel._prepare_window.assert_called_once_with(
            state,
            0,
            6,
            fail_closed_horizon=6,
            collision_margin=0.35,
        )

    def test_native_hard_reserve_reuses_exact_fail_closed_window(self):
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
        kernel._prepared_collision_margin = -float("inf")
        kernel._prepared_fail_closed_horizon = 0
        kernel._prepared_hazards = None
        kernel._prepare_window = mock.Mock(return_value=prepared)
        kernel._certify_prepared = mock.Mock(side_effect=(
            (hard, hard, ()),
            (held_effort, (), ()),
        ))

        combined = kernel.certify_delivery_sets_with_selected_reserved(
            state,
            HARD_SAFETY_HORIZON,
            HARD_SAFETY_HORIZON + 1,
            8,
            (held,),
            collision_margin=0.35,
        )
        reused = kernel._prepare_fail_closed(state, 8, 0.35)

        self.assertEqual(combined, (hard, hard, held_effort))
        self.assertIs(reused, prepared)
        kernel._prepare_window.assert_called_once_with(
            state,
            0,
            8,
            fail_closed_horizon=8,
            collision_margin=0.35,
        )

    @unittest.skipUnless(os.name == "nt", "native kernel needs Windows")
    def test_native_reserved_window_preserves_hard_and_held_results(self):
        state = snapshot(
            Bullet(192.0, 360.0, 0.25, 1.0, 3.0, 3.0, 1),
            Bullet(170.0, 378.0, 0.8, 0.0, 2.0, 2.0, 1),
            input_mask=BUTTON_FOCUS | BUTTON_LEFT,
        )
        held = action_from_input(state.input_mask)
        ordinary = NativeSafetyKernel().certify_delivery_sets_with_selected(
            state,
            HARD_SAFETY_HORIZON,
            HARD_SAFETY_HORIZON + 1,
            (held,),
            collision_margin=0.35,
        )
        reserved = (
            NativeSafetyKernel()
            .certify_delivery_sets_with_selected_reserved(
                state,
                HARD_SAFETY_HORIZON,
                HARD_SAFETY_HORIZON + 1,
                8,
                (held,),
                collision_margin=0.35,
            )
        )

        self.assertEqual(reserved, ordinary)

    def test_native_empty_selected_prefix_rechecks_exact_hard_window(self):
        state = snapshot()
        hard = certify_actions(state, HARD_SAFETY_HORIZON)
        held = action_from_input(state.input_mask)
        long_prepared = object()
        hard_prepared = object()
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepared_snapshot = None
        kernel._prepared_horizon = 0
        kernel._prepared_hazards = None
        kernel._prepare_window = mock.Mock(side_effect=(
            long_prepared,
            hard_prepared,
        ))
        kernel._certify_prepared = mock.Mock(side_effect=(
            ((), (), ()),
            (hard, hard, ()),
            ((), (), ()),
        ))

        combined = kernel.certify_delivery_sets_with_selected(
            state,
            HARD_SAFETY_HORIZON,
            HARD_SAFETY_HORIZON + 1,
            (held,),
            collision_margin=0.35,
        )

        self.assertEqual(combined, (hard, hard, ()))
        self.assertEqual(
            kernel._prepare_window.call_args_list,
            [
                mock.call(
                    state,
                    0,
                    HARD_SAFETY_HORIZON + 1,
                    fail_closed_horizon=HARD_SAFETY_HORIZON + 1,
                    collision_margin=0.35,
                ),
                mock.call(
                    state,
                    0,
                    HARD_SAFETY_HORIZON,
                    fail_closed_horizon=HARD_SAFETY_HORIZON,
                    collision_margin=0.35,
                ),
            ],
        )

    def test_native_window_prunes_only_unreachable_aabbs(self):
        state = snapshot(x=192.0, y=380.0)
        frames = (
            (
                (197.6, 380.0, 197.6, 380.0),
                (197.61, 380.0, 197.61, 380.0),
                (192.0, 374.4, 192.0, 374.4),
                (192.0, 374.39, 192.0, 374.39),
            ),
            (
                (201.6, 380.0, 201.6, 380.0),
                (201.61, 380.0, 201.61, 380.0),
            ),
        )

        filtered = NativeSafetyKernel._reachable_aabb_frames(
            state,
            frames,
            start_frame=0,
            collision_margin=0.35,
        )

        self.assertEqual(
            filtered,
            (
                (frames[0][0], frames[0][2]),
                (frames[1][0],),
            ),
        )

    def test_fully_fail_closed_native_window_skips_unused_nominal_ecl(self):
        state = snapshot()
        horizon = 5
        empty_frames = ((),) * horizon
        forecast = WorldBirthForecast(
            births=empty_frames,
            hazards=empty_frames,
            covered_frames=horizon,
            body_hazards=empty_frames,
        )
        kernel = object.__new__(NativeSafetyKernel)
        kernel._hard_birth_snapshot = None
        kernel._hard_birth_horizon = 0
        kernel._hard_birth_forecast = None

        with (
            mock.patch(
                "th06.kernels.safety.bullet_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.enemy_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.laser_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.forecast_world_births",
                return_value=forecast,
            ) as births,
        ):
            kernel._prepare_window(
                state,
                0,
                horizon,
                fail_closed_horizon=horizon,
            )

        births.assert_called_once_with(
            state,
            ((state.x, state.y),) * horizon,
        )

    def test_future_oriented_laser_reaches_python_and_native_safety(self):
        state = snapshot()
        empty_frames = ((),)
        laser = LaserHazard(
            state.x - 10.0,
            state.y,
            0.0,
            10.0,
            20.0,
            5.0,
        )
        forecast = WorldBirthForecast(
            births=empty_frames,
            hazards=empty_frames,
            covered_frames=1,
            body_hazards=empty_frames,
            laser_hazards=((laser,),),
        )
        with (
            mock.patch(
                "th06.safety.bullet_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.safety.enemy_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.safety.laser_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.safety.forecast_world_births",
                return_value=forecast,
            ),
        ):
            self.assertFalse(certify_actions(
                state,
                1,
                delivery_delays=(0,),
                actions=(CONTROL_ACTIONS[0],),
            ))

        kernel = object.__new__(NativeSafetyKernel)
        kernel._hard_birth_snapshot = None
        kernel._hard_birth_horizon = 0
        kernel._hard_birth_forecast = None
        with (
            mock.patch(
                "th06.kernels.safety.bullet_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.enemy_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.laser_hazards_by_frame",
                return_value=empty_frames,
            ),
            mock.patch(
                "th06.kernels.safety.forecast_world_births",
                return_value=forecast,
            ),
        ):
            _, _, laser_offsets, lasers = kernel._prepare_window(
                state,
                0,
                1,
                fail_closed_horizon=1,
            )

        self.assertEqual(tuple(laser_offsets), (0, 1))
        self.assertEqual(len(lasers), 1)

    def test_soft_native_window_reuses_fresh_hard_ecl_prefix(self):
        state = snapshot()
        hard_horizon = 5
        soft_horizon = 16
        hard_frames = ((),) * hard_horizon
        soft_frames = ((),) * soft_horizon
        hard_forecast = WorldBirthForecast(
            births=hard_frames,
            hazards=hard_frames,
            covered_frames=hard_horizon,
            body_hazards=hard_frames,
        )
        nominal_forecast = WorldBirthForecast(
            births=soft_frames,
            hazards=soft_frames,
            covered_frames=soft_horizon,
            body_hazards=soft_frames,
        )
        kernel = object.__new__(NativeSafetyKernel)
        kernel._hard_birth_snapshot = None
        kernel._hard_birth_horizon = 0
        kernel._hard_birth_forecast = None

        with (
            mock.patch(
                "th06.kernels.safety.bullet_hazards_by_frame",
                return_value=soft_frames,
            ),
            mock.patch(
                "th06.kernels.safety.enemy_hazards_by_frame",
                return_value=soft_frames,
            ),
            mock.patch(
                "th06.kernels.safety.laser_hazards_by_frame",
                return_value=soft_frames,
            ),
            mock.patch(
                "th06.kernels.safety.forecast_world_births",
                side_effect=(hard_forecast, nominal_forecast),
            ) as births,
        ):
            kernel._prepare_window(
                state,
                0,
                hard_horizon,
                fail_closed_horizon=hard_horizon,
            )
            kernel._prepare_window(state, 0, soft_horizon)

        self.assertEqual(
            births.call_args_list,
            [
                mock.call(
                    state,
                    ((state.x, state.y),) * hard_horizon,
                ),
                mock.call(
                    state,
                    ((state.x, state.y),) * soft_horizon,
                    rng_mode="nominal",
                ),
            ],
        )

    def test_soft_native_window_extends_exact_nominal_ecl_prefix(self):
        state = snapshot()
        hard_horizon = 4
        first_horizon = 8
        second_horizon = 12
        all_frames = ((),) * second_horizon
        hard_forecast = WorldBirthForecast(
            births=all_frames[:hard_horizon],
            hazards=all_frames[:hard_horizon],
            covered_frames=hard_horizon,
            body_hazards=all_frames[:hard_horizon],
        )
        continuation = WorldForecastContinuation((), 0x1234, 9, False)
        first_nominal = WorldBirthForecast(
            births=all_frames[:first_horizon],
            hazards=all_frames[:first_horizon],
            covered_frames=first_horizon,
            body_hazards=all_frames[:first_horizon],
            continuation=continuation,
        )
        second_nominal = WorldBirthForecast(
            births=all_frames,
            hazards=all_frames,
            covered_frames=second_horizon,
            body_hazards=all_frames,
            continuation=continuation,
        )
        kernel = object.__new__(NativeSafetyKernel)
        kernel._hard_birth_snapshot = None
        kernel._hard_birth_horizon = 0
        kernel._hard_birth_forecast = None
        kernel._nominal_birth_snapshot = None
        kernel._nominal_birth_horizon = 0
        kernel._nominal_birth_forecast = None

        with (
            mock.patch(
                "th06.kernels.safety.bullet_hazards_by_frame",
                return_value=all_frames,
            ),
            mock.patch(
                "th06.kernels.safety.enemy_hazards_by_frame",
                return_value=all_frames,
            ),
            mock.patch(
                "th06.kernels.safety.laser_hazards_by_frame",
                return_value=all_frames,
            ),
            mock.patch(
                "th06.kernels.safety.forecast_world_births",
                side_effect=(hard_forecast, first_nominal),
            ) as births,
            mock.patch(
                "th06.kernels.safety.extend_nominal_world_births",
                return_value=second_nominal,
            ) as extend,
        ):
            kernel._prepare_window(
                state,
                0,
                hard_horizon,
                fail_closed_horizon=hard_horizon,
            )
            kernel._prepare_window(state, 0, first_horizon)
            kernel._prepare_window(state, 0, second_horizon)

        self.assertEqual(
            births.call_args_list,
            [
                mock.call(
                    state,
                    ((state.x, state.y),) * hard_horizon,
                ),
                mock.call(
                    state,
                    ((state.x, state.y),) * first_horizon,
                    rng_mode="nominal",
                ),
            ],
        )
        extend.assert_called_once_with(
            state,
            first_nominal,
            ((state.x, state.y),) * (
                second_horizon - first_horizon
            ),
        )

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
        kernel._prepare.assert_called_once_with(state, 40, 0.35)
        self.assertEqual(kernel._certify_prepared.call_count, 2)

    def test_native_held_frontier_reuses_the_effort_hazards(self):
        state = snapshot()
        held = action_from_input(state.input_mask)
        prepared = object()
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepared_snapshot = state
        kernel._prepared_horizon = 8
        kernel._prepared_collision_margin = 0.35
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

        self.assertTrue(decision.safe_actions)
        self.assertEqual(decision.reason, "route-unavailable")
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
