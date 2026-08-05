import struct
import unittest
from dataclasses import asdict, replace
from unittest import mock

from counterexample_corpus import load_cases

from th06.barrage_lab.assets import (
    Pbg3Archive,
    parse_ecl_bullet_opcodes,
)
from th06.barrage_lab.corpus import decode_snapshot
from th06.barrage_lab.generator import (
    BARRAGE_FAMILIES,
    generate_barrage_births,
    generate_barrage_case,
    horizontal_band_count,
    runtime_barrage_template,
    stress_player_position,
)
from th06.barrage_lab.oracle import certify_linear_source
from th06.barrage_lab.planner import PlannerGuidanceValue, source_terminal_counts
from th06.barrage_lab.runner import (
    PlannerMismatch,
    SweepMismatch,
    python_terminal_guidance,
    python_terminal_counts,
    shrink_planner_mismatch,
    python_action_names,
    shrink_mismatch,
    source_terminal_guidance,
)
from th06.barrage_lab.temporal import run_proposal_temporal_sweep
from th06.barrage_lab.stateful import (
    ExactTerminalPolicy,
    UnsupportedStatefulModel,
    causal_branch_diversity,
    derive_nominal_battle_worlds,
    physical_step_parity,
    run_closed_loop,
    step_bullet,
    step_closed_world,
    step_nominal_battle_world,
    step_fired_bullet,
    sweep_initial_snapshot,
    _terminal_metric,
    _terminal_action_metric,
    _authority_filtered_preferred,
    _deep_preferred_within,
    _progressive_delivery_preferred,
    _terminal_preferred,
    _terminal_rungs,
)
from th06.hazards.bullets import hazard_box
from th06.hazards.ecl import source_enemy_template
from th06.hazards.world import (
    WorldBirthForecast,
    WorldForecastContinuation,
)
from th06.model import (
    CONTROL_ACTIONS,
    Bullet,
    EclInstruction,
    Laser,
    PLAYER_DEAD,
    PlayerAttackState,
    SafeAction,
    Snapshot,
    StageTimelineInstruction,
    action_from_input,
)


class BitWriter:
    def __init__(self):
        self.bits = []

    def bit(self, value):
        self.bits.append(int(bool(value)))

    def integer(self, value, width):
        for shift in range(width - 1, -1, -1):
            self.bit(value & (1 << shift))

    def varint(self, value):
        width = next(width for width in (8, 16, 24, 32) if value < 1 << width)
        header = {8: 0, 16: 1, 24: 2, 32: 3}[width]
        self.integer(header, 2)
        self.integer(value, width)

    def bytes(self):
        while len(self.bits) % 8:
            self.bit(0)
        result = bytearray()
        for start in range(0, len(self.bits), 8):
            value = 0
            for bit in self.bits[start:start + 8]:
                value = (value << 1) | bit
            result.append(value)
        return bytes(result)


def literal_stream(data):
    writer = BitWriter()
    for value in data:
        writer.bit(1)
        writer.integer(value, 8)
    writer.bit(0)
    writer.integer(0, 13)
    return writer.bytes()


def ecl_bytes():
    header = struct.pack("<hhIII", 1, 0, 0, 0, 0) + struct.pack("<I", 20)
    instruction = struct.pack(
        "<ihhBBBBhhiiffffi",
        17, 67, 44, 0, 0x04, 0, 0,
        2, 7, 5, 3, 4.0, 1.0, 0.25, 0.1, 0x04,
    )
    terminal = struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0)
    return header + instruction + terminal


def ecl_effect_bytes():
    header = struct.pack("<hhIII", 1, 0, 0, 0, 0) + struct.pack("<I", 20)
    effects = struct.pack(
        "<ihhBBBBiiiiffff",
        0, 82, 44, 0, 0x04, 0, 0,
        40, 1, -1, -1, 1.5, 2.0, -1.0, -1.0,
    )
    bullet = struct.pack(
        "<ihhBBBBhhiiffffi",
        0, 68, 44, 0, 0x04, 0, 0,
        2, 7, 5, 3, 4.0, 1.0, 0.25, 0.1, 0x44,
    )
    terminal = struct.pack("<ihhBBBB", -1, -1, 12, 0, 0xFF, 0, 0)
    return header + effects + bullet + terminal


def pbg3_bytes(name, payload):
    compressed = literal_stream(payload)
    data_offset = 7
    table_offset = data_offset + len(compressed)
    header = BitWriter()
    header.varint(1)
    header.varint(table_offset)
    header_bytes = header.bytes()
    assert len(header_bytes) == 3
    table = BitWriter()
    table.varint(0)
    table.varint(0)
    table.varint(sum(compressed))
    table.varint(data_offset)
    table.varint(len(payload))
    for value in name.encode("ascii") + b"\0":
        table.integer(value, 8)
    return b"PBG3" + header_bytes + compressed + table.bytes()


