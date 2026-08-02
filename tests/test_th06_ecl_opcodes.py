import math
import struct
import unittest
from dataclasses import replace

from th06.hazards.ecl import (
    ECL_OPCODE_COUNT,
    FAIL_CLOSED_ECL_OPCODES,
    HAZARD_NEUTRAL_ECL_OPCODES,
    MODELLED_ECL_OPCODES,
    forecast_ecl_births,
)
from th06.model import EnemySpawner, EclInstruction


def instruction(address: int, opcode: int, args: bytes, size: int) -> EclInstruction:
    raw = struct.pack("<ihhBBBB", 0, opcode, size, 0, 4, 0, 0) + args
    raw += bytes(max(0, size - len(raw)))
    return EclInstruction(address, 0, opcode, size, 4, raw.hex())


def emitter(first: EclInstruction, sentinel: EclInstruction) -> EnemySpawner:
    return EnemySpawner(
        slot=0,
        x=10.0,
        y=20.0,
        velocity_x=0.0,
        velocity_y=0.0,
        angle=0.0,
        angular_velocity=0.0,
        speed=2.0,
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
        shoot_offset_x=0.0,
        shoot_offset_y=0.0,
        bullet_rank_speed_low=-0.5,
        bullet_rank_speed_high=0.5,
        bullet_rank_amount1_low=0,
        bullet_rank_amount1_high=0,
        bullet_rank_amount2_low=0,
        bullet_rank_amount2_high=0,
        life=10,
        shooting_disabled=False,
        interval=0,
        timer=0,
        timer_float=0.0,
        pattern=None,
        ecl_time=0,
        ecl_time_float=0.0,
        ecl_ints=(0,) * 8,
        ecl_floats=(0.0,) * 4,
        ecl_compare=0,
        repeat_ex_index=None,
        next_instruction=first,
        ecl_program=(first, sentinel),
        hitbox_half_width=3.0,
        hitbox_half_height=4.0,
        interactable=True,
        collidable=True,
    )


class EclOpcodeCoverageTests(unittest.TestCase):
    def test_every_source_opcode_has_one_authority_classification(self):
        groups = (
            MODELLED_ECL_OPCODES,
            HAZARD_NEUTRAL_ECL_OPCODES,
            frozenset(FAIL_CLOSED_ECL_OPCODES),
        )
        self.assertEqual(set().union(*groups), set(range(ECL_OPCODE_COUNT)))
        for index, left in enumerate(groups):
            for right in groups[index + 1:]:
                self.assertFalse(left & right)

    def test_every_hazard_neutral_opcode_advances_coverage(self):
        for opcode in sorted(HAZARD_NEUTRAL_ECL_OPCODES):
            with self.subTest(opcode=opcode):
                first = instruction(0x1000, opcode, bytes(68), 0x50)
                sentinel = EclInstruction(
                    0x1050, -1, 0, 0, 0, (bytes(12)).hex()
                )
                forecast = forecast_ecl_births(
                    emitter(first, sentinel),
                    ((100.0, 400.0),),
                    difficulty=2,
                    rank=0,
                    bullet_sizes=(),
                )
                self.assertEqual(forecast.covered_frames, 1, forecast.reason)

    def test_move_time_accelerate_matches_source_interpolation(self):
        # Opcode 63 calls MoveTime and selects easing type 3.  The source
        # displacement is cos(angle) * speed * duration / 2.
        first = instruction(
            0x1000,
            63,
            struct.pack("<iffff", 4, 0.0, 0.0, 0.0, 0.0),
            0x20,
        )
        sentinel = EclInstruction(0x1020, -1, 0, 0, 0, bytes(12).hex())
        forecast = forecast_ecl_births(
            emitter(first, sentinel),
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(forecast.covered_frames, 4)
        self.assertEqual(forecast.reason, "")
        self.assertIsNotNone(forecast.next_spawner)
        self.assertAlmostEqual(forecast.next_spawner.x, 14.0)
        centers = [
            (box[0] + box[2]) / 2.0
            for frame in forecast.body_hazards
            for box in frame
        ]
        self.assertEqual(len(centers), 4)
        for actual, expected in zip(centers, (10.0, 10.25, 11.0, 14.0)):
            self.assertTrue(math.isclose(actual, expected, abs_tol=1e-6))

    def test_unmodelled_hazard_opcode_has_specific_fail_closed_reason(self):
        first = instruction(0x1000, 85, bytes(68), 0x50)
        sentinel = EclInstruction(0x1050, -1, 0, 0, 0, bytes(12).hex())
        forecast = forecast_ecl_births(
            emitter(first, sentinel),
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )
        self.assertEqual(forecast.covered_frames, 0)
        self.assertIn("laser creation", forecast.reason)
        self.assertNotIn("unsupported ECL opcode", forecast.reason)

    def test_boss_timer_setup_remains_covered_before_its_callback(self):
        timer = instruction(0x1000, 112, struct.pack("<i", 0), 0x10)
        threshold = instruction(0x1010, 115, struct.pack("<i", 1200), 0x10)
        callback = instruction(0x1020, 116, struct.pack("<i", 16), 0x10)
        sentinel = EclInstruction(0x1030, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(timer, sentinel),
            ecl_program=(timer, threshold, callback, sentinel),
        )

        forecast = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(forecast.covered_frames, 4)
        self.assertEqual(forecast.reason, "")
        self.assertEqual(forecast.next_spawner.timer_callback_threshold, 1200)
        self.assertEqual(forecast.next_spawner.timer_callback_sub, 16)
        self.assertEqual(forecast.next_spawner.boss_timer, 4)


if __name__ == "__main__":
    unittest.main()
