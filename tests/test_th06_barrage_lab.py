import struct
import unittest
from dataclasses import replace

from th06.barrage_lab.assets import (
    Pbg3Archive,
    parse_ecl_bullet_opcodes,
)
from th06.barrage_lab.generator import (
    generate_barrage_case,
    stress_player_position,
)
from th06.barrage_lab.oracle import certify_linear_source
from th06.barrage_lab.planner import source_terminal_counts
from th06.barrage_lab.runner import (
    PlannerMismatch,
    SweepMismatch,
    python_terminal_counts,
    shrink_planner_mismatch,
    python_action_names,
    shrink_mismatch,
)
from th06.hazards.bullets import hazard_box
from th06.model import Bullet


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