class BarrageLabTests(unittest.TestCase):
    def test_stateful_horizontal_band_counterexamples(self):
        for case in load_cases():
            if case.get("runner") != "barrage_stateful_policy":
                continue
            snapshot = decode_snapshot(case["input"]["snapshot"])
            for metric in (
                "count",
                "authority-filtered-count",
                "delivery-filtered-count",
            ):
                expected = case["expect"][metric]
                result = run_closed_loop(
                    snapshot,
                    ExactTerminalPolicy(
                        case["input"]["horizon"], metric=metric
                    ),
                    frames=case["input"]["frames"],
                    delivery_seed=case["input"]["delivery_seed"],
                )
                self.assertEqual(
                    result.decision_trace[0][1], expected["first_action"]
                )
                self.assertEqual(result.outcome, expected["outcome"])
                self.assertEqual(
                    result.survived_frames, expected["survived_frames"]
                )

    def test_horizontal_band_family_builds_mature_layered_source_fans(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]

        first = generate_barrage_case(
            (opcode,),
            17,
            target_bullets=192,
            player_position=(166.0, 427.0),
            barrage_family="horizontal-bands",
        )
        second = generate_barrage_case(
            (opcode,),
            17,
            target_bullets=192,
            player_position=(166.0, 427.0),
            barrage_family="horizontal-bands",
        )

        self.assertIn(first.family, BARRAGE_FAMILIES)
        self.assertEqual(first, second)
        self.assertEqual(len(first.snapshot.bullets), 192)
        self.assertGreaterEqual(
            horizontal_band_count(first.snapshot.bullets), 4
        )
        self.assertTrue(all(
            bullet.state == 1 and bullet.timer >= 32
            for bullet in first.snapshot.bullets
        ))

    def test_horizontal_births_keep_aimed_fan_source_geometry(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = generate_barrage_case(
            (opcode,), 3, target_bullets=8
        ).snapshot

        births = generate_barrage_births(
            (opcode,),
            11,
            snapshot,
            frames=12,
            events=3,
            barrage_family="horizontal-bands",
        )

        self.assertEqual(len(births), 3)
        self.assertTrue(all(event.pattern.aim_mode == 0 for event in births))
        self.assertTrue(all(event.pattern.count1 >= 3 for event in births))
        self.assertTrue(all(-24.0 <= event.origin[1] <= 144.0 for event in births))

    def test_stateful_sweep_can_start_from_multiple_physical_bullet_worlds(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        base = generate_barrage_case(
            (opcode,), 5, target_bullets=8
        ).snapshot
        worlds = (
            replace(base, frame=100, x=80.0),
            replace(base, frame=101, x=304.0),
        )

        first = sweep_initial_snapshot(
            (opcode,), 0, physical_initial_worlds=worlds
        )
        second = sweep_initial_snapshot(
            (opcode,), 1, physical_initial_worlds=worlds
        )

        self.assertEqual((first.frame, first.x), (100, 80.0))
        self.assertEqual((second.frame, second.x), (101, 304.0))
        self.assertEqual(first.bullets, worlds[0].bullets)
        battle = sweep_initial_snapshot(
            (opcode,), 0, physical_battle_worlds=worlds
        )
        self.assertIs(battle, worlds[0])
        with self.assertRaises(ValueError):
            sweep_initial_snapshot(
                (opcode,),
                0,
                runtime_templates=(runtime_barrage_template({
                    "x": 80.0, "y": 200.0, "bullets": (),
                }),),
                physical_initial_worlds=worlds,
            )

    def test_nominal_battle_step_keeps_source_world_births_and_rng(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 7, target_bullets=1)
        start = replace(
            case.snapshot,
            bullets=(),
            input_mask=0x05,
            timeline_instructions=(),
            timeline_complete=True,
        )
        newborn = replace(case.snapshot.bullets[0], slot=-1)
        empty = ((),)
        forecast = WorldBirthForecast(
            births=((newborn,),),
            hazards=empty,
            covered_frames=1,
            body_hazards=empty,
            continuation=WorldForecastContinuation(
                (), 0x4567, 99, True, 1
            ),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )

        with mock.patch(
            "th06.barrage_lab.stateful.forecast_world_births",
            return_value=forecast,
        ):
            following = step_nominal_battle_world(start, right)

        self.assertEqual(following.frame, start.frame + 1)
        self.assertEqual(following.x, start.x + start.focus_speed)
        self.assertEqual((following.rng_seed, following.rng_generation), (0x4567, 99))
        self.assertEqual(len(following.bullets), 1)
        self.assertEqual(following.bullets[0].slot, 0)

    def test_nominal_battle_step_retains_occupied_timeline_boss_wait(self):
        wait = EclInstruction(
            0x1000, 999, 0, 12, 4,
            struct.pack("<ihhBBBB", 999, 0, 12, 0, 4, 0, 0).hex(),
        )
        emitter = source_enemy_template(
            (wait,), (wait.address,), 0, 100.0, 100.0, 100,
        )
        self.assertIsNotNone(emitter)
        emitter = replace(emitter, slot=0)
        timeline_wait = StageTimelineInstruction(
            0x2000,
            5282,
            0,
            12,
            8,
            struct.pack("<hBBi", 5282, 0, 12, 0).hex(),
        )
        terminal = StageTimelineInstruction(
            0x2008,
            -1,
            0,
            0,
            8,
            struct.pack("<hBBi", -1, 0, 0, 0).hex(),
        )
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        start = replace(
            generate_barrage_case((opcode,), 7, target_bullets=1).snapshot,
            bullets=(),
            spawners=(emitter,),
            timeline_time=5282,
            timeline_time_float=5282.0,
            timeline_time_previous=5281,
            timeline_instructions=(timeline_wait, terminal),
            timeline_complete=True,
            timeline_boss_slots=(0, -1, -1, -1, -1, -1, -1, -1),
        )
        forecast = WorldBirthForecast(
            births=((),),
            hazards=((),),
            covered_frames=1,
            body_hazards=((),),
            continuation=WorldForecastContinuation(
                (emitter,), start.rng_seed, start.rng_generation, True, 1, True,
            ),
        )
        stay = next(
            action for action in CONTROL_ACTIONS if action.name == "stay"
        )

        with mock.patch(
            "th06.barrage_lab.stateful.forecast_world_births",
            return_value=forecast,
        ) as forecast_world:
            following = step_nominal_battle_world(start, stay)

        self.assertEqual(
            (
                following.timeline_time_previous,
                following.timeline_time,
                following.timeline_time_float,
            ),
            (5281, 5282, 5282.0),
        )
        self.assertEqual(following.timeline_instructions, start.timeline_instructions)
        self.assertEqual(forecast_world.call_args.args[0].timeline_instructions, ())

    def test_candidate_path_changes_aim_damage_death_and_callback_birth(self):
        def instruction(address, time, opcode, args=b""):
            size = 12 + len(args)
            raw = struct.pack(
                "<ihhBBBB", time, opcode, size, 0, 4, 0, 0
            ) + args
            return EclInstruction(address, time, opcode, size, 4, raw.hex())

        def aimed_bullet(address):
            return instruction(
                address,
                0,
                67,
                struct.pack(
                    "<hhiiffffi", 2, 0, 1, 1, 4.0, 4.0, 0.0, 0.0, 4
                ),
            )

        initial = aimed_bullet(0x1000)
        initial_wait = instruction(0x102C, 999, 0)
        callback = aimed_bullet(0x2000)
        callback_wait = instruction(0x202C, 999, 0)
        program = (initial, initial_wait, callback, callback_wait)
        emitter = source_enemy_template(
            program, (initial.address, callback.address),
            0, 124.0, 112.0, 40,
        )
        self.assertIsNotNone(emitter)
        emitter = replace(
            emitter,
            slot=0,
            has_been_in_bounds=True,
            sprite_half_width=8.0,
            sprite_half_height=8.0,
            death_mode=1,
            death_callback_sub=1,
        )
        attack = PlayerAttackState(
            shots=(),
            last_enemy_hit_x=-999.0,
            last_enemy_hit_y=-999.0,
            orb_state=1,
            is_focus=False,
            focus_timer_previous=-999,
            focus_timer=0,
            focus_timer_float=0.0,
            # Timer five fires the four main shots but not the 16-frame orb
            # shots, so the collision difference comes only from the path.
            fire_timer_previous=4,
            fire_timer=5,
            fire_timer_float=5.0,
            orb_positions=((76.0, 120.0), (124.0, 120.0)),
            shot_type=0,
            bomb_active=False,
            spell_active=False,
        )
        root = Snapshot(
            frame=10,
            stage=5,
            player_state=0,
            x=100.0,
            y=120.0,
            half_width=1.25,
            half_height=1.25,
            normal_speed=4.0,
            focus_speed=2.0,
            normal_diagonal_speed=2.828427,
            focus_diagonal_speed=1.414214,
            frame_multiplier=1.0,
            input_mask=0x05,
            bullets=(),
            laser_count=0,
            in_menu=False,
            time_stopped=False,
            replay_or_demo=False,
            spawners=(emitter,),
            difficulty=2,
            bullet_sizes=((3.0, 3.0),) * 3,
            rng_seed=0x1234,
            current_power=128,
            timeline_complete=True,
            player_attack=attack,
            effect_active_upper_bound=0,
            item_active_upper_bound=0,
        )
        actions = {action.name: action for action in CONTROL_ACTIONS}

        left = step_nominal_battle_world(root, actions["left_fast"])
        right = step_nominal_battle_world(root, actions["right_fast"])

        self.assertNotEqual(left.bullets[0].angle, right.bullets[0].angle)
        self.assertEqual((left.spawners[0].life, left.spawners[0].interactable), (40, True))
        self.assertEqual((right.spawners[0].life, right.spawners[0].interactable), (0, False))
        self.assertEqual(right.spawners[0].next_instruction, callback)
        self.assertGreater(right.rng_generation, left.rng_generation)

        left_callback_frame = step_nominal_battle_world(
            left, actions["left_fast"]
        )
        right_callback_frame = step_nominal_battle_world(
            right, actions["right_fast"]
        )
        self.assertEqual(len(left_callback_frame.bullets), 1)
        self.assertEqual(len(right_callback_frame.bullets), 2)

        diversity = causal_branch_diversity(
            root,
            1,
            actions=(actions["left_fast"], actions["right_fast"]),
        )
        self.assertEqual(diversity.supported_actions, 2)
        self.assertEqual(diversity.unique_enemy_combat_states, 2)
        self.assertEqual(diversity.unique_rng_states, 2)

    def test_graze_is_one_shot_and_defers_effect_callback_rng(self):
        attack = PlayerAttackState(
            shots=(),
            last_enemy_hit_x=-999.0,
            last_enemy_hit_y=-999.0,
            orb_state=1,
            is_focus=True,
            focus_timer_previous=0,
            focus_timer=1,
            focus_timer_float=1.0,
            fire_timer_previous=0,
            fire_timer=1,
            fire_timer_float=1.0,
            orb_positions=((76.0, 400.0), (124.0, 400.0)),
            shot_type=0,
            bomb_active=False,
            spell_active=False,
        )
        root = Snapshot(
            frame=10,
            stage=5,
            player_state=0,
            x=100.0,
            y=200.0,
            half_width=1.25,
            half_height=1.25,
            normal_speed=4.0,
            focus_speed=2.0,
            normal_diagonal_speed=2.828427,
            focus_diagonal_speed=1.414214,
            frame_multiplier=1.0,
            input_mask=0x05,
            bullets=(Bullet(
                x=120.0,
                y=200.0,
                vx=0.0,
                vy=0.0,
                half_width=2.0,
                half_height=2.0,
                state=1,
                slot=0,
            ),),
            laser_count=0,
            in_menu=False,
            time_stopped=False,
            replay_or_demo=False,
            timeline_complete=True,
            rng_seed=0x1234,
            rng_generation=10,
            rank=31,
            subrank=96,
            max_rank=32,
            current_power=128,
            player_attack=attack,
            effect_active_upper_bound=1,
            item_active_upper_bound=0,
            # This effect was born after EffectManager on the root frame.
            pending_effect_rng_ids=(8,),
        )
        stay = next(action for action in CONTROL_ACTIONS if action.name == "stay")

        first = step_nominal_battle_world(root, stay)

        # The retained effect callback costs two u32/f32 draws (four u16),
        # then the new graze effect's time-zero SetRandomSprite costs one.
        self.assertEqual(first.rng_generation, 15)
        self.assertTrue(first.bullets[0].is_grazed)
        self.assertEqual((first.rank, first.subrank), (32, 2))
        self.assertEqual(first.pending_effect_rng_ids, (8,))
        self.assertEqual(first.effect_active_upper_bound, 2)

        second = step_nominal_battle_world(first, stay)

        # The same bullet cannot score or spawn another effect.  Only the
        # prior frame's deferred random-splash callback consumes RNG.
        self.assertEqual(second.rng_generation, 19)
        self.assertTrue(second.bullets[0].is_grazed)
        self.assertEqual((second.rank, second.subrank), (32, 2))
        self.assertEqual(second.pending_effect_rng_ids, ())
        self.assertEqual(second.effect_active_upper_bound, 2)

    def test_ecl_dropitems_inserts_typed_rng_conditioned_item_slots(self):
        def instruction(address, time, opcode, value):
            raw = struct.pack(
                "<ihhBBBBi", time, opcode, 16, 0, 4, 0, 0, value
            )
            return EclInstruction(address, time, opcode, 16, 4, raw.hex())

        drop = instruction(0x1000, 0, 119, 2)
        explicit = instruction(0x1010, 0, 124, 3)
        wait = instruction(0x1020, 999, 0, 0)
        emitter = source_enemy_template(
            (drop, explicit, wait),
            (drop.address,),
            0,
            100.0,
            100.0,
            100,
        )
        self.assertIsNotNone(emitter)
        emitter = replace(
            emitter,
            slot=0,
            has_been_in_bounds=True,
            sprite_half_width=8.0,
            sprite_half_height=8.0,
        )
        attack = PlayerAttackState(
            shots=(),
            last_enemy_hit_x=-999.0,
            last_enemy_hit_y=-999.0,
            orb_state=1,
            is_focus=True,
            focus_timer_previous=0,
            focus_timer=1,
            focus_timer_float=1.0,
            fire_timer_previous=0,
            fire_timer=1,
            fire_timer_float=1.0,
            orb_positions=((76.0, 400.0), (124.0, 400.0)),
            shot_type=0,
            bomb_active=False,
            spell_active=False,
        )
        root = Snapshot(
            frame=10,
            stage=5,
            player_state=0,
            x=192.0,
            y=400.0,
            half_width=1.25,
            half_height=1.25,
            normal_speed=4.0,
            focus_speed=2.0,
            normal_diagonal_speed=2.828427,
            focus_diagonal_speed=1.414214,
            frame_multiplier=1.0,
            input_mask=0x05,
            bullets=(),
            laser_count=0,
            in_menu=False,
            time_stopped=False,
            replay_or_demo=False,
            spawners=(emitter,),
            timeline_complete=True,
            rng_seed=0x1234,
            rng_generation=10,
            current_power=128,
            player_attack=attack,
            effect_active_upper_bound=0,
            item_active_upper_bound=0,
        )
        stay = next(action for action in CONTROL_ACTIONS if action.name == "stay")

        following = step_nominal_battle_world(root, stay)

        # DROPITEMS draws two f32 offsets per item (four u16 each).  At full
        # power both requests become point items before ItemManager moves them.
        self.assertEqual(following.rng_generation, 18)
        self.assertEqual(
            tuple(item.item_type for item in following.item_states),
            (1, 1, 3),
        )
        self.assertEqual(
            tuple(item.timer for item in following.item_states),
            (1, 1, 1),
        )
        self.assertEqual(following.item_next_index, 3)

    def test_nominal_battle_corpus_is_derived_through_stateful_play(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        base = generate_barrage_case(
            (opcode,), 7, target_bullets=1
        ).snapshot
        roots = (
            replace(
                base,
                frame=100,
                bullets=(),
                spawners=(),
                enemies=(),
                timeline_instructions=(),
                timeline_complete=True,
            ),
            replace(
                base,
                frame=200,
                bullets=(),
                spawners=(),
                enemies=(),
                timeline_instructions=(),
                timeline_complete=True,
            ),
        )
        lateral = tuple(
            action for action in CONTROL_ACTIONS
            if action.name in ("left", "right")
        )

        def certify(snapshot):
            return tuple(
                SafeAction(
                    action,
                    999.0,
                    snapshot.x + action.dx * 8.0,
                    snapshot.y,
                )
                for action in lateral
            )

        first, summary = derive_nominal_battle_worlds(
            roots,
            cases=4,
            maximum_warmup_frames=4,
            certifier=certify,
        )
        second, repeated = derive_nominal_battle_worlds(
            roots,
            cases=4,
            maximum_warmup_frames=4,
            certifier=certify,
        )

        self.assertEqual(first, second)
        self.assertEqual(summary, repeated)
        self.assertEqual(summary.generated_cases, 4)
        self.assertEqual(summary.outcomes, (("survived", 4),))
        self.assertEqual(summary.total_warmup_updates, 10)
        self.assertEqual(summary.total_born_bullets, 0)
        self.assertEqual(summary.source_root_frames, (100, 200))
        self.assertEqual(
            sorted(world.frame - (100 if world.frame < 200 else 200)
                   for world in first),
            [1, 2, 3, 4],
        )
        self.assertTrue(all(world.timeline_complete for world in first))

    def test_runtime_decoder_restores_hashable_future_ecl_program(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        state = generate_barrage_case((opcode,), 7, target_bullets=1).snapshot
        sentinel = EclInstruction(
            0x1000, -1, -1, 12, 0xFF, bytes(12).hex()
        )
        decoded = decode_snapshot(asdict(replace(
            state,
            ecl_subroutines=(sentinel.address,),
            timeline_ecl_program=(sentinel,),
            timeline_message_delays=((2, 240),),
        )))

        self.assertIsInstance(decoded.timeline_ecl_program, tuple)
        self.assertIsInstance(decoded.timeline_message_delays[0], tuple)
        self.assertEqual(hash(decoded.timeline_ecl_program), hash((sentinel,)))

    def test_source_archive_and_ecl_catalogue(self):
        archive = Pbg3Archive(pbg3_bytes("test.ecl", ecl_bytes()))
        self.assertEqual([entry.name for entry in archive.entries], ["test.ecl"])
        opcodes = parse_ecl_bullet_opcodes(
            archive.read("test.ecl"), "test.ecl"
        )
        self.assertEqual(len(opcodes), 1)
        opcode = opcodes[0]
        self.assertTrue(opcode.has_literal_arguments)
        self.assertTrue(opcode.executes_on(2))
        self.assertEqual((opcode.aim_mode, opcode.count1, opcode.count2), (0, 5, 3))

    def test_variable_pattern_is_not_claimed_literal(self):
        raw = bytearray(ecl_bytes())
        struct.pack_into("<i", raw, 20 + 16, -10001)
        opcode = parse_ecl_bullet_opcodes(bytes(raw), "vars.ecl")[0]
        self.assertFalse(opcode.has_literal_arguments)

        raw = bytearray(ecl_bytes())
        struct.pack_into("<f", raw, 20 + 24, -10005.0)
        opcode = parse_ecl_bullet_opcodes(bytes(raw), "float-vars.ecl")[0]
        self.assertFalse(opcode.has_literal_arguments)

    def test_literal_bullet_effects_follow_their_source_instruction(self):
        opcode = parse_ecl_bullet_opcodes(
            ecl_effect_bytes(), "effects.ecl"
        )[0]
        effects = opcode.effects_for(2)
        self.assertIsNotNone(effects)
        self.assertEqual(effects.ints[:2], (40, 1))
        self.assertEqual(effects.floats[:2], (1.5, 2.0))

    def test_seeded_source_case_matches_independent_oracle(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        first = generate_barrage_case((opcode,), 19, target_bullets=64)
        second = generate_barrage_case((opcode,), 19, target_bullets=64)
        self.assertEqual(first, second)
        expected = certify_linear_source(first.snapshot, 8).actions
        self.assertEqual(python_action_names(first.snapshot, 8), expected)
        self.assertEqual(len(first.snapshot.bullets), 64)

    def test_source_boundary_placements_are_deterministic_and_valid(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        position = stress_player_position(3, "corner")
        case = generate_barrage_case(
            (opcode,), 3, target_bullets=8, player_position=position
        )

        self.assertEqual(position, (376.0, 432.0))
        self.assertEqual((case.snapshot.x, case.snapshot.y), position)
        with self.assertRaises(ValueError):
            generate_barrage_case(
                (opcode,), 3, target_bullets=8,
                player_position=(377.0, 432.0),
            )

    def test_runtime_corpus_conditions_source_valid_dense_cases(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        template = runtime_barrage_template({
            "x": 152.0,
            "y": 229.941162109375,
            "input_mask": 0x80,
            "rank": 31,
            "bullets": [{}] * 80,
        }, density_scale=2.0)

        case = generate_barrage_case(
            (opcode,), 41, runtime_template=template
        )

        self.assertEqual(
            (case.snapshot.x, case.snapshot.y),
            (152.0, 229.941162109375),
        )
        self.assertEqual(case.snapshot.input_mask, 0x80)
        self.assertEqual(case.snapshot.rank, 31)
        self.assertEqual(len(case.snapshot.bullets), 160)
        self.assertEqual(
            python_action_names(case.snapshot, 4),
            certify_linear_source(case.snapshot, 4).actions,
        )

    def test_temporal_fuzz_bounds_directional_soft_proposals(self):
        summary, mismatch = run_proposal_temporal_sweep(512)

        self.assertIsNone(mismatch)
        self.assertEqual(summary.seeds, 512)
        self.assertGreater(summary.focused_cases, 0)
        self.assertGreater(summary.fast_cases, 0)

    def test_source_slowdown_is_projected_at_its_known_angle(self):
        bullet = Bullet(
            x=100.0, y=100.0, vx=0.0, vy=0.0,
            half_width=2.0, half_height=2.0, state=1,
            ex_flags=0x201, angle=0.0, speed=2.0,
            timer=11, timer_float=11.0,
        )
        self.assertEqual(hazard_box(bullet, 1), (101.5625, 98.0, 105.5625, 102.0))
        self.assertEqual(hazard_box(bullet, 2), (104.8125, 98.0, 108.8125, 102.0))

    def test_source_dynamic_precedence_delays_acceleration(self):
        bullet = Bullet(
            x=100.0, y=100.0, vx=2.0, vy=0.0,
            half_width=2.0, half_height=2.0, state=1,
            ex_flags=0x11, angle=0.0, speed=2.0,
            acceleration_x=1.0, acceleration_y=0.0,
            acceleration_duration=30, timer=16, timer_float=16.0,
        )
        self.assertEqual(hazard_box(bullet, 1), (100.0, 98.0, 104.0, 102.0))
        self.assertEqual(hazard_box(bullet, 2), (102.0, 98.0, 106.0, 102.0))
        self.assertEqual(hazard_box(bullet, 3), (105.0, 98.0, 109.0, 102.0))

    def test_stateful_fired_step_matches_source_projection_state(self):
        bullet = Bullet(
            x=100.0, y=100.0, vx=2.0, vy=0.0,
            half_width=2.0, half_height=2.0, state=1,
            ex_flags=0x11, angle=0.0, speed=2.0,
            acceleration_x=1.0, acceleration_y=0.0,
            acceleration_duration=30, timer=16, timer_float=16.0,
        )

        first = step_fired_bullet(bullet)
        second = step_fired_bullet(first)
        third = step_fired_bullet(second)

        self.assertEqual((first.x, second.x, third.x), (102.0, 104.0, 107.0))
        self.assertEqual((first.timer, third.timer_float), (17, 19.0))
        self.assertEqual(first.ex_flags, 0x11)
        self.assertEqual(second.ex_flags, 0x10)
        self.assertEqual(third.vx, 3.0)

        spawning = replace(
            bullet,
            state=3,
            ex_flags=0,
            timer=14,
            timer_float=14.0,
        )
        penultimate = step_bullet(spawning)
        fired = step_bullet(penultimate)
        self.assertEqual(penultimate.state, 3)
        self.assertAlmostEqual(penultimate.x, 100.8, places=5)
        self.assertEqual((fired.state, fired.timer), (1, 1))
        self.assertAlmostEqual(fired.x, 103.6, places=4)

        homing = replace(
            bullet,
            ex_flags=0x80,
            speed=3.0,
            turn_speed=2.0,
            timer=5,
            timer_float=5.0,
            direction_interval=5,
            direction_num_times=0,
            direction_max_times=1,
        )
        aimed = step_bullet(homing, (100.0, 200.0))
        self.assertAlmostEqual(aimed.x, 100.0, places=5)
        self.assertAlmostEqual(aimed.y, 102.0, places=5)
        self.assertEqual((aimed.ex_flags, aimed.direction_num_times), (0, 1))

    def test_fired_bullet_retires_only_after_visual_sprite_leaves_bounds(self):
        touching = Bullet(
            x=-3.0,
            y=100.0,
            vx=-1.0,
            vy=0.0,
            half_width=2.0,
            half_height=2.0,
            state=1,
            sprite_half_width=4.0,
            sprite_half_height=4.0,
        )

        boundary = step_fired_bullet(touching)
        self.assertIsNotNone(boundary)
        self.assertEqual(boundary.x, -4.0)
        self.assertIsNone(step_fired_bullet(boundary))

    def test_direction_bullet_out_of_bounds_counter_resets_and_caps(self):
        persistent = Bullet(
            x=-5.0,
            y=100.0,
            vx=0.0,
            vy=0.0,
            half_width=2.0,
            half_height=2.0,
            state=1,
            ex_flags=0x40,
            speed=0.0,
            turn_speed=0.0,
            direction_interval=100,
            direction_max_times=3,
            sprite_half_width=4.0,
            sprite_half_height=4.0,
        )

        outside = step_fired_bullet(persistent)
        self.assertIsNotNone(outside)
        self.assertEqual(outside.out_of_bounds_frames, 1)

        reentered = step_fired_bullet(replace(
            outside,
            x=1.0,
            vx=0.0,
        ))
        self.assertIsNotNone(reentered)
        self.assertEqual(reentered.out_of_bounds_frames, 0)

        self.assertIsNone(step_fired_bullet(replace(
            persistent,
            out_of_bounds_frames=0xFF,
        )))

    def test_stateful_world_and_physical_player_parity_are_closed_loop(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 7, target_bullets=8)
        right = next(action for action in CONTROL_ACTIONS if action.name == "right")
        start = replace(
            case.snapshot,
            frame=100,
            input_mask=0x05,
            bullets=tuple(
                replace(bullet, x=-1000.0, y=-1000.0)
                for bullet in case.snapshot.bullets
            ),
        )
        following = step_closed_world(start, right)
        parity = physical_step_parity((start, following))

        self.assertEqual(parity.adjacent_pairs, 1)
        self.assertEqual(parity.exact_player_steps, 1)
        self.assertEqual(
            parity.exact_fired_bullet_steps,
            parity.fired_bullet_steps,
        )
        self.assertLessEqual(parity.maximum_bullet_error, 1e-4)

        laser = Laser(
            x=1000.0,
            y=1000.0,
            angle=0.0,
            start_offset=0.0,
            end_offset=50.0,
            start_length=100.0,
            width=16.0,
            speed=2.0,
            start_time=10,
            hitbox_start_time=100,
            duration=60,
            despawn_duration=10,
            hitbox_end_delay=5,
            timer=9,
            timer_float=9.0,
            flags=0,
            state=0,
            slot=3,
        )
        laser_start = replace(start, lasers=(laser,), laser_count=1)
        laser_following = replace(
            following,
            lasers=(replace(
                laser,
                end_offset=52.0,
                timer=10,
                timer_float=10.0,
            ),),
            laser_count=1,
        )
        laser_parity = physical_step_parity(
            (laser_start, laser_following)
        )

        self.assertEqual(laser_parity.laser_steps, 1)
        self.assertEqual(laser_parity.exact_laser_steps, 1)
        self.assertEqual(laser_parity.maximum_laser_error, 0.0)
        self.assertEqual(laser_parity.first_laser_mismatch, "")

        result = run_closed_loop(
            replace(start, bullets=()),
            lambda _snapshot: right,
            frames=3,
            delivery_seed=1,
        )
        self.assertEqual(result.outcome, "survived")
        self.assertEqual(result.actions, ("stay", "right", "right"))

        with mock.patch(
            "th06.barrage_lab.stateful.certify_linear_source",
            wraps=certify_linear_source,
        ) as certify:
            run_closed_loop(
                replace(start, bullets=()),
                lambda _snapshot: right,
                frames=2,
                delivery_seed=3,
            )
        self.assertIn(1, [call.args[1] for call in certify.call_args_list])
        self.assertNotIn(4, [call.args[1] for call in certify.call_args_list])
        self.assertIn(
            (0,),
            [call.kwargs.get("delivery_delays") for call in certify.call_args_list],
        )

        phase_result = run_closed_loop(
            replace(start, bullets=()),
            lambda _snapshot: right,
            frames=8,
            delivery_seed=0,
            stop_when=lambda state: state.frame >= 101,
            stop_outcome="phase-exit",
        )
        self.assertEqual(phase_result.outcome, "phase-exit")
        self.assertEqual(phase_result.survived_frames, 1)

        dead_root = replace(start, bullets=())
        held = action_from_input(dead_root.input_mask)
        with mock.patch(
            "th06.barrage_lab.stateful.step_nominal_battle_world",
            side_effect=lambda state, _action: replace(
                state,
                frame=state.frame + 1,
                player_state=PLAYER_DEAD,
            ),
        ):
            lethal = run_closed_loop(
                dead_root,
                lambda _snapshot: held,
                frames=3,
                delivery_seed=0,
                battle_world=True,
            )
        self.assertEqual(lethal.outcome, "hit")
        self.assertEqual(lethal.survived_frames, 1)

    def test_stateful_world_rejects_unproved_despawn_animation(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 7, target_bullets=1)
        despawning = replace(case.snapshot.bullets[0], state=5)

        with self.assertRaises(UnsupportedStatefulModel):
            step_closed_world(
                replace(case.snapshot, bullets=(despawning,)),
                CONTROL_ACTIONS[0],
            )

    def test_scheduled_ecl_birth_uses_source_chain_order_and_rng(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 7, target_bullets=1)
        start = replace(case.snapshot, bullets=(), input_mask=0x05)
        schedule = generate_barrage_births(
            (opcode,), 9, start, frames=8, events=1
        )
        event = schedule[0]
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )

        following = step_closed_world(
            start, right, ((event.pattern, event.origin),)
        )

        self.assertEqual(len(following.bullets), 15)
        self.assertEqual(
            {bullet.slot for bullet in following.bullets}, set(range(15))
        )
        # ECL creates state 3 here; BulletManager then moves the newborns on
        # the same update, while they remain non-collidable spawn animation.
        self.assertTrue(all(bullet.state == 3 for bullet in following.bullets))
        self.assertTrue(all(bullet.timer == 1 for bullet in following.bullets))
        self.assertEqual(following.x, start.x + start.focus_speed)

    def test_scalar_oracle_accepts_source_spawning_states(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 11, target_bullets=1)
        spawning = replace(
            case.snapshot.bullets[0], state=3, timer=14, timer_float=14.0
        )
        snapshot = replace(case.snapshot, bullets=(spawning,))

        self.assertTrue(certify_linear_source(snapshot, 1).actions)
        self.assertEqual(
            certify_linear_source(snapshot, 2).actions,
            certify_linear_source(step_closed_world(
                snapshot, CONTROL_ACTIONS[0]
            ), 1).actions,
        )

    def test_stateful_terminal_metrics_keep_survival_positive(self):
        narrow_many = PlannerGuidanceValue(12, 1.0, 100.0, 100.0)
        clear_few = PlannerGuidanceValue(4, 9.0, 120.0, 100.0)

        self.assertGreater(
            _terminal_metric(narrow_many, "count-clearance"),
            _terminal_metric(clear_few, "count-clearance"),
        )
        self.assertGreater(
            _terminal_metric(clear_few, "clearance-count"),
            _terminal_metric(narrow_many, "clearance-count"),
        )
        self.assertEqual(_terminal_rungs(16), (8, 12, 16))
        focused = next(action for action in CONTROL_ACTIONS if action.name == "up")
        fast = next(
            action for action in CONTROL_ACTIONS if action.name == "up_fast"
        )
        self.assertGreater(
            _terminal_action_metric(
                narrow_many, "count-focus-clearance", focused
            ),
            _terminal_action_metric(
                replace(narrow_many, free_clearance=9.0),
                "count-focus-clearance",
                fast,
            ),
        )
        guidance = {focused: narrow_many, fast: replace(
            narrow_many, free_clearance=9.0
        )}
        first, confirmation = _terminal_preferred(
            guidance, "count-clearance-confirmed", None
        )
        second, _ = _terminal_preferred(
            guidance, "count-clearance-confirmed", confirmation
        )
        self.assertEqual(first, frozenset(guidance))
        self.assertEqual(second, frozenset((fast,)))

    def test_stateful_closed_loop_reports_actual_minimum_clearance(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )

        result = run_closed_loop(
            snapshot,
            lambda _snapshot: CONTROL_ACTIONS[0],
            frames=2,
            delivery_seed=0,
        )

        self.assertEqual(result.minimum_clearance, 999.0)

    def test_stateful_frame_continuation_is_an_explicit_count_policy(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        with mock.patch(
            "th06.barrage_lab.stateful.terminal_reachability_counts",
            side_effect=lambda _snapshot, candidates, *_args: {
                candidate.action: int(candidate.action == right)
                for candidate in candidates
            },
        ) as reachability:
            chosen = ExactTerminalPolicy(
                8,
                continuation="frame",
            )(snapshot)

        self.assertEqual(chosen, right)
        reachability.assert_called_once()
        with self.assertRaises(ValueError):
            ExactTerminalPolicy(
                8,
                metric="count-clearance",
                continuation="frame",
            )

    def test_stateful_policy_volume_replays_the_production_primitive(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )

        def policy_scores(_snapshot, candidates, *args, **kwargs):
            self.assertEqual(args, (4, 8))
            self.assertEqual(kwargs["continuation_actions"], CONTROL_ACTIONS)
            return {
                candidate.action: int(candidate.action == right)
                for candidate in candidates
            }

        with mock.patch(
            "th06.barrage_lab.stateful.nominal_policy_scores",
            side_effect=policy_scores,
        ) as scores:
            chosen = ExactTerminalPolicy(
                8, metric="policy-volume"
            )(snapshot)

        self.assertEqual(chosen, right)
        scores.assert_called_once()

    def test_stateful_policy_target_breaks_only_a_preferred_tie(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        left = next(
            action for action in CONTROL_ACTIONS if action.name == "left"
        )

        with mock.patch(
            "th06.barrage_lab.stateful.nominal_policy_scores",
            return_value={
                action: int(action in (left, right))
                for action in CONTROL_ACTIONS
            },
        ):
            chosen = ExactTerminalPolicy(
                8,
                metric="policy-volume",
                target=(snapshot.x + 100.0, snapshot.y),
            )(snapshot)

        self.assertEqual(chosen, right)

    def test_stateful_constant_frontier_replays_the_legacy_dense_primitive(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        hard = mock.Mock(
            actions=tuple(action.name for action in CONTROL_ACTIONS),
            terminal_positions=tuple(
                (action.name, snapshot.x, snapshot.y)
                for action in CONTROL_ACTIONS
            ),
        )
        constant = mock.Mock(actions=(right.name,))

        with mock.patch(
            "th06.barrage_lab.stateful.certify_linear_source",
            side_effect=(hard, constant),
        ) as certify:
            chosen = ExactTerminalPolicy(
                6, metric="constant-frontier"
            )(snapshot)

        self.assertEqual(chosen, right)
        self.assertEqual(certify.call_args_list[1].args[1], 6)

    def test_constant_clearance_ranks_only_the_unchanged_action_reserve(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        left = next(
            action for action in CONTROL_ACTIONS if action.name == "left"
        )
        hard = mock.Mock(
            actions=(right.name, left.name),
            terminal_positions=(
                (right.name, snapshot.x, snapshot.y),
                (left.name, snapshot.x, snapshot.y),
            ),
        )
        reserve = (
            SafeAction(right, 8.0, snapshot.x, snapshot.y),
            SafeAction(left, 3.0, snapshot.x, snapshot.y),
        )

        with mock.patch(
            "th06.barrage_lab.stateful.certify_linear_source",
            return_value=hard,
        ), mock.patch(
            "th06.barrage_lab.stateful.certify_actions",
            return_value=reserve,
        ) as certify:
            chosen = ExactTerminalPolicy(
                5, metric="constant-clearance"
            )(snapshot)

        self.assertEqual(chosen, right)
        self.assertEqual(certify.call_args.args[1], 5)

    def test_constant_frontier_count_excludes_deep_winner_outside_reserve(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        left = next(
            action for action in CONTROL_ACTIONS if action.name == "left"
        )
        down = next(
            action for action in CONTROL_ACTIONS if action.name == "down"
        )
        hard = mock.Mock(
            actions=tuple(action.name for action in CONTROL_ACTIONS),
            terminal_positions=tuple(
                (action.name, snapshot.x, snapshot.y)
                for action in CONTROL_ACTIONS
            ),
        )
        reserve = mock.Mock(actions=(right.name, left.name))
        counts = {action.name: 1 for action in CONTROL_ACTIONS}
        counts[right.name] = 3
        counts[left.name] = 2
        counts[down.name] = 10

        with mock.patch(
            "th06.barrage_lab.stateful.certify_linear_source",
            side_effect=(hard, reserve),
        ), mock.patch(
            "th06.barrage_lab.stateful.source_terminal_counts",
            return_value=mock.Mock(counts=tuple(counts.items())),
        ):
            chosen = ExactTerminalPolicy(
                10, metric="constant-frontier-count"
            )(snapshot)

        self.assertEqual(chosen, right)

    def test_local_count_vector_keeps_the_earliest_complete_rung_primary(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        left = next(
            action for action in CONTROL_ACTIONS if action.name == "left"
        )

        def counts_at_horizon(_snapshot, actions, _delay, horizon):
            values = {name: 1 for name in actions}
            values[right.name] = 3 if horizon == 8 else 1
            values[left.name] = 1 if horizon == 8 else 3
            return mock.Mock(counts=tuple(values.items()))

        with mock.patch(
            "th06.barrage_lab.stateful.source_terminal_counts",
            side_effect=counts_at_horizon,
        ):
            deep_first = ExactTerminalPolicy(
                16, metric="count-vector"
            )(snapshot)
            local_first = ExactTerminalPolicy(
                16, metric="local-count-vector"
            )(snapshot)

        self.assertEqual(deep_first, left)
        self.assertEqual(local_first, right)

    def test_authority_filter_preserves_deep_ranking_inside_viable_actions(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        snapshot = replace(
            generate_barrage_case((opcode,), 5, target_bullets=1).snapshot,
            bullets=(),
        )
        right = next(
            action for action in CONTROL_ACTIONS if action.name == "right"
        )
        left = next(
            action for action in CONTROL_ACTIONS if action.name == "left"
        )
        down = next(
            action for action in CONTROL_ACTIONS if action.name == "down"
        )

        def replanning(_snapshot, candidates, **_kwargs):
            values = {candidate.action: 1 for candidate in candidates}
            values[right] = 1
            values[left] = 2
            values[down] = 0
            return values

        def terminal(_snapshot, actions, _delay, _horizon):
            values = {name: 1 for name in actions}
            values[right.name] = 3
            values[left.name] = 1
            values[down.name] = 10
            return mock.Mock(counts=tuple(values.items()))

        with mock.patch(
            "th06.barrage_lab.stateful.source_replanning_scores",
            side_effect=replanning,
        ) as replanning_mock, mock.patch(
            "th06.barrage_lab.stateful.source_terminal_counts",
            side_effect=terminal,
        ):
            most_next_actions = ExactTerminalPolicy(
                16, metric="replanning-count"
            )(snapshot)
            filtered_deep = ExactTerminalPolicy(
                16, metric="authority-filtered-count"
            )(snapshot)

        self.assertEqual(most_next_actions, left)
        self.assertEqual(filtered_deep, right)
        self.assertTrue(all(
            call.kwargs["continuation_actions"] == CONTROL_ACTIONS
            for call in replanning_mock.call_args_list
        ))
        self.assertEqual(
            _authority_filtered_preferred(
                {right: 1, left: 2, down: 0},
                {right: 0, left: 0, down: 10},
            ),
            frozenset((right, left)),
        )
        self.assertEqual(
            _deep_preferred_within(
                frozenset((right, left)),
                {right: 3, left: 1, down: 10},
            ),
            frozenset((right,)),
        )
        self.assertEqual(
            _deep_preferred_within(
                frozenset((right, left)),
                {right: 0, left: 0, down: 10},
            ),
            frozenset((right, left)),
        )

    def test_delivery_ladder_keeps_last_complete_nonempty_rung(self):
        state = replace(
            generate_barrage_case(
                (parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0],),
                5,
                target_bullets=1,
            ).snapshot,
            bullets=(),
        )
        actions = CONTROL_ACTIONS[:3]
        candidates = tuple(
            SafeAction(action, 999.0, state.x, state.y)
            for action in actions
        )
        viability = {
            8: {actions[0]: 1, actions[1]: 1, actions[2]: 0},
            12: {actions[0]: 1, actions[1]: 0},
            16: {actions[0]: 0},
        }
        terminal = {
            8: {actions[0]: 2, actions[1]: 3},
            12: {actions[0]: 4},
        }
        calls = []

        def viability_at_horizon(working, rung):
            calls.append(("viability", rung, tuple(
                candidate.action for candidate in working
            )))
            return viability[rung]

        def terminal_at_horizon(working, rung):
            calls.append(("terminal", rung, tuple(
                candidate.action for candidate in working
            )))
            return terminal[rung]

        preferred = _progressive_delivery_preferred(
            candidates,
            16,
            viability_at_horizon,
            terminal_at_horizon,
        )

        self.assertEqual(preferred, frozenset((actions[0],)))
        self.assertEqual(
            calls,
            [
                ("viability", 8, actions),
                ("terminal", 8, actions[:2]),
                ("viability", 12, actions[:2]),
                ("terminal", 12, actions[:1]),
                ("viability", 16, actions[:1]),
            ],
        )

    def test_mismatch_reducer_keeps_earliest_horizon_and_provenance(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 23, target_bullets=8)
        far_bullets = tuple(
            replace(bullet, x=-1000.0, y=-1000.0, vx=0.0, vy=0.0)
            for bullet in case.snapshot.bullets
        )
        snapshot = replace(case.snapshot, bullets=far_bullets)

        def fake_certifier(state, horizon):
            expected = certify_linear_source(state, horizon).actions
            return expected[:-1] if horizon >= 3 and state.bullets else expected

        expected = certify_linear_source(snapshot, 8).actions
        mismatch = SweepMismatch(
            23, "fake", 8, expected, fake_certifier(snapshot, 8),
            snapshot, case.sources,
        )
        reduced = shrink_mismatch(mismatch, fake_certifier)
        self.assertEqual(reduced.horizon, 3)
        self.assertEqual(len(reduced.snapshot.bullets), 1)
        self.assertEqual(len(reduced.sources), 1)
        self.assertEqual(reduced.differing_actions, ("down_right_fast",))

    def test_source_planner_deduplicates_boundary_aliased_states(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 19, target_bullets=8)
        snapshot = replace(
            case.snapshot,
            bullets=(),
            x=376.0,
            y=432.0,
            input_mask=0xA4,
        )
        result = source_terminal_counts(snapshot, ("right",), 4, 8)

        # Nine focused continuation actions collapse to six physical endpoints
        # at the bottom-right clamp. Raw path multiplicity would report nine.
        self.assertEqual(result.counts, (("right", 6),))

    def test_seeded_source_planner_matches_production_reference(self):
        opcode = parse_ecl_bullet_opcodes(
            ecl_effect_bytes(), "effects.ecl"
        )[0]
        case = generate_barrage_case((opcode,), 0, target_bullets=64)
        candidates = certify_linear_source(case.snapshot, 4).actions
        expected = source_terminal_counts(
            case.snapshot, candidates, 4, 8
        ).counts

        self.assertEqual(
            python_terminal_counts(case.snapshot, candidates, 4, 8),
            expected,
        )

    def test_equal_clearance_target_uses_stable_position_order(self):
        opcode = parse_ecl_bullet_opcodes(
            ecl_effect_bytes(), "effects.ecl"
        )[0]
        case = generate_barrage_case((opcode,), 0, target_bullets=1)
        state = replace(
            case.snapshot,
            x=376.0,
            y=432.0,
            input_mask=0x10,
            bullets=(Bullet(
                x=384.7381591796875,
                y=331.3005065917969,
                vx=-0.7630788683891296,
                vy=2.961068630218506,
                half_width=2.0,
                half_height=2.0,
                state=1,
                ex_flags=520,
                speed=3.057812452316284,
                angle=1.8230124711990356,
                timer=20,
                timer_float=20.0,
                slot=639,
            ),),
        )

        expected = source_terminal_guidance(
            state, ("up_right",), 4, 8
        )[0][1]
        actual = python_terminal_guidance(
            state, ("up_right",), 4, 8
        )[0][1]

        self.assertEqual(expected[0], actual[0])
        self.assertAlmostEqual(expected[1], actual[1], places=3)
        self.assertEqual(expected[2:], (368.0, 426.3431))
        self.assertEqual(expected[2:], actual[2:])

    def test_planner_reducer_minimizes_horizon_candidate_and_bullets(self):
        opcode = parse_ecl_bullet_opcodes(ecl_bytes(), "test.ecl")[0]
        case = generate_barrage_case((opcode,), 29, target_bullets=8)
        far_bullets = tuple(
            replace(bullet, x=-1000.0, y=-1000.0, vx=0.0, vy=0.0)
            for bullet in case.snapshot.bullets
        )
        snapshot = replace(case.snapshot, bullets=far_bullets)
        candidates = ("stay", "right")

        def fake_planner(state, names, segment_length, horizon):
            counts = list(
                source_terminal_counts(
                    state, names, segment_length, horizon
                ).counts
            )
            if horizon >= 6 and state.bullets and "stay" in names:
                counts[names.index("stay")] = (
                    "stay", counts[names.index("stay")][1] + 1
                )
            return tuple(counts)

        expected = source_terminal_counts(
            snapshot, candidates, 4, 8
        ).counts
        mismatch = PlannerMismatch(
            29,
            "fake",
            4,
            8,
            candidates,
            expected,
            fake_planner(snapshot, candidates, 4, 8),
            snapshot,
            case.sources,
        )
        reduced = shrink_planner_mismatch(mismatch, fake_planner)

        self.assertEqual(reduced.horizon, 6)
        self.assertEqual(reduced.candidate_names, ("stay",))
        self.assertEqual(reduced.differing_actions, ("stay",))
        self.assertEqual(len(reduced.snapshot.bullets), 1)
        self.assertEqual(len(reduced.sources), 1)


if __name__ == "__main__":
    unittest.main()
