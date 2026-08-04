import struct
import unittest
from dataclasses import asdict, replace
from unittest import mock

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
    physical_step_parity,
    run_closed_loop,
    step_bullet,
    step_closed_world,
    step_fired_bullet,
    sweep_initial_snapshot,
    _terminal_metric,
    _terminal_action_metric,
    _authority_filtered_preferred,
    _deep_preferred_within,
    _terminal_preferred,
    _terminal_rungs,
)
from th06.hazards.bullets import hazard_box
from th06.model import CONTROL_ACTIONS, Bullet, EclInstruction


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
        with self.assertRaises(ValueError):
            sweep_initial_snapshot(
                (opcode,),
                0,
                runtime_templates=(runtime_barrage_template({
                    "x": 80.0, "y": 200.0, "bullets": (),
                }),),
                physical_initial_worlds=worlds,
            )

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
