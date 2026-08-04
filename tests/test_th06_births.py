import math
import struct
import unittest
from dataclasses import replace
from unittest import mock

from th06.hazards.births import (
    UnsupportedBirthModel,
    periodic_births,
    periodic_hazards_by_frame,
    spawn_pattern,
    spawn_pattern_envelope,
)
from th06.hazards.bullets import hazard_box
from th06.hazards.ecl import forecast_ecl_births
from th06.hazards.rng import RngState
from th06.hazards.timeline import TimelineBossInterrupt
from th06.hazards.world import (
    WorldBirthForecast,
    _project_hazards,
    _timeline_interrupt_targets,
    extend_nominal_world_births,
    forecast_world_births,
)
from th06.birth_parity import compare_periodic_births
from th06.model import (
    Bullet,
    BulletPattern,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
    Snapshot,
    StageTimelineInstruction,
)
from th06.safety import certify_actions


def pattern(**changes) -> BulletPattern:
    values = dict(
        sprite=0,
        angle1=0.0,
        angle2=0.1,
        speed1=4.0,
        speed2=2.0,
        ex_floats=(0.0, 0.0, 0.0, 0.0),
        ex_ints=(0, 0, 0, 0),
        count1=5,
        count2=2,
        aim_mode=1,
        flags=0x04,
        half_width=3.0,
        half_height=3.0,
    )
    values.update(changes)
    return BulletPattern(**values)


def spawner(pattern_value: BulletPattern, **changes) -> EnemySpawner:
    values = dict(
        slot=7,
        x=32.0,
        y=60.0,
        velocity_x=1.0,
        velocity_y=0.0,
        angle=0.0,
        angular_velocity=0.0,
        speed=1.0,
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
        shoot_offset_x=2.0,
        shoot_offset_y=3.0,
        bullet_rank_speed_low=-0.5,
        bullet_rank_speed_high=0.5,
        bullet_rank_amount1_low=0,
        bullet_rank_amount1_high=0,
        bullet_rank_amount2_low=0,
        bullet_rank_amount2_high=0,
        life=10,
        shooting_disabled=False,
        interval=3,
        timer=1,
        timer_float=1.0,
        pattern=pattern_value,
        ecl_time=0,
        ecl_time_float=0.0,
        ecl_ints=(0, 0, 0, 0, 0, 0, 0, 0),
        ecl_floats=(0.0, 0.0, 0.0, 0.0),
        ecl_compare=0,
        repeat_ex_index=None,
        next_instruction=None,
        ecl_program=(),
    )
    values.update(changes)
    return EnemySpawner(**values)


def snapshot(frame: int, **changes) -> Snapshot:
    values = dict(
        frame=frame,
        stage=5,
        player_state=0,
        x=100.0,
        y=0.0,
        half_width=1.0,
        half_height=1.0,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=3.0,
        focus_diagonal_speed=1.5,
        frame_multiplier=1.0,
        input_mask=0,
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
    )
    values.update(changes)
    return Snapshot(**values)


