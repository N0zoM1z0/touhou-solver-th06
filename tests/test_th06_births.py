import math
import struct
import unittest
from dataclasses import replace

from th06.hazards.births import (
    UnsupportedBirthModel,
    periodic_births,
    periodic_hazards_by_frame,
    spawn_pattern,
)
from th06.hazards.ecl import forecast_ecl_births
from th06.hazards.rng import RngState
from th06.birth_parity import compare_periodic_births
from th06.model import BulletPattern, EnemySpawner, EclInstruction, Snapshot


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


if __name__ == "__main__":
    unittest.main()
