import math
import struct
import unittest
from dataclasses import replace

from th06.hazards.births import (
    UnsupportedBirthModel,
    periodic_births,
    periodic_hazards_by_frame,
    spawn_pattern,
    spawn_pattern_envelope,
)
from th06.hazards.ecl import forecast_ecl_births
from th06.hazards.rng import RngState
from th06.hazards.world import forecast_world_births
from th06.birth_parity import compare_periodic_births
from th06.model import (
    BulletPattern,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
    Snapshot,
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

    def test_hard_world_still_fails_closed_on_discrete_rng_control(self):
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
        self.assertEqual(hard.covered_frames, 0)
        self.assertIn("discrete uncertainty", hard.reason)
        nominal = forecast_world_births(
            state,
            ((100.0, 400.0),),
            rng_mode="nominal",
        )
        self.assertEqual(nominal.covered_frames, 1)

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