class PeriodicBirthTests(unittest.TestCase):
    def test_timeline_interrupt_uses_captured_raw_boss_pointer(self):
        state = snapshot(
            100,
            timeline_boss_slots=(7, -1, -1, -1, -1, -1, -1, -1),
        )
        ordinary = spawner(pattern(), slot=7, is_boss=False, boss_id=-1)
        other = replace(ordinary, slot=8)
        event = TimelineBossInterrupt(0x3010, 0, 3)

        self.assertTrue(_timeline_interrupt_targets(state, ordinary, event))
        self.assertFalse(_timeline_interrupt_targets(state, other, event))

    def test_world_stops_before_uninserted_timeline_enemy(self):
        transition = StageTimelineInstruction(
            0x3000,
            102,
            7,
            0,
            8,
            struct.pack("<hhhh", 102, 7, 0, 8).hex(),
        )
        state = snapshot(
            100,
            timeline_time=100,
            timeline_instructions=(transition,),
        )

        for mode in ("fail-closed", "nominal"):
            forecast = forecast_world_births(
                state,
                ((100.0, 400.0),) * 4,
                rng_mode=mode,
            )
            self.assertEqual(forecast.covered_frames, 2)
            self.assertIn("stage timeline", forecast.reason)
            self.assertIsNone(forecast.continuation)

    def test_timeline_transition_beyond_window_preserves_coverage(self):
        transition = StageTimelineInstruction(
            0x3000,
            104,
            7,
            0,
            8,
            struct.pack("<hhhh", 104, 7, 0, 8).hex(),
        )
        forecast = forecast_world_births(
            snapshot(
                100,
                timeline_time=100,
                timeline_instructions=(transition,),
            ),
            ((100.0, 400.0),) * 4,
        )

        self.assertEqual(forecast.covered_frames, 4)

    def test_hard_world_inserts_deterministic_timeline_enemy(self):
        bullet_args = struct.pack(
            "<hhii ffff I",
            0,
            0,
            1,
            1,
            4.0,
            4.0,
            0.0,
            0.0,
            4,
        )
        bullet_raw = (
            struct.pack("<ihhBBBB", 0, 68, 0x30, 0, 4, 0, 0)
            + bullet_args
        )
        bullet = EclInstruction(0x1000, 0, 68, 0x30, 4, bullet_raw.hex())
        sentinel = EclInstruction(
            0x1030,
            -1,
            -1,
            12,
            0xFF,
            struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0).hex(),
        )
        timeline_raw = struct.pack(
            "<hhhhfffhhI",
            100,
            0,
            0,
            28,
            32.0,
            60.0,
            0.0,
            10,
            -1,
            100,
        )
        transition = StageTimelineInstruction(
            0x3000,
            100,
            0,
            0,
            28,
            timeline_raw.hex(),
        )
        forecast = forecast_world_births(
            snapshot(
                100,
                bullet_sizes=((3.0, 3.0),),
                timeline_time=100,
                timeline_instructions=(transition,),
                ecl_subroutines=(0x1000,),
                timeline_ecl_program=(bullet, sentinel),
            ),
            ((100.0, 400.0),) * 4,
        )

        self.assertEqual(forecast.covered_frames, 4, forecast.reason)
        self.assertEqual([len(frame) for frame in forecast.births], [1, 0, 0, 0])
        self.assertTrue(forecast.body_hazards[0])

        nominal = forecast_world_births(
            snapshot(
                100,
                bullet_sizes=((3.0, 3.0),),
                timeline_time=100,
                timeline_instructions=(transition,),
                ecl_subroutines=(0x1000,),
                timeline_ecl_program=(bullet, sentinel),
            ),
            ((100.0, 400.0),) * 4,
            rng_mode="nominal",
        )
        self.assertEqual(nominal.covered_frames, 4, nominal.reason)
        self.assertEqual(
            [len(frame) for frame in nominal.births], [1, 0, 0, 0]
        )
        self.assertIsNotNone(nominal.continuation)
        self.assertEqual(nominal.continuation.elapsed_frames, 4)

    def test_hard_world_encloses_random_timeline_enemy_position(self):
        waiting = EclInstruction(
            0x1000,
            10000,
            1,
            16,
            0xFF,
            struct.pack(
                "<ihhBBBBI", 10000, 1, 16, 0, 0xFF, 0, 0, 0
            ).hex(),
        )
        transition = StageTimelineInstruction(
            0x3000,
            100,
            0,
            4,
            28,
            struct.pack(
                "<hhhhfffhhI",
                100,
                0,
                4,
                28,
                -999.0,
                60.0,
                0.0,
                10,
                -1,
                100,
            ).hex(),
        )
        positions = ((100.0, 400.0),) * 4
        values = dict(
            timeline_time=100,
            timeline_instructions=(transition,),
            ecl_subroutines=(0x1000,),
            timeline_ecl_program=(waiting,),
        )

        hard = forecast_world_births(snapshot(100, **values), positions)

        self.assertEqual(hard.covered_frames, 4, hard.reason)
        self.assertEqual(len(hard.body_hazards[0]), 1)
        self.assertEqual(hard.body_hazards[0][0], (-4.0, 56.0, 372.0, 64.0))
        for seed in range(32):
            nominal = forecast_world_births(
                snapshot(100, rng_seed=seed, **values),
                positions,
                rng_mode="nominal",
            )
            self.assertEqual(nominal.covered_frames, 4, nominal.reason)
            self.assertIsNotNone(nominal.continuation)
            child = nominal.continuation.emitters[0]
            self.assertGreaterEqual(child.x, 0.0)
            self.assertLessEqual(child.x, 368.0)
            outer = hard.body_hazards[0][0]
            inner = nominal.body_hazards[0][0]
            self.assertLessEqual(outer[0], inner[0])
            self.assertLessEqual(outer[1], inner[1])
            self.assertGreaterEqual(outer[2], inner[2])
            self.assertGreaterEqual(outer[3], inner[3])

    def test_nominal_timeline_spawn_extension_matches_direct_slot_loop(self):
        waiting = EclInstruction(
            0x1000,
            10000,
            1,
            12,
            0xFF,
            struct.pack("<ihhBBBB", 10000, 1, 12, 0, 0xFF, 0, 0).hex(),
        )
        transition = StageTimelineInstruction(
            0x3000,
            103,
            0,
            1,
            28,
            struct.pack(
                "<hhhhfffhhI",
                103,
                0,
                1,
                28,
                32.0,
                -44.0,
                0.0,
                -1,
                -1,
                0,
            ).hex(),
        )
        state = snapshot(
            100,
            timeline_time=100,
            timeline_instructions=(transition,),
            ecl_subroutines=(0x1000,),
            timeline_ecl_program=(waiting,),
            rng_seed=0x1234,
            rng_generation=9,
        )
        positions = ((100.0, 400.0),) * 7
        direct = forecast_world_births(
            state, positions, rng_mode="nominal"
        )
        prefix = forecast_world_births(
            state, positions[:2], rng_mode="nominal"
        )
        extended = extend_nominal_world_births(
            state, prefix, positions[2:]
        )

        self.assertEqual(extended, direct)
        self.assertEqual(direct.covered_frames, 7, direct.reason)
        self.assertEqual(len(direct.continuation.emitters), 1)
        child = direct.continuation.emitters[0]
        self.assertEqual((child.slot, child.ecl_time), (0, 5))
        self.assertEqual(direct.continuation.elapsed_frames, 7)

    def test_nominal_extension_aligns_empty_partial_tail_body_frames(self):
        state = snapshot(100)
        prefix = forecast_world_births(
            state,
            ((100.0, 400.0),) * 2,
            rng_mode="nominal",
        )
        partial_tail = WorldBirthForecast(
            ((), (), ()),
            ((), (), ()),
            2,
            "unsupported future instruction",
        )

        with mock.patch(
            "th06.hazards.world._forecast_nominal_from_state",
            return_value=partial_tail,
        ):
            extended = extend_nominal_world_births(
                state, prefix, ((100.0, 400.0),) * 3
            )

        self.assertEqual(extended.covered_frames, 4)
        self.assertEqual(extended.body_hazards, ((),) * 5)

    def test_world_stops_before_timeline_boss_interrupt(self):
        transition = StageTimelineInstruction(
            0x3010,
            100,
            0,
            10,
            16,
            struct.pack("<hhhhII", 100, 0, 10, 16, 0, 3).hex(),
        )
        forecast = forecast_world_births(
            snapshot(
                100,
                timeline_time=100,
                timeline_instructions=(transition,),
            ),
            ((100.0, 400.0),) * 4,
        )

        self.assertEqual(forecast.covered_frames, 0)
        self.assertIn("opcode 10", forecast.reason)

    def test_proved_message_wait_moves_interrupt_beyond_hard_four(self):
        instructions = (
            StageTimelineInstruction(
                0x3000,
                100,
                2,
                8,
                8,
                struct.pack("<hhhh", 100, 2, 8, 8).hex(),
            ),
            StageTimelineInstruction(
                0x3008,
                101,
                0,
                9,
                8,
                struct.pack("<hhhh", 101, 0, 9, 8).hex(),
            ),
            StageTimelineInstruction(
                0x3010,
                102,
                0,
                10,
                16,
                struct.pack("<hhhhII", 102, 0, 10, 16, 0, 3).hex(),
            ),
        )
        positions = ((100.0, 400.0),) * 4
        unproved = forecast_world_births(
            snapshot(
                99,
                stage=4,
                difficulty=2,
                character=0,
                timeline_time=99,
                timeline_instructions=instructions,
            ),
            positions,
        )
        proved = forecast_world_births(
            snapshot(
                99,
                stage=4,
                difficulty=2,
                character=0,
                timeline_time=99,
                timeline_instructions=instructions,
                timeline_message_delays=((2, 1),),
            ),
            positions,
        )

        self.assertEqual(unproved.covered_frames, 3)
        self.assertEqual(proved.covered_frames, 4, proved.reason)

    def test_timeline_interrupt_enters_captured_boss_subroutine(self):
        boss_set = EclInstruction(
            0x1000,
            0,
            101,
            16,
            0xFF,
            (struct.pack("<ihhBBBB", 0, 101, 16, 0, 0xFF, 0, 0)
             + struct.pack("<i", 0)).hex(),
        )
        interrupt_set = EclInstruction(
            0x1010,
            0,
            109,
            20,
            0xFF,
            (struct.pack("<ihhBBBB", 0, 109, 20, 0, 0xFF, 0, 0)
             + struct.pack("<ii", 1, 0)).hex(),
        )
        waiting = EclInstruction(
            0x1024,
            60,
            0,
            12,
            0xFF,
            struct.pack("<ihhBBBB", 60, 0, 12, 0, 0xFF, 0, 0).hex(),
        )
        main_end = EclInstruction(
            0x1030,
            -1,
            -1,
            12,
            0xFF,
            struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0).hex(),
        )
        bullet_args = struct.pack(
            "<hhii ffff I",
            0,
            0,
            1,
            1,
            4.0,
            4.0,
            0.0,
            0.0,
            4,
        )
        interrupt_shot = EclInstruction(
            0x2000,
            0,
            68,
            0x30,
            0xFF,
            (struct.pack("<ihhBBBB", 0, 68, 0x30, 0, 0xFF, 0, 0)
             + bullet_args).hex(),
        )
        interrupt_end = EclInstruction(
            0x2030,
            -1,
            -1,
            12,
            0xFF,
            struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0).hex(),
        )
        spawn_raw = struct.pack(
            "<hhhhfffhhI",
            100,
            0,
            0,
            28,
            192.0,
            80.0,
            0.0,
            100,
            -1,
            0,
        )
        timeline = (
            StageTimelineInstruction(
                0x3000, 100, 0, 0, 28, spawn_raw.hex()
            ),
            StageTimelineInstruction(
                0x301C,
                101,
                0,
                10,
                16,
                struct.pack("<hhhhII", 101, 0, 10, 16, 0, 0).hex(),
            ),
        )

        forecast = forecast_world_births(
            snapshot(
                100,
                timeline_time=100,
                timeline_instructions=timeline,
                ecl_subroutines=(0x1000, 0x2000),
                timeline_ecl_program=(
                    boss_set,
                    interrupt_set,
                    waiting,
                    main_end,
                    interrupt_shot,
                    interrupt_end,
                ),
                timeline_boss_slots=(-1,) * 8,
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),) * 3,
        )

        self.assertEqual(forecast.covered_frames, 3, forecast.reason)
        self.assertEqual([len(frame) for frame in forecast.births], [0, 1, 0])

    def test_world_birth_projection_matches_scalar_source_motion(self):
        turning = Bullet(
            10.0,
            20.0,
            2.0,
            0.0,
            2.0,
            3.0,
            1,
            ex_flags=0x40,
            speed=2.0,
            turn_speed=1.5,
            angle=0.0,
            direction_rotation=math.pi / 4.0,
            direction_interval=2,
            direction_max_times=3,
        )
        linear = Bullet(30.0, 40.0, -1.0, 2.0, 2.0, 3.0, 1)

        actual = _project_hazards(
            [[turning], [linear], []],
            radial=False,
        )

        self.assertEqual(actual, (
            (hazard_box(turning, 1),),
            (hazard_box(turning, 2), hazard_box(linear, 1)),
            (hazard_box(turning, 3), hazard_box(linear, 2)),
        ))

    def test_enemy_kill_all_is_neutral_only_without_callback_targets(self):
        kill_all = EclInstruction(
            0x1000,
            0,
            96,
            12,
            0xFF,
            struct.pack("<ihhBBBB", 0, 96, 12, 0, 0xFF, 0, 0).hex(),
        )
        sentinel = EclInstruction(
            0x100C, -1, 0, 12, 0xFF, (b"\xff" * 12).hex()
        )
        boss = spawner(
            pattern(),
            is_boss=True,
            shooting_disabled=True,
            next_instruction=kill_all,
            ecl_program=(kill_all, sentinel),
        )
        state = snapshot(10, spawners=(boss,))

        safe_noop = forecast_world_births(state, ((100.0, 400.0),))

        self.assertEqual(safe_noop.covered_frames, 1, safe_noop.reason)

        callback_target = replace(
            boss,
            slot=boss.slot + 1,
            is_boss=False,
            death_callback_sub=0,
            next_instruction=sentinel,
            ecl_program=(sentinel,),
        )
        unsafe_world = forecast_world_births(
            replace(state, spawners=(boss, callback_target)),
            ((100.0, 400.0),),
        )

        self.assertEqual(unsafe_world.covered_frames, 0)
        self.assertIn("ENEMYKILLALL", unsafe_world.reason)

    def test_fan_and_speed_layers_match_shipped_integer_order(self):
        bullets = spawn_pattern(pattern(), (0.0, 0.0), (100.0, 0.0))
        self.assertEqual(len(bullets), 10)
        self.assertEqual(
            [round(bullet.angle, 6) for bullet in bullets[:5]],
            [0.0, -0.1, 0.1, -0.2, 0.2],
        )
        self.assertEqual([bullet.speed for bullet in bullets[:5]], [4.0] * 5)
        # SpawnSingleBullet divides by count2, so the second of two layers is
        # the midpoint rather than speed2.
        self.assertEqual([bullet.speed for bullet in bullets[5:]], [3.0] * 5)
        self.assertTrue(all(bullet.state == 3 for bullet in bullets))

    def test_aimed_fan_uses_player_position_at_the_birth_frame(self):
        aimed = pattern(aim_mode=0, count1=1, count2=1)
        bullet = spawn_pattern(aimed, (10.0, 20.0), (10.0, 40.0))[0]
        self.assertAlmostEqual(bullet.angle, math.pi / 2.0)
        self.assertAlmostEqual(bullet.vx, 0.0, places=6)
        self.assertAlmostEqual(bullet.vy, 4.0)

    def test_periodic_timer_ticks_and_enemy_moves_before_birth(self):
        shooter = spawner(pattern(count1=1, count2=1))
        births = periodic_births(
            shooter,
            ((192.0, 400.0),) * 6,
        )
        self.assertEqual([len(items) for items in births], [0, 1, 0, 0, 1, 0])
        self.assertEqual(births[1][0].x, 36.0)
        self.assertEqual(births[1][0].y, 63.0)
        self.assertEqual(births[4][0].x, 39.0)

    def test_birth_hazard_includes_same_tick_spawn_motion(self):
        straight = pattern(
            count1=1,
            count2=1,
            angle2=0.0,
            speed1=5.0,
            speed2=5.0,
        )
        shooter = spawner(
            straight,
            x=0.0,
            y=0.0,
            velocity_x=0.0,
            shoot_offset_x=0.0,
            shoot_offset_y=0.0,
            interval=1,
            timer=0,
            timer_float=0.0,
        )
        hazards = periodic_hazards_by_frame(
            (shooter,),
            ((100.0, 0.0),),
        )
        # Normal spawn state moves by speed/2.5. The existing conservative
        # source model encloses that point through full-speed movement.
        self.assertEqual(hazards[0], ((-1.0, -3.0, 8.0, 3.0),))

    def test_random_modes_fail_closed_instead_of_sampling(self):
        random_pattern = replace(pattern(), aim_mode=6)
        with self.assertRaises(UnsupportedBirthModel):
            spawn_pattern(random_pattern, (0.0, 0.0), (10.0, 10.0))

    def test_random_pattern_consumes_explicit_source_rng(self):
        rng = RngState(0, 0)
        bullets = spawn_pattern(
            pattern(aim_mode=6, count1=1, count2=1),
            (0.0, 0.0),
            (10.0, 10.0),
            rng,
        )
        self.assertEqual(len(bullets), 1)
        self.assertEqual(rng.generation_count, 2)
        self.assertEqual(rng.seed, 0xBFC7)

        envelope = spawn_pattern_envelope(
            pattern(aim_mode=8, count1=4, count2=2),
            (0.0, 0.0),
        )
        self.assertEqual(len(envelope), 1)
        self.assertEqual(envelope[0].speed, 4.0)

    def test_adjacent_snapshot_parity_uses_native_slots(self):
        sentinel = EclInstruction(0x2000, -1, 0, 0, 0, (b"\xff" * 12).hex())
        shooter = spawner(
            pattern(count1=1, count2=1),
            velocity_x=0.0,
            shoot_offset_x=0.0,
            shoot_offset_y=0.0,
            interval=1,
            timer=0,
            timer_float=0.0,
            next_instruction=sentinel,
            ecl_program=(sentinel,),
        )
        expected = periodic_births(shooter, ((100.0, 0.0),))[0][0]
        actual = replace(
            expected,
            x=expected.x + expected.vx * 0.4,
            y=expected.y + expected.vy * 0.4,
            timer=1,
            timer_float=1.0,
            slot=42,
        )
        report = compare_periodic_births(
            snapshot(
                10,
                spawners=(shooter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            snapshot(11, bullets=(actual,)),
        )
        self.assertTrue(report.supported)
        self.assertEqual((report.predicted, report.observed), (1, 1))
        self.assertAlmostEqual(report.max_position_error, 0.0)
        self.assertAlmostEqual(report.max_angle_error, 0.0)
        self.assertAlmostEqual(report.max_speed_error, 0.0)


class EclBirthTests(unittest.TestCase):
    @staticmethod
    def instruction(
        address: int,
        time: int,
        opcode: int,
        args: bytes,
        next_size: int,
    ) -> EclInstruction:
        raw = struct.pack("<ihhBBBB", time, opcode, next_size, 0, 4, 0, 0) + args
        return EclInstruction(address, time, opcode, next_size, 4, raw.hex())

    def test_jumpdec_loop_forecasts_the_next_unborn_pattern(self):
        bullet = self.instruction(
            0x1000,
            0,
            68,
            struct.pack("<hhii ffff I", 0, 0, 1, 1, 4.0, 2.0, 0.0, 0.0, 4),
            0x30,
        )
        jump = self.instruction(
            0x1030,
            3,
            3,
            struct.pack("<iii", 0, -0x30, -10001),
            0x18,
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            timer=0,
            timer_float=0.0,
            ecl_time=1,
            ecl_time_float=1.0,
            ecl_ints=(2, 0, 0, 0, 0, 0, 0, 0),
            next_instruction=jump,
            ecl_program=(bullet, jump),
        )
        forecast = forecast_ecl_births(
            emitter,
            ((100.0, 400.0),) * 3,
            difficulty=2,
            rank=0,
            bullet_sizes=((3.0, 3.0),),
        )
        self.assertEqual(forecast.covered_frames, 3)
        self.assertEqual([len(items) for items in forecast.births], [0, 0, 1])
        self.assertAlmostEqual(forecast.births[2][0].speed, 3.5)

        world = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),) * 3,
        )
        self.assertEqual(world.covered_frames, 3)
        self.assertEqual([len(items) for items in world.births], [0, 0, 1])

    def test_world_rng_is_explicit_and_emitters_run_in_slot_order(self):
        random_bullet = self.instruction(
            0x1000,
            0,
            73,
            struct.pack(
                "<hhii ffff I", 0, 0, 1, 1, 4.0, 2.0, 1.0, -1.0, 4
            ),
            0x30,
        )
        sentinel = EclInstruction(
            0x1030, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        later_slot = spawner(
            pattern(count1=1, count2=1),
            slot=9,
            x=90.0,
            interval=0,
            next_instruction=random_bullet,
            ecl_program=(random_bullet, sentinel),
        )
        earlier_slot = replace(later_slot, slot=2, x=20.0)
        state = snapshot(
            10,
            spawners=(later_slot, earlier_slot),
            bullet_sizes=((3.0, 3.0),),
        )

        hard = forecast_world_births(state, ((100.0, 400.0),))
        self.assertEqual(hard.covered_frames, 1)
        self.assertEqual([bullet.x for bullet in hard.births[0]], [23.0, 93.0])

        nominal = forecast_world_births(
            state,
            ((100.0, 400.0),),
            rng_mode="nominal",
        )
        self.assertEqual(nominal.covered_frames, 1)
        self.assertEqual([bullet.x for bullet in nominal.births[0]], [23.0, 93.0])

        rng = RngState(0, 0)
        expected_first = spawn_pattern(
            replace(pattern(count1=1, count2=1), aim_mode=6, angle1=1.0, angle2=-1.0),
            (23.0, 63.0),
            (100.0, 400.0),
            rng,
        )[0]
        expected_second = spawn_pattern(
            replace(pattern(count1=1, count2=1), aim_mode=6, angle1=1.0, angle2=-1.0),
            (93.0, 63.0),
            (100.0, 400.0),
            rng,
        )[0]
        self.assertAlmostEqual(nominal.births[0][0].angle, expected_first.angle)
        self.assertAlmostEqual(nominal.births[0][1].angle, expected_second.angle)

    def test_nominal_world_batches_only_rng_independent_emitters(self):
        waiting = self.instruction(
            0x1000, 10000, 1, bytes(4), 0x10
        )
        later = spawner(
            pattern(count1=2, count2=1, aim_mode=1),
            slot=9,
            x=90.0,
            interval=3,
            timer=1,
            timer_float=1.0,
            next_instruction=waiting,
            ecl_program=(waiting,),
        )
        earlier = replace(later, slot=2, x=20.0, timer=2, timer_float=2.0)
        positions = tuple(
            (100.0 + frame, 400.0 - frame)
            for frame in range(12)
        )
        state = snapshot(
            10,
            spawners=(later, earlier),
            rng_seed=0x1234,
            rng_generation=19,
        )

        with mock.patch(
            "th06.hazards.world.forecast_ecl_births",
            wraps=forecast_ecl_births,
        ) as forecast:
            batched = forecast_world_births(
                state, positions, rng_mode="nominal"
            )
        with mock.patch(
            "th06.hazards.world._forecast_nominal_without_shared_rng",
            return_value=None,
        ):
            framewise = forecast_world_births(
                state, positions, rng_mode="nominal"
            )

        self.assertEqual(batched, framewise)
        self.assertEqual(forecast.call_count, 2)

    def test_nominal_extension_matches_one_full_ecl_rng_forecast(self):
        waiting = self.instruction(
            0x1000, 10000, 1, bytes(4), 0x10
        )
        random_pattern = pattern(
            aim_mode=8,
            count1=2,
            count2=1,
            angle1=1.0,
            angle2=-1.0,
        )
        later = spawner(
            random_pattern,
            slot=9,
            x=90.0,
            interval=3,
            timer=1,
            timer_float=1.0,
            next_instruction=waiting,
            ecl_program=(waiting,),
        )
        earlier = replace(later, slot=2, x=20.0, timer=2, timer_float=2.0)
        positions = tuple(
            (100.0 + frame, 400.0 - frame)
            for frame in range(12)
        )
        for emitters in ((earlier,), (later, earlier)):
            with self.subTest(emitters=len(emitters)):
                state = snapshot(
                    10,
                    spawners=emitters,
                    rng_seed=0x1234,
                    rng_generation=19,
                )
                direct = forecast_world_births(
                    state,
                    positions,
                    rng_mode="nominal",
                )
                prefix = forecast_world_births(
                    state,
                    positions[:5],
                    rng_mode="nominal",
                )
                extended = extend_nominal_world_births(
                    state,
                    prefix,
                    positions[5:],
                )

                self.assertEqual(extended, direct)

    def test_nominal_batch_keeps_no_damage_callback_semantics(self):
        waiting = self.instruction(
            0x1000, 10000, 1, bytes(4), 0x10
        )
        callback_bullet = self.instruction(
            0x2000,
            0,
            67,
            struct.pack(
                "<hhIIffffI", 0, 0, 1, 1, 1.0, 0.3, 0.0, 0.0, 0
            ),
            0x2C,
        )
        sentinel = EclInstruction(
            0x202C, -1, 0, 0, 0, bytes(12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            life=10,
            interval=0,
            interactable=True,
            is_boss=True,
            life_callback_threshold=5,
            life_callback_sub=0,
            ecl_subroutines=(0x2000,),
            next_instruction=waiting,
            ecl_program=(waiting, callback_bullet, sentinel),
        )
        state = snapshot(
            10,
            spawners=(emitter,),
            bullet_sizes=((3.0, 3.0),),
        )
        positions = ((100.0, 400.0),) * 2

        hard = forecast_world_births(state, positions)
        nominal = forecast_world_births(
            state,
            positions,
            rng_mode="nominal",
        )

        self.assertEqual(hard.covered_frames, 2, hard.reason)
        self.assertEqual([len(frame) for frame in hard.births], [0, 1])
        self.assertEqual(nominal.covered_frames, 2, nominal.reason)
        self.assertEqual(nominal.births, ((), ()))
        self.assertEqual(hard.births[1][0].speed, 0.5)

    def test_hard_world_expands_a_bounded_discrete_rng_domain(self):
        random_int = self.instruction(
            0x1000,
            0,
            6,
            struct.pack("<ii", -10001, 10),
            0x14,
        )
        sentinel = EclInstruction(
            0x1014, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=random_int,
            ecl_program=(random_int, sentinel),
        )
        state = snapshot(10, spawners=(emitter,))
        hard = forecast_world_births(state, ((100.0, 400.0),))
        self.assertEqual(hard.covered_frames, 1)
        self.assertEqual(hard.reason, "")
        nominal = forecast_world_births(
            state,
            ((100.0, 400.0),),
            rng_mode="nominal",
        )
        self.assertEqual(nominal.covered_frames, 1)

    def test_hard_world_fails_closed_on_an_unbounded_integer_rng_domain(self):
        random_int = self.instruction(
            0x1000,
            0,
            6,
            struct.pack("<ii", -10001, 65),
            0x14,
        )
        sentinel = EclInstruction(
            0x1014, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=random_int,
            ecl_program=(random_int, sentinel),
        )

        hard = forecast_world_births(
            snapshot(10, spawners=(emitter,)),
            ((100.0, 400.0),),
        )

        self.assertEqual(hard.covered_frames, 0)
        self.assertIn("exceeds branch budget", hard.reason)

    def test_delayed_interval_uses_exact_rng_or_all_hard_phases(self):
        delayed = self.instruction(
            0x1000,
            0,
            77,
            struct.pack("<i", 5),
            0x10,
        )
        sentinel = EclInstruction(
            0x1010, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            timer=0,
            timer_float=0.0,
            next_instruction=delayed,
            ecl_program=(delayed, sentinel),
        )
        state = snapshot(
            10,
            spawners=(emitter,),
            bullet_sizes=((3.0, 3.0),),
            rng_seed=0,
            rng_generation=0,
        )

        hard = forecast_world_births(
            state,
            ((100.0, 400.0),) * 3,
        )
        self.assertEqual(hard.covered_frames, 3)
        self.assertEqual([len(items) for items in hard.births], [1, 1, 1])

        nominal = forecast_world_births(
            state,
            ((100.0, 400.0),) * 3,
            rng_mode="nominal",
        )
        self.assertEqual(nominal.covered_frames, 3)
        self.assertEqual([len(items) for items in nominal.births], [1, 0, 0])

    def test_source_visual_particle_opcode_is_hazard_neutral(self):
        particle = self.instruction(
            0x1000,
            0,
            118,
            struct.pack("<iii", 4, 2, 1),
            0x18,
        )
        sentinel = EclInstruction(
            0x1018, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=particle,
            ecl_program=(particle, sentinel),
        )
        forecast = forecast_world_births(
            snapshot(10, spawners=(emitter,)),
            ((100.0, 400.0),) * 4,
        )
        self.assertEqual(forecast.covered_frames, 4)
        self.assertEqual(forecast.births, ((), (), (), ()))

    def test_source_animation_opcodes_are_hazard_neutral(self):
        animation_slot = self.instruction(
            0x1000,
            0,
            99,
            struct.pack("<ii", 4, 66),
            0x14,
        )
        animation_rotation = self.instruction(
            0x1014,
            0,
            120,
            struct.pack("<i", 0),
            0x10,
        )
        animation_main = self.instruction(
            0x1024,
            0,
            97,
            struct.pack("<i", 66),
            0x10,
        )
        spell_effect = self.instruction(
            0x1034,
            0,
            102,
            struct.pack("<iffff", 9, -0.7, -0.1, -0.5, 48.0),
            0x20,
        )
        damageable_flag = self.instruction(
            0x1054,
            0,
            105,
            struct.pack("<i", 0),
            0x10,
        )
        bounds_disable = self.instruction(
            0x1064,
            0,
            66,
            b"",
            0x0C,
        )
        sentinel = EclInstruction(
            0x1070, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=animation_slot,
            ecl_program=(
                animation_slot,
                animation_rotation,
                animation_main,
                spell_effect,
                damageable_flag,
                bounds_disable,
                sentinel,
            ),
        )
        forecast = forecast_world_births(
            snapshot(10, spawners=(emitter,)),
            ((100.0, 400.0),) * 4,
        )
        self.assertEqual(forecast.covered_frames, 4)
        self.assertEqual(forecast.births, ((), (), (), ()))

    def test_return_restores_the_captured_source_context(self):
        returned_bullet = self.instruction(
            0x1000,
            5,
            68,
            struct.pack(
                "<hhii ffff I", 0, 0, 1, 1, 4.0, 2.0, 0.0, 0.0, 4
            ),
            0x30,
        )
        sentinel = EclInstruction(
            0x1030, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        return_instruction = self.instruction(0x2000, 0, 36, b"", 0x0C)
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            ecl_time=0,
            ecl_time_float=0.0,
            next_instruction=return_instruction,
            ecl_program=(return_instruction, returned_bullet, sentinel),
            ecl_stack=(EnemyEclContext(
                0x1000,
                5,
                5.0,
                (0, 0, 0, 0, 0, 0, 0, 0),
                (0.0, 0.0, 0.0, 0.0),
                0,
                None,
            ),),
        )
        forecast = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )
        self.assertEqual(forecast.covered_frames, 1)
        self.assertEqual(len(forecast.births[0]), 1)
        self.assertEqual(forecast.births[0][0].speed, 3.5)

    def test_call_at_maximum_source_depth_enters_without_pushing(self):
        call = self.instruction(
            0x1000,
            0,
            35,
            struct.pack("<iif", 0, 7, 2.5),
            0x18,
        )
        caller_sentinel = EclInstruction(
            0x1018, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        callee_bullet = self.instruction(
            0x2000,
            0,
            68,
            struct.pack(
                "<hhii ffff I", 0, 0, 1, 1, 8.0, 8.0, 0.0, 0.0, 4
            ),
            0x30,
        )
        return_instruction = self.instruction(0x2030, 0, 36, b"", 0x0C)
        resumed_bullet = self.instruction(
            0x3000,
            0,
            68,
            struct.pack(
                "<hhii ffff I", 0, 0, 1, 1, 4.0, 4.0, 0.0, 0.0, 4
            ),
            0x30,
        )
        resumed_sentinel = EclInstruction(
            0x3030, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        saved_context = EnemyEclContext(
            0x3000,
            0,
            0.0,
            (0, 0, 0, 0, 0, 0, 0, 0),
            (0.0, 0.0, 0.0, 0.0),
            0,
            None,
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=call,
            ecl_program=(
                call,
                caller_sentinel,
                callee_bullet,
                return_instruction,
                resumed_bullet,
                resumed_sentinel,
            ),
            ecl_subroutines=(0x2000,),
            ecl_stack=(saved_context,) * 7,
        )

        forecast = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )

        self.assertEqual(forecast.covered_frames, 1, forecast.reason)
        self.assertEqual(
            sorted(bullet.speed for bullet in forecast.births[0]),
            [3.75, 7.75],
        )

    def test_conditional_call_uses_the_immutable_subroutine_table(self):
        call = self.instruction(
            0x1000,
            0,
            39,
            struct.pack("<iifii", 0, 7, 2.5, -10001, 0),
            0x20,
        )
        caller_sentinel = EclInstruction(
            0x1020, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        bullet = self.instruction(
            0x2000,
            0,
            68,
            struct.pack(
                "<hhii ffff I",
                0,
                0,
                1,
                1,
                -10005.0,
                0.0,
                0.0,
                0.0,
                4,
            ),
            0x30,
        )
        return_instruction = self.instruction(0x2030, 0, 36, b"", 0x0C)
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=call,
            ecl_program=(call, caller_sentinel, bullet, return_instruction),
            ecl_subroutines=(0x2000,),
        )
        forecast = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )
        self.assertEqual(forecast.covered_frames, 1)
        self.assertEqual(len(forecast.births[0]), 1)
        self.assertEqual(forecast.births[0][0].speed, 2.0)

    def test_interactable_opcode_activates_future_enemy_body_hazard(self):
        interactable = self.instruction(
            0x1000,
            0,
            117,
            struct.pack("<i", 1),
            0x10,
        )
        sentinel = EclInstruction(
            0x1010, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            x=100.0,
            y=200.0,
            velocity_x=0.0,
            interval=0,
            next_instruction=interactable,
            ecl_program=(interactable, sentinel),
            hitbox_half_width=6.0,
            hitbox_half_height=9.0,
            interactable=False,
            collidable=True,
        )
        forecast = forecast_world_births(
            snapshot(10, spawners=(emitter,)),
            ((100.0, 400.0),),
        )
        self.assertEqual(forecast.covered_frames, 1)
        self.assertEqual(
            forecast.body_hazards,
            (((94.0, 191.0, 106.0, 209.0),),),
        )

    def test_hard_world_carries_player_angle_as_position_uncertainty(self):
        set_angle = self.instruction(
            0x1000,
            0,
            4,
            struct.pack("<ii", -10005, -10021),
            0x14,
        )
        move = self.instruction(
            0x1014,
            0,
            45,
            struct.pack("<fff", -10005.0, 1.0, 0.0),
            0x18,
        )
        sentinel = EclInstruction(
            0x102C, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=2,
            timer=0,
            timer_float=0.0,
            next_instruction=set_angle,
            ecl_program=(set_angle, move, sentinel),
        )
        state = snapshot(10, spawners=(emitter,))
        hard = forecast_world_births(state, ((100.0, 400.0),) * 2)
        self.assertEqual(hard.covered_frames, 2)
        self.assertEqual([len(items) for items in hard.births], [0, 1])
        self.assertEqual(hard.births[1][0].half_width, 4.0)

    def test_random_timed_body_envelope_follows_easing_progress(self):
        random_heading = self.instruction(
            0x1000,
            0,
            50,
            struct.pack("<ff", -math.pi, math.pi),
            0x14,
        )
        speed = self.instruction(
            0x1014,
            0,
            47,
            struct.pack("<f", 2.0),
            0x10,
        )
        timed_move = self.instruction(
            0x1024,
            0,
            61,
            struct.pack("<i", 120),
            0x10,
        )
        sentinel = EclInstruction(
            0x1034, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(),
            x=100.0,
            y=144.0,
            velocity_x=0.0,
            speed=2.0,
            interval=0,
            next_instruction=random_heading,
            ecl_program=(random_heading, speed, timed_move, sentinel),
            hitbox_half_width=16.0,
            hitbox_half_height=18.0,
            interactable=True,
            collidable=True,
            lower_move_x=0.0,
            lower_move_y=0.0,
            upper_move_x=384.0,
            upper_move_y=448.0,
            should_clamp_position=True,
        )
        state = snapshot(10, spawners=(emitter,))
        positions = ((100.0, 400.0),) * 8

        hard = forecast_world_births(state, positions)
        radii = tuple(
            (frame[0][2] - frame[0][0]) / 2.0 - 16.0
            for frame in hard.body_hazards
        )

        self.assertAlmostEqual(radii[0], 0.0)
        self.assertGreater(radii[1], 0.0)
        self.assertLess(radii[1], 3.0)
        self.assertEqual(radii, tuple(sorted(radii)))

        for seed in range(32):
            exact = forecast_world_births(
                replace(state, rng_seed=seed),
                positions,
                rng_mode="nominal",
            )
            for outer_frame, exact_frame in zip(
                hard.body_hazards,
                exact.body_hazards,
            ):
                outer = outer_frame[0]
                inner = exact_frame[0]
                self.assertLessEqual(outer[0], inner[0])
                self.assertLessEqual(outer[1], inner[1])
                self.assertGreaterEqual(outer[2], inner[2])
                self.assertGreaterEqual(outer[3], inner[3])

    def test_hard_world_propagates_rng_interval_into_bullet_speed(self):
        random_speed = self.instruction(
            0x1000,
            0,
            8,
            struct.pack("<if", -10005, 1.0),
            0x14,
        )
        add_minimum = self.instruction(
            0x1014,
            0,
            20,
            struct.pack("<iff", -10005, -10005.0, 1.0),
            0x18,
        )
        bullet = self.instruction(
            0x102C,
            0,
            67,
            struct.pack(
                "<hhii ffff I",
                0,
                0,
                1,
                1,
                -10005.0,
                0.0,
                0.0,
                0.0,
                4,
            ),
            0x30,
        )
        sentinel = EclInstruction(
            0x105C, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=random_speed,
            ecl_program=(random_speed, add_minimum, bullet, sentinel),
        )
        hard = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )
        self.assertEqual(hard.covered_frames, 1)
        self.assertEqual(len(hard.births[0]), 1)
        self.assertEqual(hard.births[0][0].speed, 1.5)

    def test_hard_world_subtracts_rng_interval_with_outward_bounds(self):
        random_value = self.instruction(
            0x1000,
            0,
            8,
            struct.pack("<if", -10005, 1.0),
            0x14,
        )
        subtract = self.instruction(
            0x1014,
            0,
            21,
            struct.pack("<iff", -10005, 3.0, -10005.0),
            0x18,
        )
        bullet = self.instruction(
            0x102C,
            0,
            67,
            struct.pack(
                "<hhii ffff I",
                0,
                0,
                1,
                1,
                -10005.0,
                0.0,
                0.0,
                0.0,
                4,
            ),
            0x30,
        )
        sentinel = EclInstruction(
            0x105C, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            interval=0,
            next_instruction=random_value,
            ecl_program=(random_value, subtract, bullet, sentinel),
        )

        hard = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )

        self.assertEqual(hard.covered_frames, 1)
        self.assertEqual(len(hard.births[0]), 1)
        # 3 - RNG[0, 1] is [2, 3], then the rank adjustment is -0.5.
        self.assertEqual(hard.births[0][0].speed, 2.5)

    def test_hard_world_encloses_rng_derived_shoot_offset(self):
        random_x = self.instruction(
            0x1000,
            0,
            8,
            struct.pack("<if", -10005, 10.0),
            0x14,
        )
        shoot_offset = self.instruction(
            0x1014,
            0,
            81,
            struct.pack("<fff", -10005.0, 4.0, 0.0),
            0x18,
        )
        bullet = self.instruction(
            0x102C,
            0,
            67,
            struct.pack(
                "<hhii ffff I",
                0,
                0,
                1,
                1,
                2.0,
                0.0,
                0.0,
                0.0,
                4,
            ),
            0x30,
        )
        sentinel = EclInstruction(
            0x105C, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            x=20.0,
            y=30.0,
            velocity_x=0.0,
            shoot_offset_x=0.0,
            shoot_offset_y=0.0,
            interval=0,
            next_instruction=random_x,
            ecl_program=(random_x, shoot_offset, bullet, sentinel),
        )

        hard = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),),
        )

        self.assertEqual(hard.covered_frames, 1)
        self.assertEqual(len(hard.births[0]), 1)
        self.assertEqual(hard.births[0][0].x, 25.0)
        self.assertEqual(hard.births[0][0].y, 34.0)
        self.assertEqual(hard.births[0][0].half_width, 8.0)
        self.assertEqual(hard.births[0][0].half_height, 3.0)

    def test_world_retains_accelerating_emitter_motion_between_frames(self):
        sentinel = EclInstruction(
            0x2000, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1),
            x=0.0,
            y=0.0,
            velocity_x=1.0,
            velocity_y=0.0,
            angle=0.0,
            speed=1.0,
            acceleration=1.0,
            movement_mode=1,
            shoot_offset_x=0.0,
            shoot_offset_y=0.0,
            interval=3,
            timer=0,
            timer_float=0.0,
            next_instruction=sentinel,
            ecl_program=(sentinel,),
        )
        forecast = forecast_world_births(
            snapshot(
                10,
                spawners=(emitter,),
                bullet_sizes=((3.0, 3.0),),
            ),
            ((100.0, 400.0),) * 3,
        )
        self.assertEqual(forecast.covered_frames, 3)
        self.assertEqual([len(items) for items in forecast.births], [0, 0, 1])
        self.assertAlmostEqual(forecast.births[2][0].x, 6.0)

    def test_hard_authority_rejects_a_source_defined_unborn_hazard(self):
        sentinel = EclInstruction(
            0x2000, -1, 0, 0, 0, (b"\xff" * 12).hex()
        )
        emitter = spawner(
            pattern(count1=1, count2=1, aim_mode=0),
            x=100.0,
            y=0.0,
            velocity_x=0.0,
            velocity_y=0.0,
            shoot_offset_x=0.0,
            shoot_offset_y=0.0,
            interval=1,
            timer=0,
            timer_float=0.0,
            next_instruction=sentinel,
            ecl_program=(sentinel,),
        )
        state = snapshot(
            10,
            spawners=(emitter,),
            bullet_sizes=((3.0, 3.0),),
        )
        self.assertEqual(certify_actions(state, 4), ())


if __name__ == "__main__":
    unittest.main()
