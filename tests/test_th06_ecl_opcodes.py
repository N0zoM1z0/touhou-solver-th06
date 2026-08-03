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

    def test_every_modelled_opcode_reaches_an_interpreter_branch(self):
        for opcode in sorted(MODELLED_ECL_OPCODES):
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
                self.assertNotEqual(
                    forecast.reason,
                    f"unclassified ECL opcode {opcode}",
                )

    def test_every_fail_closed_opcode_reaches_its_specific_branch(self):
        for opcode, reason in sorted(FAIL_CLOSED_ECL_OPCODES.items()):
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
                self.assertEqual(forecast.reason, reason)

    def test_hard_enemy_creation_audits_child_through_window(self):
        create = instruction(
            0x1000,
            95,
            struct.pack("<ifffhhi", 0, 10.0, 20.0, 0.0, 100, 0, 0),
            0x24,
        )
        parent_wait = replace(
            instruction(0x1024, 0, bytes(4), 0x10),
            time=50,
        )
        child_disable_body = instruction(
            0x2000, 117, struct.pack("<i", 0), 0x10
        )
        child_wait = replace(
            instruction(0x2010, 0, bytes(4), 0x10),
            time=50,
        )
        source = replace(
            emitter(create, parent_wait),
            interactable=False,
            ecl_subroutines=(child_disable_body.address,),
            ecl_program=(
                create,
                parent_wait,
                child_disable_body,
                child_wait,
            ),
        )

        hard = forecast_ecl_births(
            source,
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )
        longer = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )
        nominal = forecast_ecl_births(
            source,
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(hard.covered_frames, 1, hard.reason)
        self.assertEqual(hard.births, ((),))
        self.assertEqual(hard.body_hazards, ((),))
        self.assertEqual(longer.covered_frames, 4, longer.reason)
        self.assertEqual(longer.births, ((), (), (), ()))
        self.assertEqual(longer.body_hazards, ((), (), (), ()))
        self.assertEqual(nominal.covered_frames, 0)
        self.assertIn("world-emitter insertion", nominal.reason)

    def test_hard_enemy_creation_carries_future_child_body(self):
        create = instruction(
            0x1000,
            95,
            struct.pack("<ifffhhi", 0, 30.0, 40.0, 0.0, 100, 0, 0),
            0x24,
        )
        parent_wait = replace(
            instruction(0x1024, 0, bytes(4), 0x10),
            time=50,
        )
        child_wait = replace(
            instruction(0x2000, 0, bytes(4), 0x10),
            time=50,
        )
        source = replace(
            emitter(create, parent_wait),
            interactable=False,
            ecl_subroutines=(child_wait.address,),
            ecl_program=(create, parent_wait, child_wait),
        )

        hard = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 3,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )

        self.assertEqual(hard.covered_frames, 3, hard.reason)
        self.assertTrue(all(hard.body_hazards))

    def test_bullet_effects_survive_a_frame_boundary_and_reach_spawn(self):
        effects = instruction(
            0x1000,
            82,
            struct.pack("<iiiiffff", 1, 2, 3, 4, 0.5, 1.5, 2.5, 3.5),
            0x2C,
        )
        bullet = replace(
            instruction(
                0x102C,
                67,
                struct.pack(
                    "<hhIIffffI", 0, 0, 1, 1, 1.0, 0.3, 0.0, 0.0, 0x10
                ),
                0x2C,
            ),
            time=1,
        )
        sentinel = EclInstruction(0x1058, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(effects, sentinel),
            ecl_program=(effects, bullet, sentinel),
        )

        first_frame = forecast_ecl_births(
            source,
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
        )
        self.assertIsNotNone(first_frame.next_spawner)
        second_frame = forecast_ecl_births(
            first_frame.next_spawner,
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
        )

        self.assertEqual(len(second_frame.births[0]), 1)
        spawned = second_frame.births[0][0]
        self.assertEqual(spawned.acceleration_duration, 1)
        self.assertAlmostEqual(spawned.acceleration_x, math.cos(1.5) * 0.5)
        self.assertAlmostEqual(spawned.acceleration_y, math.sin(1.5) * 0.5)

    def test_hard_forecast_unions_reachable_life_callback_timing(self):
        waiting = replace(
            instruction(0x1000, 1, bytes(4), 0x10),
            time=10000,
        )
        callback_bullet = instruction(
            0x2000,
            67,
            struct.pack(
                "<hhIIffffI", 0, 0, 1, 1, 1.0, 0.3, 0.0, 0.0, 0
            ),
            0x2C,
        )
        sentinel = EclInstruction(0x202C, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(waiting, sentinel),
            life=10,
            life_callback_threshold=5,
            life_callback_sub=0,
            ecl_subroutines=(0x2000,),
            ecl_program=(waiting, callback_bullet, sentinel),
        )

        forecast = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 2,
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )

        self.assertEqual(forecast.covered_frames, 2, forecast.reason)
        self.assertEqual([len(frame) for frame in forecast.births], [0, 1])

    def test_hard_forecast_unions_reachable_death_callback_timing(self):
        waiting = replace(
            instruction(0x1000, 1, bytes(4), 0x10),
            time=10000,
        )
        callback_bullet = instruction(
            0x2000,
            67,
            struct.pack(
                "<hhIIffffI", 0, 0, 1, 1, 1.0, 0.3, 0.0, 0.0, 0
            ),
            0x2C,
        )
        sentinel = EclInstruction(0x202C, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(waiting, sentinel),
            life=10,
            death_callback_sub=0,
            death_mode=1,
            ecl_subroutines=(0x2000,),
            ecl_program=(waiting, callback_bullet, sentinel),
            is_boss=True,
        )

        forecast = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 2,
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )

        self.assertEqual(forecast.covered_frames, 2, forecast.reason)
        self.assertEqual([len(frame) for frame in forecast.births], [0, 1])

        despawning = forecast_ecl_births(
            replace(source, death_mode=0),
            ((100.0, 400.0),) * 2,
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )
        self.assertEqual(despawning.covered_frames, 2, despawning.reason)
        self.assertEqual([len(frame) for frame in despawning.births], [0, 0])

    def test_ecl_life_set_runs_certain_death_callback_on_next_update(self):
        life_set = instruction(0x1000, 111, struct.pack("<i", 0), 0x10)
        waiting = replace(
            instruction(0x1010, 1, bytes(4), 0x10),
            time=10000,
        )
        callback_bullet = instruction(
            0x2000,
            67,
            struct.pack(
                "<hhIIffffI", 0, 0, 1, 1, 1.0, 0.3, 0.0, 0.0, 0
            ),
            0x2C,
        )
        sentinel = EclInstruction(0x202C, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(life_set, waiting),
            collidable=False,
            damageable=False,
            death_callback_sub=0,
            death_mode=3,
            is_boss=True,
            ecl_subroutines=(0x2000,),
            ecl_program=(life_set, waiting, callback_bullet, sentinel),
        )

        forecast = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 2,
            difficulty=2,
            rank=0,
            bullet_sizes=((2.0, 2.0),),
            allow_player_variables=False,
            radial_births=True,
            abstract_rng=True,
        )

        self.assertEqual(forecast.covered_frames, 2, forecast.reason)
        self.assertEqual([len(frame) for frame in forecast.births], [0, 1])
        self.assertIsNotNone(forecast.next_spawner)
        self.assertEqual(forecast.next_spawner.life, 1)
        self.assertEqual(forecast.next_spawner.death_mode, 0)
        self.assertEqual(forecast.next_spawner.death_callback_sub, -1)

    def test_death_flag_updates_the_source_three_bit_mode(self):
        death_flag = instruction(
            0x1000,
            107,
            struct.pack("<i", 9),
            0x10,
        )
        sentinel = EclInstruction(0x1010, -1, 0, 0, 0, bytes(12).hex())

        forecast = forecast_ecl_births(
            emitter(death_flag, sentinel),
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(forecast.covered_frames, 1, forecast.reason)
        self.assertEqual(forecast.next_spawner.death_mode, 1)

    def test_unconditional_jump_uses_its_short_source_layout(self):
        jump = instruction(
            0x1000,
            2,
            struct.pack("<ii", 0, 0x14),
            0x14,
        )
        sentinel = EclInstruction(0x1014, -1, 0, 0, 0, bytes(12).hex())

        forecast = forecast_ecl_births(
            emitter(jump, sentinel),
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(forecast.covered_frames, 1, forecast.reason)

    def test_set_opcodes_use_source_target_type_not_opcode_name(self):
        set_float_literal = instruction(
            0x1000,
            5,
            struct.pack("<if", -10006, 1.25),
            0x14,
        )
        setint_float_copy = instruction(
            0x1014,
            4,
            struct.pack("<ii", -10005, -10006),
            0x14,
        )
        setfloat_int_copy = instruction(
            0x1028,
            5,
            struct.pack("<ii", -10001, -10002),
            0x14,
        )
        sentinel = EclInstruction(0x103C, -1, 0, 0, 0, bytes(12).hex())
        source = replace(
            emitter(set_float_literal, sentinel),
            ecl_ints=(0, 7, 0, 0, 0, 0, 0, 0),
            ecl_program=(
                set_float_literal,
                setint_float_copy,
                setfloat_int_copy,
                sentinel,
            ),
        )

        forecast = forecast_ecl_births(
            source,
            ((100.0, 400.0),),
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )

        self.assertEqual(forecast.covered_frames, 1, forecast.reason)
        self.assertIsNotNone(forecast.next_spawner)
        self.assertEqual(forecast.next_spawner.ecl_floats[0], 1.25)
        self.assertEqual(forecast.next_spawner.ecl_ints[0], 7)

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

    def test_laser_creation_advances_only_while_source_timing_is_dormant(self):
        laser_args = struct.pack(
            "<hhffffffiiiiii",
            0,
            6,
            0.0,
            0.0,
            0.0,
            500.0,
            500.0,
            16.0,
            120,
            60,
            16,
            120,
            14,
            0,
        )
        dormant = replace(
            instruction(0x1000, 86, laser_args, 0x40),
            time=3,
        )
        sentinel = EclInstruction(
            0x1040, -1, 0, 0, 0, bytes(12).hex()
        )
        source = replace(
            emitter(dormant, sentinel),
            ecl_program=(dormant, sentinel),
        )

        covered = forecast_ecl_births(
            source,
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )
        self.assertEqual(covered.covered_frames, 4, covered.reason)

        immediate_args = bytearray(laser_args)
        struct.pack_into("<i", immediate_args, 28, 0)
        immediate = replace(
            instruction(0x1000, 86, bytes(immediate_args), 0x40),
            time=3,
        )
        blocked = forecast_ecl_births(
            replace(
                source,
                next_instruction=immediate,
                ecl_program=(immediate, sentinel),
            ),
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )
        self.assertEqual(blocked.covered_frames, 3)
        self.assertIn("aimed ECL laser creation", blocked.reason)

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

    def test_life_callback_uses_the_source_damage_cap(self):
        sentinel = EclInstruction(0x1000, -1, 0, 0, 0, bytes(12).hex())
        far = replace(
            emitter(sentinel, sentinel),
            life=13000,
            life_callback_threshold=1300,
            interactable=True,
            damageable=True,
            is_boss=True,
        )
        covered = forecast_ecl_births(
            far,
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )
        self.assertEqual(covered.covered_frames, 4)

        near = replace(far, life=1350)
        uncertain = forecast_ecl_births(
            near,
            ((100.0, 400.0),) * 4,
            difficulty=2,
            rank=0,
            bullet_sizes=(),
        )
        self.assertEqual(uncertain.covered_frames, 1)
        self.assertIn("life callback", uncertain.reason)


if __name__ == "__main__":
    unittest.main()
